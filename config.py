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


def get_shelly_host() -> str | None:
    return SHELLY_HOST
