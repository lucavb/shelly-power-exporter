import asyncio
import logging
from typing import Any, cast

import pytest
from aioshelly.rpc_device.wsrpc import WsRPC
from prometheus_client import CollectorRegistry, generate_latest

import main
from config import setup_logging
from metrics import SnapshotCollector


def options_from_main(
    monkeypatch: pytest.MonkeyPatch,
    *,
    username: str | None,
    password: str | None,
) -> Any:
    registry = CollectorRegistry()
    snapshot = SnapshotCollector()
    registry.register(snapshot)
    monkeypatch.setattr(main, "snapshot_collector", snapshot)
    monkeypatch.setattr(main, "get_shelly_credentials", lambda: (username, password))
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_MAX_SECONDS", 0)
    monkeypatch.setattr(main, "SCRAPE_INTERVAL", 0)
    monkeypatch.setattr(main, "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", 0)

    instances: list[Any] = []

    class Device:
        name = "device"
        model = "model"
        firmware_version = "firmware"

        def __init__(self) -> None:
            self.initialized = False
            self.shutdown_calls = 0

        @classmethod
        async def create(cls, session: Any, device: Any, options: Any) -> Device:
            observed.append(options)
            instance = cls()
            instances.append(instance)
            return instance

        async def initialize(self) -> None:
            self.initialized = True

        async def shutdown(self) -> None:
            self.shutdown_calls += 1

    observed: list[Any] = []
    monkeypatch.setattr(main, "RpcDevice", Device)
    monkeypatch.setattr(main, "reset_poll_failure_counter", lambda: None)

    async def success(device: Any, target: str) -> Any:
        main.shutdown_event.set()
        return type("Result", (), {"ok": True, "recycle_connection": False})()

    monkeypatch.setattr(main, "collect_metrics", success)
    main.shutdown_event = asyncio.Event()
    asyncio.run(main.main_loop("shelly.local"))
    return observed[0]


def test_rpc_credentials_are_optional_and_only_passed_when_password_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unauthenticated = options_from_main(monkeypatch, username=None, password=None)
    authenticated = options_from_main(
        monkeypatch, username="operator", password="test-secret-value"
    )

    assert unauthenticated.username is None
    assert unauthenticated.password is None
    assert authenticated.username == "operator"
    assert authenticated.password == "test-secret-value"


def test_password_is_never_written_to_logs(monkeypatch: pytest.MonkeyPatch, caplog: Any) -> None:
    options_from_main(monkeypatch, username="operator", password="test-secret-value")
    assert "test-secret-value" not in caplog.text


def test_debug_logging_does_not_emit_raw_authenticated_rpc_frames(
    monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    monkeypatch.setenv("DEBUG", "true")
    setup_logging()
    protocol_logger = logging.getLogger("aioshelly.rpc_device.wsrpc")
    caplog.set_level(logging.DEBUG)
    frame = {"method": "Shelly.GetStatus", "params": {"Authorization": "secret-digest"}}

    async def send_frame() -> None:
        rpc = WsRPC("shelly.local", lambda *_args: None)
        rpc._client = cast(Any, type("FakeClient", (), {"send_frame": _async_send_frame})())
        await rpc._send_json(frame)

    asyncio.run(send_frame())

    assert protocol_logger.level >= logging.INFO
    assert "secret-digest" not in caplog.text


async def _async_send_frame(self: Any, data: bytes, message_type: Any) -> None:
    return None


def test_failed_initialize_shuts_down_partial_device_and_exposes_initial_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = CollectorRegistry()
    snapshot = SnapshotCollector()
    registry.register(snapshot)
    monkeypatch.setattr(main, "snapshot_collector", snapshot)
    monkeypatch.setattr(main, "get_shelly_credentials", lambda: (None, None))
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_MAX_SECONDS", 0)
    monkeypatch.setattr(main, "EXIT_AFTER_CONSECUTIVE_INIT_FAILURES", 0)
    monkeypatch.setattr(main, "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", 0)
    devices: list[Any] = []

    class BrokenDevice:
        name = "bad"
        model = "bad"
        firmware_version = "bad"

        @classmethod
        async def create(cls, session: Any, device: Any, options: Any) -> BrokenDevice:
            instance = cls()
            devices.append(instance)
            return instance

        async def initialize(self) -> None:
            if len(devices) == 1:
                raise RuntimeError("initialization rejected")

        async def shutdown(self) -> None:
            self.shutdown_calls = getattr(self, "shutdown_calls", 0) + 1

    async def stop_sleep(seconds: float) -> None:
        return None

    async def succeed(device: Any, target: str) -> Any:
        main.shutdown_event.set()
        return type("Result", (), {"ok": True, "recycle_connection": False})()

    monkeypatch.setattr(main, "RpcDevice", BrokenDevice)
    monkeypatch.setattr(main, "_sleep_until_shutdown", stop_sleep)
    monkeypatch.setattr(main, "collect_metrics", succeed)
    main.shutdown_event = asyncio.Event()

    asyncio.run(main.main_loop("shelly.local"))
    output = generate_latest(registry).decode()

    assert len(devices) == 2
    assert devices[0].shutdown_calls == 1
    assert devices[1].shutdown_calls == 1
    assert 'shelly_target_up{target="shelly.local"} 0.0' in output


def test_no_poll_success_limit_uses_monotonic_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", 10)
    values = iter((25.0, 25.0))
    monkeypatch.setattr(main.time, "monotonic", lambda: next(values))

    with pytest.raises(SystemExit) as error:
        main._fatal_no_poll_success(start_monotonic=10.0, last_poll_success=None)

    assert error.value.code == 1


@pytest.mark.parametrize("wait_kind", ["init_retry", "poll_recycle", "scrape"])
def test_watchdog_bounds_reconnect_and_scrape_waits(
    monkeypatch: pytest.MonkeyPatch, wait_kind: str
) -> None:
    monkeypatch.setattr(main, "get_shelly_credentials", lambda: (None, None))
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_SECONDS", 20)
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_MAX_SECONDS", 20)
    monkeypatch.setattr(main, "SCRAPE_INTERVAL", 30)
    monkeypatch.setattr(main, "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", 5)
    monkeypatch.setattr(main, "EXIT_AFTER_CONSECUTIVE_INIT_FAILURES", 0)
    monkeypatch.setattr(
        main,
        "snapshot_collector",
        type(
            "Snapshot",
            (),
            {
                "set_initial_health": lambda *_args: None,
            },
        )(),
    )
    monkeypatch.setattr(main, "reset_poll_failure_counter", lambda: None)

    clock = [10.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    sleep_durations: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_durations.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(main, "_sleep_until_shutdown", capture_sleep)

    class Device:
        name = model = firmware_version = "device"

        @classmethod
        async def create(cls, session: Any, device: Any, options: Any) -> Device:
            return cls()

        async def initialize(self) -> None:
            if wait_kind == "init_retry":
                raise RuntimeError("init failure")

        async def shutdown(self) -> None:
            return None

    async def failed_poll(device: Any, target: str) -> Any:
        return type(
            "Result",
            (),
            {
                "ok": False,
                "recycle_connection": wait_kind == "poll_recycle",
                "consecutive_poll_failures": 1,
            },
        )()

    monkeypatch.setattr(main, "RpcDevice", Device)
    monkeypatch.setattr(main, "collect_metrics", failed_poll)
    main.shutdown_event = asyncio.Event()

    with pytest.raises(SystemExit) as error:
        asyncio.run(main.main_loop("shelly.local"))

    assert error.value.code == 1
    assert sleep_durations == [5]


def test_watchdog_sleep_preserves_disabled_and_shutdown_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_durations: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_durations.append(seconds)

    monkeypatch.setattr(main, "_sleep_until_shutdown", capture_sleep)
    monkeypatch.setattr(main, "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", 0)
    main.shutdown_event = asyncio.Event()

    async def exercise() -> None:
        await main._sleep_with_watchdog(7, 0, None)
        monkeypatch.setattr(main, "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", 1)
        main.shutdown_event.set()
        await main._sleep_with_watchdog(8, 0, None)

    asyncio.run(exercise())

    assert sleep_durations == [7]


def test_repeated_init_failures_obey_elapsed_fatal_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = CollectorRegistry()
    snapshot = SnapshotCollector()
    registry.register(snapshot)
    monkeypatch.setattr(main, "snapshot_collector", snapshot)
    monkeypatch.setattr(main, "get_shelly_credentials", lambda: (None, None))
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(main, "RECONNECT_BACKOFF_MAX_SECONDS", 0)
    monkeypatch.setattr(main, "EXIT_AFTER_CONSECUTIVE_INIT_FAILURES", 0)
    monkeypatch.setattr(main, "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", 5)
    clock = [0.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])

    class FailedInitialization:
        name = model = firmware_version = "device"

        @classmethod
        async def create(cls, session: Any, device: Any, options: Any) -> FailedInitialization:
            return cls()

        async def initialize(self) -> None:
            raise RuntimeError("init failure")

        async def shutdown(self) -> None:
            return None

    async def no_delay(seconds: float) -> None:
        clock[0] = 6.0
        return None

    monkeypatch.setattr(main, "RpcDevice", FailedInitialization)
    monkeypatch.setattr(main, "_sleep_until_shutdown", no_delay)
    main.shutdown_event = asyncio.Event()

    with pytest.raises(SystemExit) as error:
        asyncio.run(main.main_loop("shelly.local"))

    assert error.value.code == 1
    assert 'shelly_target_up{target="shelly.local"} 0.0' in generate_latest(registry).decode()
