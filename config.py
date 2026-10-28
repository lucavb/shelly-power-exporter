import logging
import os


def setup_logging() -> logging.Logger:
    log_level = (
        logging.DEBUG if os.environ.get("DEBUG", "").lower() in ("1", "true") else logging.INFO
    )
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # aioshelly logs raw RPC frames at DEBUG; authenticated frames can include a
    # digest Authorization value. Keep that protocol logger out of DEBUG mode.
    logging.getLogger("aioshelly.rpc_device.wsrpc").setLevel(logging.INFO)
    return logging.getLogger(__name__)


SHELLY_HOST = os.environ.get("SHELLY_HOST")
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9102"))
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "15"))
# Deprecated and intentionally ignored. Use METRICS_MAX_AGE_SECONDS for time-based expiry.
if "STALE_AFTER_FAILURES" in os.environ:
    logging.getLogger(__name__).warning(
        "STALE_AFTER_FAILURES is deprecated and ignored; use METRICS_MAX_AGE_SECONDS"
    )
METRICS_MAX_AGE_SECONDS = int(os.environ.get("METRICS_MAX_AGE_SECONDS", "45"))
if METRICS_MAX_AGE_SECONDS < 0:
    raise ValueError("METRICS_MAX_AGE_SECONDS must be non-negative")
SHELLY_USERNAME = os.environ.get("SHELLY_USERNAME")
SHELLY_PASSWORD = os.environ.get("SHELLY_PASSWORD")


def get_shelly_credentials() -> tuple[str | None, str | None]:
    """Return credentials; a password alone uses Shelly's default admin username."""
    if SHELLY_USERNAME and not SHELLY_PASSWORD:
        raise ValueError("SHELLY_USERNAME requires SHELLY_PASSWORD")
    if not SHELLY_PASSWORD:
        return None, None
    return SHELLY_USERNAME or "admin", SHELLY_PASSWORD


# After this many consecutive failed polls, shut down RpcDevice and reconnect (0 = never).
RECONNECT_AFTER_POLL_FAILURES = int(os.environ.get("RECONNECT_AFTER_POLL_FAILURES", "5"))
# Exponential backoff between reconnect attempts (seconds).
RECONNECT_BACKOFF_SECONDS = int(os.environ.get("RECONNECT_BACKOFF_SECONDS", "2"))
RECONNECT_BACKOFF_MAX_SECONDS = int(os.environ.get("RECONNECT_BACKOFF_MAX_SECONDS", "120"))

# Exit non-zero if there has been no successful poll for this many seconds (0 = never).
EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS = int(
    os.environ.get("EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS", "0")
)
# Exit non-zero after this many consecutive failed initialize() attempts (0 = never).
EXIT_AFTER_CONSECUTIVE_INIT_FAILURES = int(
    os.environ.get("EXIT_AFTER_CONSECUTIVE_INIT_FAILURES", "0")
)


def get_shelly_host() -> str | None:
    return SHELLY_HOST
