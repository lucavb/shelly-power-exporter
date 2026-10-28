import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def status_fixtures() -> dict[str, dict[str, Any]]:
    return {path.stem: json.loads(path.read_text()) for path in FIXTURES.glob("*_status.json")}


def test_status_fixtures_are_valid_json_objects(status_fixtures: dict[str, dict[str, Any]]) -> None:
    assert {"switch_status", "pm1_status", "em1_status"} <= status_fixtures.keys()
    assert all(isinstance(status, dict) for status in status_fixtures.values())


def test_pm_and_em1_fixtures_preserve_component_ids_and_distinct_power_fields(
    status_fixtures: dict[str, dict[str, Any]],
) -> None:
    pm1 = status_fixtures["pm1_status"]
    em1 = status_fixtures["em1_status"]

    assert pm1["pm1:0"]["id"] == 0
    assert pm1["pm1:0"]["apower"] == 8.5
    assert "act_power" not in pm1["pm1:0"]
    assert em1["em1:2"]["id"] == 2
    assert em1["em1:2"]["act_power"] == 115.5
    assert "apower" not in em1["em1:2"]
    assert em1["em1data:2"]["total_act_energy"] == 25.0
    assert em1["em1data:2"]["total_act_ret_energy"] == 1.0


def test_pro_three_em_fixture_keeps_phases_and_aggregate_fields_separate() -> None:
    fixture = json.loads((FIXTURES / "pro_3em_minimal.json").read_text())
    em = fixture["em:0"]
    emdata = fixture["emdata:0"]

    assert [em[f"{phase}_act_power"] for phase in "abc"] == [253.2, 459.6, 115.5]
    assert em["total_act_power"] == 828.3
    assert [emdata[f"{phase}_total_act_energy"] for phase in "abc"] == [
        1200.0,
        2300.0,
        3400.0,
    ]
    assert emdata["total_act"] == 6900.0
