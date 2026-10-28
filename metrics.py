"""Prometheus metric definitions and the atomic device snapshot collector."""

import threading
import time
from collections.abc import Mapping
from typing import Any

from prometheus_client import (
    GC_COLLECTOR,
    PLATFORM_COLLECTOR,
    PROCESS_COLLECTOR,
    CollectorRegistry,
    start_http_server,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, InfoMetricFamily

from config import METRICS_MAX_AGE_SECONDS

NAMESPACE = "shelly"

_SWITCH_FIELDS = {
    "switch_on": ("Switch output state (1 = on, 0 = off)", "switch_on"),
    "power_watts": ("Active power in watts", "apower"),
    "voltage_volts": ("Voltage in volts", "voltage"),
    "current_amperes": ("Current in amperes", "current"),
    "frequency_hertz": ("Grid frequency in hertz", "freq"),
}
_METER_METRICS = {
    "power_watts": ("Active power in watts", "apower"),
    "voltage_volts": ("Voltage in volts", "voltage"),
    "current_amperes": ("Current in amperes", "current"),
    "frequency_hertz": ("Grid frequency in hertz", "freq"),
    "energy_watthours_total": ("Total energy consumed in watt-hours", "aenergy.total"),
    "energy_returned_watthours_total": ("Total energy returned in watt-hours", "ret_aenergy.total"),
}
_SWITCH_METRIC_SPECS = {
    "switch_on": ("Switch output state (1 = on, 0 = off)", ["device", "channel"]),
    "power_watts": ("Active power in watts", ["device", "channel"]),
    "voltage_volts": ("Voltage in volts", ["device", "channel"]),
    "current_amperes": ("Current in amperes", ["device", "channel"]),
    "frequency_hertz": ("Grid frequency in hertz", ["device", "channel"]),
    "energy_watthours_total": ("Total energy consumed in watt-hours", ["device", "channel"]),
    "energy_returned_watthours_total": (
        "Total energy returned in watt-hours",
        ["device", "channel"],
    ),
    "temperature_celsius": ("Device temperature in celsius", ["device", "channel"]),
    "wifi_rssi_dbm": ("WiFi signal strength in dBm", ["device"]),
    "uptime_seconds": ("Device uptime in seconds", ["device"]),
    "last_poll_success_timestamp_seconds": (
        "Unix timestamp of the last successful poll",
        ["target"],
    ),
    "poll_duration_seconds": (
        "Duration of the most recent poll attempt in seconds",
        ["target"],
    ),
    "device_error": (
        "Shelly device component error flag (bounded error names)",
        ["device", "component", "id", "error"],
    ),
    "meter_power_watts": ("Meter active power in watts", ["device", "component", "id"]),
    "meter_voltage_volts": ("Meter voltage in volts", ["device", "component", "id"]),
    "meter_current_amperes": ("Meter current in amperes", ["device", "component", "id"]),
    "meter_frequency_hertz": ("Meter frequency in hertz", ["device", "component", "id"]),
    "meter_energy_watthours_total": (
        "Meter total consumed energy in watt-hours",
        ["device", "component", "id"],
    ),
    "meter_energy_returned_watthours_total": (
        "Meter total returned energy in watt-hours",
        ["device", "component", "id"],
    ),
    "meter_em_power_watts": (
        "EM phase active power in watts",
        ["device", "component", "id", "phase"],
    ),
    "meter_em_voltage_volts": (
        "EM phase voltage in volts",
        ["device", "component", "id", "phase"],
    ),
    "meter_em_current_amperes": (
        "EM phase current in amperes",
        ["device", "component", "id", "phase"],
    ),
    "meter_em_frequency_hertz": (
        "EM phase frequency in hertz",
        ["device", "component", "id", "phase"],
    ),
    "meter_em_energy_watthours_total": (
        "EM/EMData phase consumed energy in watt-hours",
        ["device", "component", "id", "phase"],
    ),
    "meter_em_energy_returned_watthours_total": (
        "EM/EMData phase returned energy in watt-hours",
        ["device", "component", "id", "phase"],
    ),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _nested(mapping: Mapping[str, Any], path: str) -> Any:
    value: Any = mapping
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _snapshot_metric_series(
    metrics: Mapping[str, dict[tuple[str, ...], float]],
) -> dict[str, dict[tuple[str, ...], float]]:
    """Copy nested metric maps so later updates cannot alter a scrape in progress."""
    return {name: dict(series) for name, series in metrics.items()}


class SnapshotCollector:
    """Thread-safe, atomic snapshot exposed to Prometheus without stale series."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._devices: dict[str, dict[str, Any]] = {}

    def set_health(
        self,
        target: str,
        up: bool,
        mac: str | None = None,
        failure_count: int | None = None,
        duration: float | None = None,
    ) -> None:
        with self._lock:
            device = self._devices.setdefault(target, {"metrics": {}, "info": {}})
            device["target_up"] = int(up)
            if failure_count is not None:
                device.setdefault("metrics", {})["poll_failures"] = {
                    (target,): float(failure_count)
                }
            if duration is not None:
                device.setdefault("metrics", {})["poll_duration_seconds"] = {(target,): duration}
            known_mac = mac or device.get("mac")
            if known_mac:
                device["mac"] = known_mac
                device["up"] = int(up)

    def get_device_mac(self, target: str) -> str | None:
        with self._lock:
            device = self._devices.get(target)
            mac = device.get("mac") if device else None
            return str(mac) if mac else None

    def set_success(
        self,
        target: str,
        mac: str | None,
        status: Mapping[str, Any],
        info: Mapping[str, str],
        success_unix: float,
        duration: float,
        errors: Mapping[tuple[str, str, str], float],
        failure_count: int = 0,
    ) -> None:
        """Replace all measurement data in one operation; omitted fields are absent."""
        if mac is None:
            with self._lock:
                existing = self._devices.setdefault(target, {"metrics": {}, "info": {}})
                existing.update(
                    {
                        "target_up": 1,
                        "metrics": {
                            "last_poll_success_timestamp_seconds": {(target,): success_unix},
                            "poll_duration_seconds": {(target,): duration},
                            "poll_failures": {(target,): float(failure_count)},
                        },
                        "success_monotonic": time.monotonic(),
                    }
                )
            return
        values: dict[str, dict[tuple[str, ...], float]] = {}
        for component, data in status.items() if mac else ():
            if not isinstance(data, Mapping):
                continue
            if component.startswith("switch:"):
                channel = component.partition(":")[2]
                if not channel:
                    continue
                for metric, (_, source) in _SWITCH_FIELDS.items():
                    if source == "switch_on":
                        output = data.get("output")
                        value = float(output) if isinstance(output, bool) else None
                    else:
                        value = _number(data.get(source))
                    if value is not None:
                        values.setdefault(metric, {})[(mac, channel)] = value
                for metric, path in (
                    ("energy_watthours_total", "aenergy.total"),
                    ("energy_returned_watthours_total", "ret_aenergy.total"),
                    ("temperature_celsius", "temperature.tC"),
                ):
                    value = _number(_nested(data, path))
                    if value is not None:
                        values.setdefault(metric, {})[(mac, channel)] = value
            elif component.startswith(("pm1:", "em1:", "em1data:", "em:", "emdata:")):
                component_type, _, component_id = component.partition(":")
                if component_type == "emdata":
                    for metric, suffix in (
                        ("energy_watthours_total", "total_act"),
                        ("energy_returned_watthours_total", "total_act_ret"),
                    ):
                        for phase in ("a", "b", "c"):
                            energy_field = (
                                f"{phase}_total_act_energy"
                                if metric == "energy_watthours_total"
                                else f"{phase}_total_act_ret_energy"
                            )
                            phase_value = _number(data.get(energy_field))
                            if phase_value is not None:
                                values.setdefault("meter_em_" + metric, {})[
                                    (mac, component_type, component_id, phase)
                                ] = phase_value
                        total_value = _number(data.get(suffix))
                        if total_value is not None:
                            values.setdefault("meter_" + metric, {})[
                                (mac, component_type, component_id)
                            ] = total_value
                if component_type == "em":
                    phase_fields = {
                        "power_watts": ("act_power", "_act_power"),
                        "voltage_volts": ("voltage", "_voltage"),
                        "current_amperes": ("current", "_current"),
                        "frequency_hertz": ("freq", "_freq"),
                        "energy_watthours_total": ("act_energy", "_total_act_energy"),
                        "energy_returned_watthours_total": (
                            "act_ret_energy",
                            "_total_act_ret_energy",
                        ),
                    }
                    phases = ("a", "b", "c")
                    for metric, (total_field, phase_suffix) in phase_fields.items():
                        for phase in phases:
                            phase_value = _number(data.get(phase + phase_suffix))
                            if phase_value is not None:
                                values.setdefault("meter_em_" + metric, {})[
                                    (mac, component_type, component_id, phase)
                                ] = phase_value
                        total_value = _number(data.get("total_" + total_field))
                        if total_value is None:
                            total_value = _number(data.get(total_field))
                        if total_value is not None:
                            values.setdefault("meter_" + metric, {})[
                                (mac, component_type, component_id)
                            ] = total_value
                for metric, (_, source) in _METER_METRICS.items():
                    if component_type in ("em", "emdata"):
                        continue
                    component_source = source.strip()
                    component_sources = [component_source]
                    if component_type in ("em1", "em1data"):
                        if component_source == "apower":
                            component_sources.append("act_power")
                        elif component_source == "aenergy.total":
                            if component_type == "em1data":
                                component_sources.append("total_act_energy")
                            else:
                                component_sources.append("act_energy")
                        elif component_source == "ret_aenergy.total":
                            if component_type == "em1data":
                                component_sources.append("total_act_ret_energy")
                            else:
                                component_sources.append("act_ret_energy")
                    value = next(
                        (
                            parsed
                            for source_path in component_sources
                            if (parsed := _number(_nested(data, source_path))) is not None
                        ),
                        None,
                    )
                    if value is None:
                        continue
                    labels = (mac, component_type, component_id)
                    if component_type == "pm1" and metric == "energy_watthours_total":
                        total_energy = value
                        returned_energy = _number(_nested(data, "ret_aenergy.total"))
                        if returned_energy is None:
                            continue
                        value = total_energy - returned_energy
                    values.setdefault("meter_" + metric, {})[labels] = value
        wifi = status.get("wifi")
        if mac is not None and isinstance(wifi, Mapping):
            value = _number(wifi.get("rssi"))
            if value is not None:
                values.setdefault("wifi_rssi_dbm", {})[(mac,)] = value
        sys_data = status.get("sys")
        if mac is not None and isinstance(sys_data, Mapping):
            value = _number(sys_data.get("uptime"))
            if value is not None:
                values.setdefault("uptime_seconds", {})[(mac,)] = value
        values.setdefault("last_poll_success_timestamp_seconds", {})[(target,)] = success_unix
        values.setdefault("poll_duration_seconds", {})[(target,)] = duration
        values.setdefault("poll_failures", {})[(target,)] = float(failure_count)
        if mac is not None:
            for (component, component_id, error), active in errors.items():
                values.setdefault("device_error", {})[(mac, component, component_id, error)] = (
                    active
                )
        with self._lock:
            existing = self._devices.setdefault(target, {})
            existing.update(
                {
                    "mac": mac,
                    "up": 1,
                    "target_up": 1,
                    "metrics": values,
                    "info": dict(info),
                    "success_monotonic": time.monotonic(),
                }
            )

    def set_initial_health(self, target: str, up: bool = False) -> None:
        self.set_health(target, up)

    def known_targets(self) -> list[str]:
        with self._lock:
            return list(self._devices)

    def collect(self):
        with self._lock:
            snapshot = {
                key: {
                    **value,
                    "info": dict(value.get("info", {})),
                    "metrics": _snapshot_metric_series(value.get("metrics", {})),
                }
                for key, value in self._devices.items()
            }
            # Derive expiry while holding the lock, so a publication racing a scrape
            # cannot have newer health overwritten by stale state.
            freshness = METRICS_MAX_AGE_SECONDS
            now = time.monotonic()
            if freshness > 0:
                for device in snapshot.values():
                    success = device.get("success_monotonic")
                    if success is not None and now - success >= freshness:
                        device["metrics"] = {
                            name: series
                            for name, series in device["metrics"].items()
                            if name
                            in (
                                "last_poll_success_timestamp_seconds",
                                "poll_duration_seconds",
                                "poll_failures",
                            )
                        }
                        device["up"] = 0
                        device["target_up"] = 0
            for target, device in snapshot.items():
                metrics = device.get("metrics", {})
                if "poll_failures" not in metrics:
                    metrics["poll_failures"] = {(target,): 0.0}
        yield from self._collect_snapshot(snapshot)

    @staticmethod
    def _collect_snapshot(snapshot: dict[str, dict[str, Any]]):
        specs = {
            "switch_on": ("Switch output state (1 = on, 0 = off)", ["device", "channel"]),
            "power_watts": ("Active power in watts", ["device", "channel"]),
            "voltage_volts": ("Voltage in volts", ["device", "channel"]),
            "current_amperes": ("Current in amperes", ["device", "channel"]),
            "frequency_hertz": ("Grid frequency in hertz", ["device", "channel"]),
            "energy_watthours_total": (
                "Total energy consumed in watt-hours",
                ["device", "channel"],
            ),
            "energy_returned_watthours_total": (
                "Total energy returned in watt-hours",
                ["device", "channel"],
            ),
            "temperature_celsius": ("Device temperature in celsius", ["device", "channel"]),
            "wifi_rssi_dbm": ("WiFi signal strength in dBm", ["device"]),
            "uptime_seconds": ("Device uptime in seconds", ["device"]),
            "last_poll_success_timestamp_seconds": (
                "Unix timestamp of the last successful poll",
                ["target"],
            ),
            "poll_duration_seconds": (
                "Duration of the most recent poll attempt in seconds",
                ["target"],
            ),
            "device_error": (
                "Shelly device component error flag (bounded error names)",
                ["device", "component", "id", "error"],
            ),
            "meter_power_watts": ("Meter active power in watts", ["device", "component", "id"]),
            "meter_voltage_volts": ("Meter voltage in volts", ["device", "component", "id"]),
            "meter_current_amperes": ("Meter current in amperes", ["device", "component", "id"]),
            "meter_frequency_hertz": ("Meter frequency in hertz", ["device", "component", "id"]),
            "meter_energy_watthours_total": (
                "Meter total consumed energy in watt-hours",
                ["device", "component", "id"],
            ),
            "meter_energy_returned_watthours_total": (
                "Meter total returned energy in watt-hours",
                ["device", "component", "id"],
            ),
            "meter_em_power_watts": (
                "EM phase active power in watts",
                ["device", "component", "id", "phase"],
            ),
            "meter_em_voltage_volts": (
                "EM phase voltage in volts",
                ["device", "component", "id", "phase"],
            ),
            "meter_em_current_amperes": (
                "EM phase current in amperes",
                ["device", "component", "id", "phase"],
            ),
            "meter_em_frequency_hertz": (
                "EM phase frequency in hertz",
                ["device", "component", "id", "phase"],
            ),
            "meter_em_energy_watthours_total": (
                "EM/EMData phase consumed energy in watt-hours",
                ["device", "component", "id", "phase"],
            ),
            "meter_em_energy_returned_watthours_total": (
                "EM/EMData phase returned energy in watt-hours",
                ["device", "component", "id", "phase"],
            ),
        }
        specs.update(_SWITCH_METRIC_SPECS)
        for metric, (description, _) in _METER_METRICS.items():
            specs["meter_" + metric] = (description, ["device", "component", "id"])
            specs["meter_em_" + metric] = (description, ["device", "component", "id", "phase"])
        families: dict[str, GaugeMetricFamily] = {}
        failure_counts: dict[str, float] = {}
        target_health: dict[str, int] = {}
        device_health: dict[str, int] = {}
        infos: dict[str, dict[str, str]] = {}
        for target, device in snapshot.items():
            if "target_up" in device:
                target_health[target] = device["target_up"]
            if device.get("mac") and "up" in device:
                device_health[device["mac"]] = device["up"]
            if device.get("mac") and device.get("info"):
                infos[device["mac"]] = device["info"]
            for metric, series in device.get("metrics", {}).items():
                if metric == "poll_failures":
                    failure_counts[target] = next(iter(series.values()), 0.0)
                    continue
                if metric not in specs:
                    continue
                description, labels = specs[metric]
                family_name = metric
                if metric.startswith("meter_em_"):
                    labels = ["device", "component", "id", "phase"]
                elif metric.startswith("meter_"):
                    labels = ["device", "component", "id"]
                family = families.setdefault(
                    family_name,
                    GaugeMetricFamily(f"{NAMESPACE}_{family_name}", description, labels=labels),
                )
                for label_values, value in series.items():
                    family.add_metric(list(label_values), value)
        if failure_counts:
            family = CounterMetricFamily(
                f"{NAMESPACE}_poll_failures_total",
                "Total failed device polls since exporter start",
                labels=["target"],
            )
            for target, value in failure_counts.items():
                family.add_metric([target], value)
            yield family
        if target_health:
            family = GaugeMetricFamily(
                f"{NAMESPACE}_target_up",
                "Target reachability status (1 = up, 0 = down)",
                labels=["target"],
            )
            for target, value in target_health.items():
                family.add_metric([target], value)
            yield family
        if device_health:
            family = GaugeMetricFamily(
                f"{NAMESPACE}_up",
                "Device reachability status (1 = up, 0 = down)",
                labels=["device"],
            )
            for device, value in device_health.items():
                family.add_metric([device], value)
            yield family
        if infos:
            family = InfoMetricFamily(
                f"{NAMESPACE}_info",
                "Device information labels",
                labels=["device"],
            )
            for device, values in infos.items():
                family.add_metric([device], values)
            yield family
        yield from families.values()


snapshot_collector = SnapshotCollector()
registry = CollectorRegistry(auto_describe=True)
registry.register(GC_COLLECTOR)
registry.register(PLATFORM_COLLECTOR)
registry.register(PROCESS_COLLECTOR)
registry.register(snapshot_collector)


def start_metrics_server(port: int) -> None:
    """Start the custom registry HTTP endpoint in Prometheus' background thread."""
    start_http_server(port, registry=registry)
