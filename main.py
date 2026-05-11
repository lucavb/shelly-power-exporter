import asyncio
import contextlib
import logging
import signal
import sys
import time

import aiohttp
from aioshelly.common import ConnectionOptions
from aioshelly.rpc_device import RpcDevice
from prometheus_client import start_http_server

from collector import collect_metrics, reset_poll_failure_counter
from config import (
    EXIT_AFTER_CONSECUTIVE_INIT_FAILURES,
    EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS,
    METRICS_PORT,
    RECONNECT_AFTER_POLL_FAILURES,
    RECONNECT_BACKOFF_MAX_SECONDS,
    RECONNECT_BACKOFF_SECONDS,
    SCRAPE_INTERVAL,
    get_shelly_host,
    setup_logging,
)
from version import get_version

setup_logging()
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()


def _fatal_no_poll_success(start_monotonic: float, last_poll_success: float | None) -> None:
    limit = EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS
    if limit <= 0:
        return
    now = time.monotonic()
    reference = last_poll_success if last_poll_success is not None else start_monotonic
    if now - reference >= limit:
        logger.critical(
            "No successful poll within %d seconds; exiting for process restart",
            limit,
        )
        sys.exit(1)


async def _sleep_until_shutdown(seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)


async def main_loop(shelly_host: str) -> None:
    """Main loop: connect, poll, recycle connection on repeated failures."""
    options = ConnectionOptions(ip_address=shelly_host)
    start_monotonic = time.monotonic()
    last_poll_success: float | None = None
    reconnect_backoff = float(RECONNECT_BACKOFF_SECONDS)
    init_failures = 0
    device: RpcDevice | None = None

    async with aiohttp.ClientSession() as session:
        while not shutdown_event.is_set():
            if device is None:
                try:
                    logger.info("Connecting to Shelly device at %s", shelly_host)
                    device = await RpcDevice.create(session, None, options)
                    await device.initialize()
                except Exception as e:
                    init_failures += 1
                    logger.error("Failed to initialize Shelly device: %s", e)
                    if (
                        EXIT_AFTER_CONSECUTIVE_INIT_FAILURES > 0
                        and init_failures >= EXIT_AFTER_CONSECUTIVE_INIT_FAILURES
                    ):
                        logger.critical(
                            "Exiting after %d consecutive init failures",
                            init_failures,
                        )
                        sys.exit(1)
                    await _sleep_until_shutdown(reconnect_backoff)
                    reconnect_backoff = min(
                        reconnect_backoff * 2,
                        float(RECONNECT_BACKOFF_MAX_SECONDS),
                    )
                    continue

                init_failures = 0
                reconnect_backoff = float(RECONNECT_BACKOFF_SECONDS)
                reset_poll_failure_counter()
                logger.info(
                    "Connected to %s (Model: %s, FW: %s)",
                    device.name,
                    device.model,
                    device.firmware_version,
                )

            assert device is not None
            poll_result = await collect_metrics(device)
            _fatal_no_poll_success(start_monotonic, last_poll_success)

            if poll_result.ok:
                last_poll_success = time.monotonic()
            elif poll_result.recycle_connection:
                logger.warning(
                    "Recycling Shelly connection after %d consecutive poll failures (threshold %d)",
                    poll_result.consecutive_poll_failures,
                    RECONNECT_AFTER_POLL_FAILURES,
                )
                with contextlib.suppress(Exception):
                    await device.shutdown()
                device = None
                reset_poll_failure_counter()
                await _sleep_until_shutdown(float(RECONNECT_BACKOFF_SECONDS))
                continue

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=SCRAPE_INTERVAL)

            _fatal_no_poll_success(start_monotonic, last_poll_success)

        if device is not None:
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
    if RECONNECT_AFTER_POLL_FAILURES > 0:
        logger.info(
            "Reconnect after %d consecutive poll failures; backoff %ds–%ds",
            RECONNECT_AFTER_POLL_FAILURES,
            RECONNECT_BACKOFF_SECONDS,
            RECONNECT_BACKOFF_MAX_SECONDS,
        )
    if EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS > 0:
        logger.info(
            "Will exit if no successful poll for %ds",
            EXIT_AFTER_SECONDS_WITHOUT_POLL_SUCCESS,
        )
    if EXIT_AFTER_CONSECUTIVE_INIT_FAILURES > 0:
        logger.info(
            "Will exit after %d consecutive init failures",
            EXIT_AFTER_CONSECUTIVE_INIT_FAILURES,
        )

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
