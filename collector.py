"""Poll Shelly RPC devices and atomically publish fresh snapshots."""

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aioshelly.rpc_device import RpcDevice

from config import RECONNECT_AFTER_POLL_FAILURES
from metrics import snapshot_collector

logger = logging.getLogger(__name__)
_consecutive_failures = 0
_total_failures = 0


def reset_poll_failure_counter() -> None:
    global _consecutive_failures
    _consecutive_failures = 0


@dataclass(frozen=True)
class PollResult:
    ok: bool
    recycle_connection: bool
    consecutive_poll_failures: int = 0


_DEVICE_ERRORS = ("overtemp", "overpower", "overvoltage", "undervoltage", "overcurrent")


def _device_errors(status: Mapping[str, Any]) -> dict[tuple[str, str, str], float]:
    """Expose recognized flags per component without merging across components."""
    result: dict[tuple[str, str, str], float] = {}
    for component, data in status.items():
        if not isinstance(data, Mapping):
            continue
        component_type, separator, component_id = component.partition(":")
        if not separator or component_type not in {
            "switch",
            "pm1",
            "em1",
            "em1data",
            "em",
            "emdata",
            "cover",
            "input",
        }:
            continue
        for error in _DEVICE_ERRORS:
            result[(component_type, component_id, error)] = 0.0
        errors = data.get("errors", [])
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, str) and error.lower() in _DEVICE_ERRORS:
                    result[(component_type, component_id, error.lower())] = 1.0
        for error in _DEVICE_ERRORS:
            if data.get(error) is True:
                result[(component_type, component_id, error)] = 1.0
    return result


async def collect_metrics(device: RpcDevice, target: str | None = None) -> PollResult:
    """Fetch one fresh GetStatus response (not poll()'s merged top-level status)."""
    global _consecutive_failures, _total_failures
    target = target if target is not None else str(device.ip_address)
    started = time.monotonic()
    try:
        previous_mac = snapshot_collector.get_device_mac(target)
    except Exception:
        previous_mac = None
    try:
        response = await device.call_rpc("Shelly.GetStatus")
        status = response.get("result", response) if isinstance(response, Mapping) else None
        if not isinstance(status, Mapping):
            raise ValueError("Shelly.GetStatus response is not a status object")
        mac = status.get("sys", {}).get("mac") or previous_mac
        _consecutive_failures = 0
        now = time.time()
        info = (
            {
                "model": str(device.model or "unknown"),
                "firmware": str(device.firmware_version or "unknown"),
                "name": str(device.name or "unknown"),
                "mac": str(mac),
            }
            if mac is not None
            else {}
        )
        snapshot_collector.set_success(
            target,
            str(mac) if mac is not None else None,
            status,
            info,
            now,
            time.monotonic() - started,
            _device_errors(status) if mac is not None else {},
            _total_failures,
        )
        logger.debug("Updated metrics for device %s", mac)
        return PollResult(ok=True, recycle_connection=False)
    except Exception as error:
        _consecutive_failures += 1
        logger.error(
            "Error polling device %s (failure %d; %s)",
            target,
            _consecutive_failures,
            type(error).__name__,
        )
        _total_failures += 1
        snapshot_collector.set_health(
            target,
            False,
            previous_mac,
            failure_count=_total_failures,
            duration=time.monotonic() - started,
        )
        recycle = (
            RECONNECT_AFTER_POLL_FAILURES > 0
            and _consecutive_failures >= RECONNECT_AFTER_POLL_FAILURES
        )
        return PollResult(False, recycle, _consecutive_failures)
