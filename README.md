# Shelly Power Exporter

Prometheus exporter for Shelly Gen2+ devices with power metering using `aioshelly`.

## Supported Devices

Supports RPC status components `switch`, `pm1`, `em1`, `em1data`, `em`, and
`emdata` on compatible Gen2+ devices. Support is based on component payloads;
not every model or firmware has been tested on hardware. Devices using other
component types are not covered. Multi-channel switches are exposed with a
`channel` label.

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
| `METRICS_MAX_AGE_SECONDS` | 45 | Maximum age of measurement snapshots. When older, measurement and component-error series disappear; `0` disables expiry. Health, failure count, last-success timestamp, and last-attempt duration remain available. |
| `STALE_AFTER_FAILURES` | — | Deprecated and ignored. Set `METRICS_MAX_AGE_SECONDS` instead; this variable no longer sets freshness or resets measurements. |
| `SHELLY_USERNAME` | `admin` when a password is set | Shelly RPC username. Optional; if omitted while a password is configured, `admin` is used. A username without a password is invalid. |
| `SHELLY_PASSWORD` | — | Optional Shelly RPC password. The exporter does not log configured credentials. The RPC library can log raw authenticated frames at DEBUG, so its protocol logger is held at INFO even when exporter DEBUG is enabled. |
| `RECONNECT_AFTER_POLL_FAILURES` | 5 | After N consecutive failed polls, close the RPC connection and reconnect (0 = disable) |
| `RECONNECT_BACKOFF_SECONDS` | 2 | Initial backoff (seconds) after a failed `initialize()`; doubles up to the max |
| `RECONNECT_BACKOFF_MAX_SECONDS` | 120 | Cap for reconnect backoff after init failures |
| `EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS` | 0 | Exit with non-zero status if no successful poll for this many seconds (0 = never; use with Kubernetes restart) |
| `EXIT_AFTER_CONSECUTIVE_INIT_FAILURES` | 0 | Exit after this many failed `initialize()` attempts in a row (0 = never) |
| `DEBUG` | false | Enable debug logging |

For an authenticated device, inject `SHELLY_PASSWORD` via your deployment's
secret mechanism. For local use, prompt without echoing it:

```bash
read -rs SHELLY_PASSWORD
export SHELLY_PASSWORD SHELLY_HOST=192.168.1.100
uv run shelly-power-exporter
```

If your device uses a different username, set `SHELLY_USERNAME` as well.
Environment variables can be visible to other processes or deployment
administrators; use your platform's secret-management facilities where available.

### Connection recovery

If the Shelly RPC session gets into a bad state (for example repeated `Not connected` errors), the exporter recreates the device after `RECONNECT_AFTER_POLL_FAILURES` consecutive poll failures. Failed reconnects use exponential backoff between attempts.

To let the orchestrator restart the process when the device stays unreachable, set `EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS` and/or `EXIT_AFTER_CONSECUTIVE_INIT_FAILURES` to positive values.

## Metrics

Metrics are collected from a fresh `Shelly.GetStatus` RPC response and are prefixed with `shelly_`. Measurements are published as a snapshot: fields missing from a successful response are omitted, never fabricated as zero. After `METRICS_MAX_AGE_SECONDS`, measurement and component-error series disappear until the next successful poll. The default cache window is 45 seconds; zero disables time-based expiry.

Set the maximum age higher than `SCRAPE_INTERVAL` plus expected RPC latency to
avoid expiring healthy readings between polls.

Switch metrics retain the `device` (MAC) and `channel` labels. Meter metrics use distinct families and labels `device` (MAC), `component` (for example `pm1`, `em1`, `em1data`, `em`, or `emdata`), and component `id`. EM and EMData phase series additionally use `phase` (`a`, `b`, or `c`). Shelly's RPC energy fields are expressed in watt-hours. EMData `total_act` / `total_act_ret` are the device-reported aggregate Wh values; phase `*_total_act_energy` / `*_total_act_ret_energy` values are also exposed as Wh. The exporter passes these values through unchanged and does not sum phases to derive totals. This matches the Home Assistant Pro 3EM fixture. See [Shelly status handler](https://github.com/openWB/core/blob/master/packages/modules/devices/shelly/shelly/status_handler.py) and [Home Assistant Pro 3EM fixture](https://github.com/home-assistant/core/blob/566f087a2c064d8b9ec5b47a14ee23548216a1ad/tests/components/shelly/fixtures/pro_3em.json).

### Electrical Metrics (per channel)

* `shelly_switch_on`: Switch output state (1 = on, 0 = off)
* `shelly_power_watts`: Active power in watts
* `shelly_voltage_volts`: Voltage in volts
* `shelly_current_amperes`: Current in amperes
* `shelly_frequency_hertz`: Grid frequency in hertz
* `shelly_energy_watthours_total`: Total energy consumed in watt-hours
* `shelly_energy_returned_watthours_total`: Total energy returned in watt-hours
* `shelly_temperature_celsius`: Device/channel temperature in Celsius

### Device Metrics

* `shelly_wifi_rssi_dbm`: WiFi signal strength in dBm
* `shelly_uptime_seconds`: Device uptime in seconds

### Metering metrics

* `shelly_meter_power_watts`, `shelly_meter_voltage_volts`, `shelly_meter_current_amperes`, `shelly_meter_frequency_hertz`
* `shelly_meter_energy_watthours_total`, `shelly_meter_energy_returned_watthours_total`
* `shelly_meter_em_power_watts`, `shelly_meter_em_voltage_volts`, `shelly_meter_em_current_amperes`, `shelly_meter_em_frequency_hertz`
* `shelly_meter_em_energy_watthours_total`, `shelly_meter_em_energy_returned_watthours_total` (per-phase EM/EMData measurements)

The non-phase meter families cover PM1, EM1, EM1Data, EM, and EMData where the component provides that measurement. PM1's `meter_energy_watthours_total` is computed as `aenergy.total - ret_aenergy.total` only when both are present; `meter_energy_returned_watthours_total` reports `ret_aenergy.total` separately. Negative results are preserved (not clamped); when the returned counter is missing, consumed energy is omitted. Switch energy semantics remain unchanged. EM1Data reads `total_act_energy` and `total_act_ret_energy`; EMData reads the distinct `total_act` and `total_act_ret` fields. Phase families expose only reported phase values; no total is synthesized from phases. EMData phase energy values use `a_total_act_energy` / `a_total_act_ret_energy` (likewise phases `b` and `c`). These values pass through without conversion. Home Assistant marks these energy fields as `WATT_HOUR`, and its fixture shows the keys. See [Shelly status handler](https://github.com/openWB/core/blob/master/packages/modules/devices/shelly/shelly/status_handler.py), [Home Assistant sensor definitions](https://github.com/home-assistant/core/blob/566f087a2c064d8b9ec5b47a14ee23548216a1ad/homeassistant/components/shelly/sensor.py), and [Home Assistant Pro 3EM fixture](https://github.com/home-assistant/core/blob/566f087a2c064d8b9ec5b47a14ee23548216a1ad/tests/components/shelly/fixtures/pro_3em.json).

### Exporter Metrics

* `shelly_target_up{target}`: configured target reachability, including before the device MAC is known
* `shelly_up{device}`: device reachability once its MAC is known
* `shelly_info_info{device,model,firmware,name,mac}`: device information
* `shelly_last_poll_success_timestamp_seconds{target}`: Unix time of last successful poll
* `shelly_poll_duration_seconds{target}`: duration of most recent poll attempt, successful or failed
* `shelly_poll_failures_total{target}`: cumulative failed poll attempts since exporter start
* `shelly_device_error{device,component,id,error}`: bounded protection/error flags (`overtemp`, `overpower`, `overvoltage`, `undervoltage`, `overcurrent`); flags are independent per component and ID

On expiry, health changes to down and stale measurements/errors disappear. Last-success time, last-attempt duration, and cumulative failure count remain exposed. The endpoint also retains the Prometheus client's default process, platform, and Python garbage-collection metrics.

Example Prometheus alert expressions:

```promql
shelly_target_up == 0
time() - shelly_last_poll_success_timestamp_seconds > 60
shelly_device_error == 1
```

Use `up == 0` separately to detect an unreachable exporter; the last-success
series is absent until the first successful poll. Choose the freshness threshold
to suit your poll interval and `METRICS_MAX_AGE_SECONDS`.

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
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

## License

MIT
