pro_3em_minimal.json contains a minimal excerpt adapted from the Home Assistant
Core Shelly Pro 3EM fixture at
https://github.com/home-assistant/core/blob/566f087a2c064d8b9ec5b47a14ee23548216a1ad/tests/components/shelly/fixtures/pro_3em.json
Copyright the Home Assistant contributors; distributed under the repository's
license. Fields omitted from the original fixture are not needed by these tests.

switch_status.json, pm1_status.json, and em1_status.json are small hand-authored
representative status snippets for the respective Shelly component schemas; they
are not copied from third-party fixture data.

The PM1 power field (`pm1:0.apower`) and EM1 power field (`em1:2.act_power`)
follow the component schemas consumed by openWB:
https://github.com/openWB/core/blob/master/packages/modules/devices/shelly/shelly/status_handler.py
These examples are independently authored and contain no copied fixture payload.
