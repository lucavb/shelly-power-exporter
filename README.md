# Shelly Power Exporter

Prometheus exporter for Shelly Gen2+ devices with power metering using `aioshelly`.

## Supported Devices

Works with any Shelly device that uses the RPC API and has power metering:

- **Gen2**: Shelly Plus 1PM, Plus 2PM, Pro 1PM, Pro 2PM, Pro 4PM, Plus Plug S, etc.
- **Gen3**: Shelly Plus 1PM Gen3, Plus 2PM Gen3, Plug S Gen3, etc.
- **Gen4**: Future devices using the RPC API

Multi-channel devices (e.g., 2PM, 4PM) are automatically discovered and exposed with a `channel` label.

## Installation

### Using uv

```bash
uv sync
uv run shelly-power-exporter
```

### Using Docker

```bash
docker run -d \
  --name shelly-exporter \
  -p 9102:9102 \
  -e SHELLY_HOST=192.168.1.100 \
  ghcr.io/lucavb/shelly-power-exporter:latest
```

### Docker Compose

```yaml
services:
  shelly-exporter:
    image: ghcr.io/lucavb/shelly-power-exporter:latest
    ports:
      - "9102:9102"
    environment:
      - SHELLY_HOST=192.168.1.100
    restart: unless-stopped
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SHELLY_HOST` | _required_ | IP address of the Shelly device |
| `METRICS_PORT` | 9102 | Port for Prometheus metrics endpoint |
| `SCRAPE_INTERVAL` | 15 | Seconds between data fetches |
| `STALE_AFTER_FAILURES` | 3 | Reset instant metrics to 0 after N consecutive failures (0 = disable) |
| `DEBUG` | false | Enable debug logging |

## Metrics

All metrics are prefixed with `shelly_` and include a `device` label (MAC address). Per-channel metrics also include a `channel` label.

### Electrical Metrics (per channel)

* `shelly_switch_on`: Switch output state (1 = on, 0 = off)
* `shelly_power_watts`: Active power in watts
* `shelly_voltage_volts`: Voltage in volts
* `shelly_current_amperes`: Current in amperes
* `shelly_frequency_hertz`: Grid frequency in hertz
* `shelly_energy_watthours_total`: Total energy consumed in watt-hours
* `shelly_energy_returned_watthours_total`: Total energy returned in watt-hours
* `shelly_temperature_celsius`: Device/channel temperature in celsius

### Device Metrics

* `shelly_wifi_rssi_dbm`: WiFi signal strength in dBm
* `shelly_uptime_seconds`: Device uptime in seconds

### Exporter Metrics

* `shelly_up`: Device reachability status (1 = up, 0 = down)
* `shelly_info`: Device information labels (model, mac, firmware, name)

## Example Output

```prometheus
shelly_up{device="34CDB0775B2C"} 1
shelly_info_info{device="34CDB0775B2C",model="S3SW-002P16EU",firmware="1.7.1",name="shelly2pmg3-34cdb0775b2c"} 1
shelly_switch_on{channel="0",device="34CDB0775B2C"} 0
shelly_switch_on{channel="1",device="34CDB0775B2C"} 1
shelly_power_watts{channel="0",device="34CDB0775B2C"} 0
shelly_power_watts{channel="1",device="34CDB0775B2C"} 3.3
```

## Development

```bash
uv sync --dev
uv run ruff check .
uv run ruff format .
uv run pyright
```

## License

MIT
