import logging
from dataclasses import dataclass

from aioshelly.rpc_device import RpcDevice

from config import RECONNECT_AFTER_POLL_FAILURES, STALE_AFTER_FAILURES
from metrics import (
    register_device_channel,
    reset_instant_metrics,
    shelly_current_amperes,
    shelly_energy_returned_watthours_total,
    shelly_energy_watthours_total,
    shelly_frequency_hertz,
    shelly_info,
    shelly_power_watts,
    shelly_switch_on,
    shelly_temperature_celsius,
    shelly_up,
    shelly_uptime_seconds,
    shelly_voltage_volts,
    shelly_wifi_rssi_dbm,
)

logger = logging.getLogger(__name__)

_consecutive_failures = 0


def reset_poll_failure_counter() -> None:
    """Clear consecutive poll failure count (call after a new connection is established)."""
    global _consecutive_failures
    _consecutive_failures = 0


@dataclass(frozen=True)
class PollResult:
    """Outcome of a single poll cycle."""

    ok: bool
    recycle_connection: bool
    consecutive_poll_failures: int = 0


async def collect_metrics(device: RpcDevice) -> PollResult:
    """Poll device and update Prometheus metrics."""
    global _consecutive_failures

    # Get MAC address from status if available, otherwise use hostname as fallback
    mac = device.status.get("sys", {}).get("mac") or device.hostname

    try:
        await device.poll()
        _consecutive_failures = 0
        # Update MAC if it changed or was missing
        mac = device.status.get("sys", {}).get("mac") or device.hostname
        shelly_up.labels(device=mac).set(1)
    except Exception as e:
        _consecutive_failures += 1
        logger.error(
            "Error polling device %s (failure %d/%d): %s",
            device.ip_address,
            _consecutive_failures,
            STALE_AFTER_FAILURES,
            e,
        )
        shelly_up.labels(device=mac).set(0)

        if STALE_AFTER_FAILURES > 0 and _consecutive_failures >= STALE_AFTER_FAILURES:
            logger.warning("Resetting instant metrics after %d failures", _consecutive_failures)
            reset_instant_metrics(mac)

        recycle = (
            RECONNECT_AFTER_POLL_FAILURES > 0
            and _consecutive_failures >= RECONNECT_AFTER_POLL_FAILURES
        )
        return PollResult(
            ok=False,
            recycle_connection=recycle,
            consecutive_poll_failures=_consecutive_failures,
        )

    # Update metrics from device status
    status = device.status

    # Device Info
    shelly_info.labels(device=mac).info(
        {
            "model": device.model,
            "firmware": device.firmware_version,
            "name": device.name or "unknown",
            "mac": mac,
        }
    )

    # WiFi Data
    wifi = status.get("wifi", {})
    if wifi:
        shelly_wifi_rssi_dbm.labels(device=mac).set(wifi.get("rssi", 0))

    # System Data
    sys_status = status.get("sys", {})
    if sys_status:
        shelly_uptime_seconds.labels(device=mac).set(sys_status.get("uptime", 0))

    # Iterate over all components in status
    for key, data in status.items():
        # Handle all switches (switch:0, switch:1, etc.)
        if key.startswith("switch:"):
            try:
                channel = key.split(":")[1]
                register_device_channel(mac, channel)

                labels = {"device": mac, "channel": channel}
                shelly_switch_on.labels(**labels).set(1 if data.get("output") else 0)
                shelly_power_watts.labels(**labels).set(data.get("apower", 0))
                shelly_voltage_volts.labels(**labels).set(data.get("voltage", 0))
                shelly_current_amperes.labels(**labels).set(data.get("current", 0))
                shelly_frequency_hertz.labels(**labels).set(data.get("freq", 0))

                aenergy = data.get("aenergy", {})
                if aenergy:
                    shelly_energy_watthours_total.labels(**labels).set(aenergy.get("total", 0))

                ret_aenergy = data.get("ret_aenergy", {})
                if ret_aenergy:
                    shelly_energy_returned_watthours_total.labels(**labels).set(
                        ret_aenergy.get("total", 0)
                    )

                temp = data.get("temperature", {})
                if temp:
                    shelly_temperature_celsius.labels(**labels).set(temp.get("tC", 0))
            except (IndexError, ValueError) as e:
                logger.error("Error parsing channel from key %s: %s", key, e)

    logger.debug("Updated metrics for device %s", mac)
    return PollResult(ok=True, recycle_connection=False, consecutive_poll_failures=0)
