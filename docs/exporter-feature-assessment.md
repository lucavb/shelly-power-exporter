# Exporter feature assessment

Research date: 2026-10-28. Sources: Shelly documentation located with
taia-web-search, Prometheus documentation and aioshelly source fetched through
GitHub MCP, and this repository. Shelly documentation was available via
search-grounded extracts, not direct page fetches; verify against the target
device and firmware before implementation.

## Implementation research: actual integrations

- [aioshelly 14.0.1](https://github.com/home-assistant-libs/aioshelly/blob/14.0.1/aioshelly/rpc_device/device.py)
  installs RPC authentication from connection options after reading device
  information. Its `poll()` uses `self._status.update(status)`: missing top-level
  components can therefore remain cached even after a successful poll. A fresh
  `Shelly.GetStatus` response is needed to reliably remove disappeared components.
- [Home Assistant's Pro 3EM fixture](https://github.com/home-assistant/core/blob/566f087a2c064d8b9ec5b47a14ee23548216a1ad/tests/components/shelly/fixtures/pro_3em.json)
  has `em:0` phase measurements and `emdata:0` phase and aggregate energy.
  [EDDIE's integration](https://github.com/eddie-energy/eddie/blob/main/aiida/src/main/java/energy/eddie/aiida/adapters/datasource/shelly/transformer/ShellyComponent.java)
  separately models `em`, `em1`, `emdata`, and `em1data` component indices.
- [openWB](https://github.com/openWB/core/blob/master/packages/modules/devices/shelly/shelly/status_handler.py)
  reads `pm1:0.apower` for the Mini PM and `em1:0.act_power` for an EM1 meter.
  [OpenEMS](https://github.com/OpenEMS/openems/blob/develop/io.openems.edge.io.shelly/src/io/openems/edge/io/shelly/shellypluspmmini/IoShellyPlusPmMiniImpl.java)
  also reads `pm1:0` from `Shelly.GetStatus`. These two components require
  different power field names.
- [openHAB device-profile tests](https://github.com/openhab/openhab-addons/blob/main/bundles/org.openhab.binding.shelly/src/test/java/org/openhab/binding/shelly/internal/api2/Shelly2GetDeviceProfileTest.java)
  distinguish one-, two-, and three-component EM1 devices. A component index
  is not automatically a physical phase; its meaning depends on device/profile.
- [meloos/shelly-prometheus-exporter](https://github.com/meloos/shelly-prometheus-exporter/blob/main/shelly_exporter/collector.py)
  uses per-scrape metric families, a health metric and optional credentials;
  it handles switches rather than proving EM-family support.

The exporter covers core measurements for one RPC device whose data appears in
`switch:N` components. It is not feature-complete for all RPC power meters as
claimed in `README.md`: `collector.py` processes switch components only.

## Priorities

1. **Fix energy meaning and missing/stale data.** Shelly's
   [switch documentation](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch/)
   says energy in `ret_aenergy` is also added to `aenergy`. The exporter calls
   `aenergy.total` consumed energy, which can mislead when exporting power;
   confirm the behavior for the device and firmware before changing the metric.
   `collector.py` also substitutes zero for some absent fields; `metrics.py`
   resets instant values to zero after failures while retaining other values.
   Prefer explicit unavailable/freshness semantics and test these cases.
2. **Support authenticated devices.** Shelly's
   [authentication documentation](https://shelly-api-docs.shelly.cloud/gen2/General/Authentication/)
   describes digest authentication. This exporter passes only the host to
   `ConnectionOptions` (`main.py`); upstream
   [aioshelly options](https://github.com/home-assistant-libs/aioshelly/blob/main/aioshelly/common.py)
   accept username and password. Expose credentials safely and validate with
   the pinned dependency and a protected device; upstream main is not proof of
   compatibility with every pinned version.
3. **Add metering-only components as needed.** Shelly documents
   [PM1](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/PM1/),
   [EM](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM/),
   [EM1](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM1/)
   and [EMData](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EMData/).
   They expose power or energy outside `switch:N`. Add models supported by
   representative fixtures or hardware; design bounded phase labels and avoid
   mixing phase totals into the same metric as individual phases.
4. **Improve error visibility and recovery tests.** Shelly switch status
   documents error flags such as `overtemp` and `overpower`; expose bounded
   device error states where supported. Add tests for initialization failures,
   reconnects, disappearing fields and `shelly_up` before the first poll.
   A last-success timestamp as a metric value can make cached data age visible.
5. **Consider extra electrical measurements.** Where supported, power factor
   and apparent power can be useful for electrical diagnostics; they should
   remain optional and absent when unsupported. See the PM1 and EM sources.

## Prometheus considerations

The [Prometheus exporter guidelines](https://github.com/prometheus/docs/blob/main/docs/instrumenting/writing_exporters.md)
recommend synchronous collection on scrape, new metric families rather than
persistently updated global series, and either a failed scrape or an exporter
health gauge for target failures. This exporter instead caches periodic polls;
redesigning it may affect device load and timeouts, so documenting freshness and
expiring unavailable data is a smaller alternative. Prometheus sample
timestamps are distinct from exposing last-success time as a metric value.

The same guidelines reserve `_total` for counters; the existing energy metrics
are gauges (`metrics.py`). Review device reset behavior, counter exposition,
query compatibility and migration before changing names or types. Counter
resets are expected and can be handled by Prometheus rate calculations; do not
assume a decrease alone makes a cumulative reading a gauge.

The guidance generally prefers one exporter per target and describes a
multi-target pattern for black-box devices. One process per Shelly already
works; multi-target support is optional, not a prerequisite for completeness.
