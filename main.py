import asyncio
import contextlib
import logging
import signal
import sys

import aiohttp
from aioshelly.common import ConnectionOptions
from aioshelly.rpc_device import RpcDevice
from prometheus_client import start_http_server

from collector import collect_metrics
from config import METRICS_PORT, SCRAPE_INTERVAL, get_shelly_host, setup_logging
from version import get_version

setup_logging()
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()


async def main_loop(shelly_host: str) -> None:
    """Main loop for polling Shelly device."""
    options = ConnectionOptions(ip_address=shelly_host)

    async with aiohttp.ClientSession() as session:
        logger.info("Connecting to Shelly device at %s", shelly_host)
        try:
            device = await RpcDevice.create(session, None, options)
            await device.initialize()
        except Exception as e:
            logger.error("Failed to initialize Shelly device: %s", e)
            return

        logger.info(
            "Connected to %s (Model: %s, FW: %s)",
            device.name,
            device.model,
            device.firmware_version,
        )

        while not shutdown_event.is_set():
            await collect_metrics(device)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=SCRAPE_INTERVAL)

        await device.shutdown()
        logger.info("Device connection shut down")


def main() -> None:
    """Entry point for the exporter."""
    shelly_host = get_shelly_host()
    if not shelly_host:
        logger.error("SHELLY_HOST environment variable is required")
        sys.exit(1)

    logger.info("Starting Shelly Plug Exporter v%s", get_version())
    logger.info("Shelly Host: %s", shelly_host)
    logger.info("Metrics Port: %d", METRICS_PORT)
    logger.info("Scrape Interval: %ds", SCRAPE_INTERVAL)

    start_http_server(METRICS_PORT)
    logger.info("Prometheus metrics server started on port %d", METRICS_PORT)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown_handler(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        loop.call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        loop.run_until_complete(main_loop(shelly_host))
    finally:
        loop.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
