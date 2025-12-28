from prometheus_client import Gauge, Info

# Namespace for all metrics
NAMESPACE = "shelly"

# Device reachability
shelly_up = Gauge(
    "up",
    "Device reachability status (1 = up, 0 = down)",
    ["device"],
    namespace=NAMESPACE,
)

# Device information
shelly_info = Info(
    "info",
    "Device information labels",
    ["device"],
    namespace=NAMESPACE,
)

# Electrical metrics (Per Channel)
shelly_switch_on = Gauge(
    "switch_on",
    "Switch output state (1 = on, 0 = off)",
    ["device", "channel"],
    namespace=NAMESPACE,
)
shelly_power_watts = Gauge(
    "power_watts",
    "Active power in watts",
    ["device", "channel"],
    namespace=NAMESPACE,
)
shelly_voltage_volts = Gauge(
    "voltage_volts",
    "Voltage in volts",
    ["device", "channel"],
    namespace=NAMESPACE,
)
shelly_current_amperes = Gauge(
    "current_amperes",
    "Current in amperes",
    ["device", "channel"],
    namespace=NAMESPACE,
)
shelly_frequency_hertz = Gauge(
    "frequency_hertz",
    "Grid frequency in hertz",
    ["device", "channel"],
    namespace=NAMESPACE,
)
shelly_energy_watthours_total = Gauge(
    "energy_watthours_total",
    "Total energy consumed in watt-hours",
    ["device", "channel"],
    namespace=NAMESPACE,
)
shelly_energy_returned_watthours_total = Gauge(
    "energy_returned_watthours_total",
    "Total energy returned in watt-hours",
    ["device", "channel"],
    namespace=NAMESPACE,
)
shelly_temperature_celsius = Gauge(
    "temperature_celsius",
    "Device temperature in celsius",
    ["device", "channel"],
    namespace=NAMESPACE,
)

# Device metrics (Device Level)
shelly_wifi_rssi_dbm = Gauge(
    "wifi_rssi_dbm",
    "WiFi signal strength in dBm",
    ["device"],
    namespace=NAMESPACE,
)
shelly_uptime_seconds = Gauge(
    "uptime_seconds",
    "Device uptime in seconds",
    ["device"],
    namespace=NAMESPACE,
)

# Track known channels per device for resetting
_known_device_channels: dict[str, set[str]] = {}


def register_device_channel(device_mac: str, channel: str) -> None:
    """Register a channel for a device to track it for resets."""
    if device_mac not in _known_device_channels:
        _known_device_channels[device_mac] = set()
    _known_device_channels[device_mac].add(channel)


def reset_instant_metrics(device_mac: str) -> None:
    """Reset power/voltage/current metrics to 0 for all known channels of a device."""
    channels = _known_device_channels.get(device_mac, set())
    for channel in channels:
        shelly_switch_on.labels(device=device_mac, channel=channel).set(0)
        shelly_power_watts.labels(device=device_mac, channel=channel).set(0)
        shelly_voltage_volts.labels(device=device_mac, channel=channel).set(0)
        shelly_current_amperes.labels(device=device_mac, channel=channel).set(0)
        shelly_frequency_hertz.labels(device=device_mac, channel=channel).set(0)
        shelly_temperature_celsius.labels(device=device_mac, channel=channel).set(0)

    # Reset device-level status that can be zeroed
    shelly_wifi_rssi_dbm.labels(device=device_mac).set(0)
