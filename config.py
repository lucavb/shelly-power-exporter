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
    return logging.getLogger(__name__)


SHELLY_HOST = os.environ.get("SHELLY_HOST")
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9102"))
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "15"))
STALE_AFTER_FAILURES = int(os.environ.get("STALE_AFTER_FAILURES", "3"))

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
