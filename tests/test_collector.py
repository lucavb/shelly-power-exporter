import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest
from aioshelly.rpc_device import RpcDevice
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families

import collector
from metrics import SnapshotCollector

FIXTURES = Path(__file__).parent / "fixtures"


def collect(device: FakeDevice, target: str | None = None):
    """Adapt the focused test double to the collector's upstream device annotation."""
    return collector.collect_metrics(cast(RpcDevice, device), target)


class FakeDevice:
    hostname = "shelly.local"
    ip_address = "192.0.2.10"
    model = "Test Shelly"
    firmware_version = "1.0.0"
    name = "Test"

    def __init__(self, result: dict[str, Any], initial_status: dict[str, Any] | None = None):
        self.result = result
        self.status = initial_status or {}
        self.calls: list[str] = []
        self.poll_calls = 0

    async def call_rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(method)
        return self.result

    async def poll(self) -> None:
        self.poll_calls += 1
        self.status.update(self.result)


@pytest.fixture
def snapshot(monkeypatch: pytest.MonkeyPatch) -> SnapshotCollector:
    registry = CollectorRegistry()
    result = SnapshotCollector()
    registry.register(result)
    monkeypatch.setattr(collector, "snapshot_collector", result)
    return result


def exposition(snapshot: SnapshotCollector) -> str:
    registry = CollectorRegistry()
    registry.register(snapshot)
    return generate_latest(registry).decode()


def find_sample(output: str, family_name: str, **labels: str) -> float:
    for family in text_string_to_metric_families(output):
        for sample in family.samples:
            if sample.name == family_name and all(
                sample.labels.get(key) == value for key, value in labels.items()
            ):
                return float(sample.value)
    raise AssertionError(f"No sample {family_name} with labels {labels}")


def test_uses_one_fresh_get_status_result_and_preserves_switch_compatibility(
    snapshot: SnapshotCollector,
) -> None:
    status = json.loads((FIXTURES / "switch_status.json").read_text())
    device = FakeDevice(status, {"switch:1": {"apower": 999.0}})

    result = asyncio.run(collect(device))
    output = exposition(snapshot)

    assert result.ok
    assert device.calls == ["Shelly.GetStatus"]
    assert device.poll_calls == 0
    assert 'shelly_power_watts{channel="0",device="aa:bb:cc:dd:ee:ff"} 42.5' in output
    assert 'shelly_switch_on{channel="0",device="aa:bb:cc:dd:ee:ff"} 1.0' in output
    assert 'shelly_energy_watthours_total{channel="0",device="aa:bb:cc:dd:ee:ff"} 100.0' in output
    assert (
        'shelly_energy_returned_watthours_total{channel="0",device="aa:bb:cc:dd:ee:ff"} 2.0'
        in output
    )
    assert 'shelly_temperature_celsius{channel="0",device="aa:bb:cc:dd:ee:ff"} 41.5' in output
    assert 'shelly_uptime_seconds{device="aa:bb:cc:dd:ee:ff"} 120.0' in output
    assert "999.0" not in output


def test_pm1_and_em1_power_are_collected_without_confusing_switch_power(
    snapshot: SnapshotCollector,
) -> None:
    pm1 = json.loads((FIXTURES / "pm1_status.json").read_text())
    em1 = json.loads((FIXTURES / "em1_status.json").read_text())
    device = FakeDevice({**pm1, **em1, "switch:0": {"output": False, "apower": 0.0}})

    asyncio.run(collect(device))
    output = exposition(snapshot)

    assert 'component="pm1",device="22:33:44:55:66:77",id="0"' in output
    assert 'component="em1",device="22:33:44:55:66:77",id="2"' in output
    assert (
        find_sample(
            output,
            "shelly_meter_power_watts",
            component="pm1",
            device="22:33:44:55:66:77",
            id="0",
        )
        == 8.5
    )
    assert (
        find_sample(
            output,
            "shelly_meter_power_watts",
            component="em1",
            device="22:33:44:55:66:77",
            id="2",
        )
        == 115.5
    )
    assert (
        find_sample(
            output,
            "shelly_meter_energy_watthours_total",
            component="em1data",
            device="22:33:44:55:66:77",
            id="2",
        )
        == 25.0
    )
    assert (
        find_sample(
            output,
            "shelly_meter_energy_returned_watthours_total",
            component="em1data",
            device="22:33:44:55:66:77",
            id="2",
        )
        == 1.0
    )
    assert (
        find_sample(
            output,
            "shelly_switch_on",
            channel="0",
            device="22:33:44:55:66:77",
        )
        == 0.0
    )
    assert (
        find_sample(
            output,
            "shelly_power_watts",
            channel="0",
            device="22:33:44:55:66:77",
        )
        == 0.0
    )


def test_em_three_phase_readings_keep_aggregate_separate(snapshot: SnapshotCollector) -> None:
    status = json.loads((FIXTURES / "pro_3em_minimal.json").read_text())
    device = FakeDevice({"sys": {"mac": "three-phase"}, **status})

    asyncio.run(collect(device))
    output = exposition(snapshot)

    assert "shelly_meter_em_power_watts" in output
    assert "253.2" in output and "459.6" in output and "115.5" in output
    assert 'phase="a"' in output and 'phase="b"' in output and 'phase="c"' in output
    for phase, value in zip("abc", (1200.0, 2300.0, 3400.0), strict=True):
        assert (
            find_sample(
                output,
                "shelly_meter_em_energy_watthours_total",
                component="emdata",
                device="three-phase",
                id="0",
                phase=phase,
            )
            == value
        )
    assert (
        find_sample(
            output,
            "shelly_meter_energy_watthours_total",
            component="emdata",
            device="three-phase",
            id="0",
        )
        == 6900.0
    )
    assert (
        find_sample(
            output,
            "shelly_meter_energy_returned_watthours_total",
            component="emdata",
            device="three-phase",
            id="0",
        )
        == 12.0
    )
    aggregate_lines = [line for line in output.splitlines() if "828.3" in line]
    assert len(aggregate_lines) == 1
    assert aggregate_lines[0].startswith("shelly_meter_power_watts{")
    assert "phase=" not in aggregate_lines[0]


def test_null_or_missing_measurements_are_not_reported_as_zero_but_real_zero_is(
    snapshot: SnapshotCollector,
) -> None:
    device = FakeDevice(
        {
            "sys": {"mac": "nullable"},
            "switch:0": {"output": False, "apower": 0.0, "voltage": None},
            "pm1:0": {"apower": None},
        }
    )

    asyncio.run(collect(device))
    output = exposition(snapshot)

    assert 'shelly_power_watts{channel="0",device="nullable"} 0.0' in output
    assert 'shelly_meter_power_watts{component="pm1"' not in output
    assert "shelly_voltage_volts" not in output
    assert 'shelly_switch_on{channel="0",device="nullable"} 0.0' in output


def test_missing_switch_fields_are_absent_while_explicit_zero_is_exported(
    snapshot: SnapshotCollector,
) -> None:
    device = FakeDevice(
        {
            "sys": {"mac": "distinguish"},
            "switch:0": {"apower": 0.0, "current": None},
            "switch:1": {"output": False, "apower": None},
        }
    )
    asyncio.run(collect(device))
    output = exposition(snapshot)

    assert find_sample(output, "shelly_power_watts", channel="0", device="distinguish") == 0.0
    assert 'shelly_power_watts{channel="1",device="distinguish"}' not in output
    assert 'shelly_current_amperes{channel="0",device="distinguish"}' not in output
    assert find_sample(output, "shelly_switch_on", channel="1", device="distinguish") == 0.0


def test_pm1_consumed_energy_subtracts_returned_energy_when_both_are_present(
    snapshot: SnapshotCollector,
) -> None:
    device = FakeDevice(
        {
            "sys": {"mac": "pm-energy"},
            "pm1:0": {
                "apower": 15.0,
                "aenergy": {"total": 125.0},
                "ret_aenergy": {"total": 25.0},
            },
            "pm1:1": {"apower": 3.0, "aenergy": {"total": 50.0}},
            "switch:0": {
                "output": True,
                "apower": 1.0,
                "aenergy": {"total": 125.0},
                "ret_aenergy": {"total": 25.0},
            },
        }
    )

    asyncio.run(collect(device))
    output = exposition(snapshot)

    assert (
        find_sample(
            output,
            "shelly_meter_energy_watthours_total",
            component="pm1",
            device="pm-energy",
            id="0",
        )
        == 100.0
    )
    assert (
        'shelly_meter_energy_watthours_total{component="pm1",device="pm-energy",id="1"}'
        not in output
    )
    # Switch totals retain their established semantics (no PM1 adjustment).
    assert (
        find_sample(output, "shelly_energy_watthours_total", device="pm-energy", channel="0")
        == 125.0
    )


def test_success_replaces_disappeared_components_and_fields(snapshot: SnapshotCollector) -> None:
    device = FakeDevice({"sys": {"mac": "gone"}, "pm1:0": {"apower": 4.0, "voltage": 230.0}})
    asyncio.run(collect(device))
    assert 'shelly_meter_power_watts{component="pm1"' in exposition(snapshot)

    device.result = {"sys": {"mac": "gone"}, "pm1:1": {"voltage": 230.0}}
    asyncio.run(collect(device))
    output = exposition(snapshot)

    assert 'component="pm1",device="gone",id="0"' not in output
    assert 'component="pm1",device="gone",id="1"' in output
    assert 'shelly_meter_power_watts{component="pm1"' not in output


def test_device_errors_use_a_bounded_error_label_set(snapshot: SnapshotCollector) -> None:
    device = FakeDevice(
        {
            "sys": {"mac": "errors"},
            "switch:0": {"apower": 1.0, "errors": ["overtemp", "made_up_unbounded_error"]},
            "pm1:0": {"errors": ["overpower"]},
        }
    )

    asyncio.run(collect(device))
    output = exposition(snapshot)

    assert 'component="switch",device="errors",error="overtemp",id="0"} 1.0' in output
    assert 'component="pm1",device="errors",error="overpower",id="0"} 1.0' in output
    assert 'component="pm1",device="errors",error="overtemp",id="0"} 0.0' in output
    assert "made_up_unbounded_error" not in output
    error_samples = [
        line for line in output.splitlines() if line.startswith("shelly_device_error{")
    ]
    assert len(error_samples) <= 10


def test_expiration_is_target_specific_and_preserves_failure_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    registry = CollectorRegistry()
    snapshot = SnapshotCollector()
    registry.register(snapshot)
    monkeypatch.setattr("metrics.METRICS_MAX_AGE_SECONDS", 5)
    monkeypatch.setattr("metrics.time.monotonic", lambda: now[0])
    monkeypatch.setattr(collector, "snapshot_collector", snapshot)
    monkeypatch.setattr(collector, "_total_failures", 0)
    monkeypatch.setattr(collector, "_consecutive_failures", 0)
    fresh_device = FakeDevice({"sys": {"mac": "fresh-mac"}, "switch:0": {"apower": 10}})
    stale_device = FakeDevice(
        {
            "sys": {"mac": "stale-mac"},
            "switch:0": {"apower": 20},
            "switch:1": {"errors": ["overtemp"]},
        }
    )
    asyncio.run(collect(fresh_device, target="fresh"))
    asyncio.run(collect(stale_device, target="stale"))

    now[0] = 4.999
    before = generate_latest(registry).decode()
    assert 'shelly_power_watts{channel="0",device="fresh-mac"} 10.0' in before
    assert 'shelly_power_watts{channel="0",device="stale-mac"} 20.0' in before

    class BrokenDevice(FakeDevice):
        async def call_rpc(
            self, method: str, params: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            raise RuntimeError("offline")

    asyncio.run(collect(BrokenDevice({}), target="stale"))
    asyncio.run(collect(BrokenDevice({}), target="stale"))
    failed = generate_latest(registry).decode()
    assert (
        'shelly_device_error{component="switch",device="stale-mac",error="overtemp",id="1"} 1.0'
        in failed
    )
    now[0] = 5.0
    fresh_device.result = {"sys": {"mac": "fresh-mac"}, "switch:0": {"apower": 11}}
    asyncio.run(collect(fresh_device, target="fresh"))
    after = generate_latest(registry).decode()
    assert 'shelly_power_watts{channel="0",device="fresh-mac"} 11.0' in after
    assert 'shelly_power_watts{channel="0",device="stale-mac"} 20.0' not in after
    # Error state remains visible until max age; expired snapshots no longer expose it.
    assert (
        'shelly_device_error{component="switch",device="stale-mac",error="overtemp",id="1"} 1.0'
    ) not in after
    failure_family = next(
        family
        for family in text_string_to_metric_families(after)
        if family.name == "shelly_poll_failures"
    )
    failure_sample = next(
        sample
        for sample in failure_family.samples
        if sample.name == "shelly_poll_failures_total" and sample.labels["target"] == "stale"
    )
    assert failure_sample.value >= 2.0


def test_exposition_contains_valid_info_and_health_by_configured_target(
    snapshot: SnapshotCollector,
) -> None:
    device = FakeDevice(json.loads((FIXTURES / "switch_status.json").read_text()))
    asyncio.run(collect(device, target="shelly.example.internal"))
    output = exposition(snapshot)

    assert 'shelly_target_up{target="shelly.example.internal"} 1.0' in output
    assert 'shelly_info_info{device="aa:bb:cc:dd:ee:ff"' in output
    assert 'model="Test Shelly"' in output and 'firmware="1.0.0"' in output
    parsed = list(text_string_to_metric_families(output))
    info_samples = [
        sample
        for family in parsed
        for sample in family.samples
        if sample.name == "shelly_info_info"
    ]
    assert any(sample.labels["model"] == "Test Shelly" for sample in info_samples)


def test_failure_marks_health_down_and_freshness_expires_at_explicit_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "RECONNECT_AFTER_POLL_FAILURES", 1)
    clock = [100.0]
    monkeypatch.setattr("metrics.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("metrics.METRICS_MAX_AGE_SECONDS", 10)
    collector_snapshot = SnapshotCollector()
    registry = CollectorRegistry()
    registry.register(collector_snapshot)
    monkeypatch.setattr(collector, "snapshot_collector", collector_snapshot)
    device = FakeDevice({"sys": {"mac": "offline"}, "switch:0": {"apower": 22.0}})
    asyncio.run(collect(device))
    assert "shelly_power_watts" in exposition(collector_snapshot)

    class BrokenDevice(FakeDevice):
        async def call_rpc(
            self, method: str, params: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            raise RuntimeError("unavailable")

    result = asyncio.run(collect(BrokenDevice({}, {"sys": {"mac": "offline"}})))
    assert not result.ok and result.recycle_connection
    assert 'shelly_target_up{target="192.0.2.10"} 0.0' in exposition(collector_snapshot)

    # Connection recycling does not refresh the prior success timestamp.
    collector.reset_poll_failure_counter()
    collector_snapshot.set_health("192.0.2.10", False, "offline")
    clock[0] = 109.999
    assert "shelly_power_watts" in exposition(collector_snapshot)
    clock[0] = 110.0
    output = exposition(collector_snapshot)
    assert "shelly_power_watts" not in output
    assert 'shelly_target_up{target="192.0.2.10"} 0.0' in output
