import importlib
from collections.abc import Iterator

import pytest

import config

_CONFIG_ENV_VARS = (
    "SCRAPE_INTERVAL",
    "METRICS_MAX_AGE_SECONDS",
    "RECONNECT_AFTER_POLL_FAILURES",
    "RECONNECT_BACKOFF_SECONDS",
    "RECONNECT_BACKOFF_MAX_SECONDS",
    "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS",
    "EXIT_AFTER_CONSECUTIVE_INIT_FAILURES",
)


@pytest.fixture
def restore_config_module() -> Iterator[None]:
    original_values = {name: getattr(config, name) for name in _CONFIG_ENV_VARS}
    yield
    for name, value in original_values.items():
        setattr(config, name, value)


def load_config_with_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for variable in _CONFIG_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)
    for variable, value in values.items():
        monkeypatch.setenv(variable, value)
    importlib.reload(config)


def test_defaults_and_zero_disabled_thresholds_are_valid(
    monkeypatch: pytest.MonkeyPatch, restore_config_module: None
) -> None:
    load_config_with_env(
        monkeypatch,
        RECONNECT_AFTER_POLL_FAILURES="0",
        EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS="0",
        EXIT_AFTER_CONSECUTIVE_INIT_FAILURES="0",
    )

    assert config.SCRAPE_INTERVAL == 15
    assert config.RECONNECT_BACKOFF_SECONDS == 2
    assert config.RECONNECT_BACKOFF_MAX_SECONDS == 120
    assert config.RECONNECT_AFTER_POLL_FAILURES == 0
    assert config.EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS == 0
    assert config.EXIT_AFTER_CONSECUTIVE_INIT_FAILURES == 0


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("SCRAPE_INTERVAL", "0", "SCRAPE_INTERVAL must be greater than zero"),
        ("SCRAPE_INTERVAL", "-1", "SCRAPE_INTERVAL must be greater than zero"),
        (
            "RECONNECT_BACKOFF_SECONDS",
            "0",
            "RECONNECT_BACKOFF_SECONDS must be greater than zero",
        ),
        (
            "RECONNECT_BACKOFF_SECONDS",
            "-1",
            "RECONNECT_BACKOFF_SECONDS must be greater than zero",
        ),
        (
            "RECONNECT_BACKOFF_MAX_SECONDS",
            "0",
            "RECONNECT_BACKOFF_MAX_SECONDS must be greater than zero",
        ),
        (
            "RECONNECT_BACKOFF_MAX_SECONDS",
            "-1",
            "RECONNECT_BACKOFF_MAX_SECONDS must be greater than zero",
        ),
        (
            "RECONNECT_AFTER_POLL_FAILURES",
            "-1",
            "RECONNECT_AFTER_POLL_FAILURES must be non-negative",
        ),
        (
            "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS",
            "-1",
            "EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS must be non-negative",
        ),
        (
            "EXIT_AFTER_CONSECUTIVE_INIT_FAILURES",
            "-1",
            "EXIT_AFTER_CONSECUTIVE_INIT_FAILURES must be non-negative",
        ),
    ],
)
def test_invalid_timing_and_threshold_values_fail_early(
    monkeypatch: pytest.MonkeyPatch,
    restore_config_module: None,
    variable: str,
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        load_config_with_env(monkeypatch, **{variable: value})


@pytest.mark.parametrize(
    ("initial", "maximum"),
    [("3", "2"), ("120", "2")],
)
def test_reconnect_backoff_initial_cannot_exceed_maximum(
    monkeypatch: pytest.MonkeyPatch,
    restore_config_module: None,
    initial: str,
    maximum: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="must be less than or equal to",
    ):
        load_config_with_env(
            monkeypatch,
            RECONNECT_BACKOFF_SECONDS=initial,
            RECONNECT_BACKOFF_MAX_SECONDS=maximum,
        )


def test_valid_timing_boundaries_and_equal_backoffs_are_accepted(
    monkeypatch: pytest.MonkeyPatch, restore_config_module: None
) -> None:
    load_config_with_env(
        monkeypatch,
        SCRAPE_INTERVAL="1",
        RECONNECT_AFTER_POLL_FAILURES="1",
        RECONNECT_BACKOFF_SECONDS="1",
        RECONNECT_BACKOFF_MAX_SECONDS="1",
        EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS="1",
        EXIT_AFTER_CONSECUTIVE_INIT_FAILURES="1",
    )

    assert config.SCRAPE_INTERVAL == 1
    assert config.RECONNECT_AFTER_POLL_FAILURES == 1
    assert config.RECONNECT_BACKOFF_SECONDS == config.RECONNECT_BACKOFF_MAX_SECONDS == 1
    assert config.EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS == 1
    assert config.EXIT_AFTER_CONSECUTIVE_INIT_FAILURES == 1
