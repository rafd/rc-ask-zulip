import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import db
from checkin_classifier import (
    DEFAULT_MAX_PARENT_CATEGORIES,
    classify_cached,
    consolidate_buckets,
)
from checkin_fetch import build_grouped

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 12 * 60 * 60  # 12 hours


def _seconds_since_snapshot() -> float | None:
    snap = db.get_snapshot()
    if snap is None:
        return None
    _, created_at = snap
    try:
        # Stored as naive ISO; treat as UTC.
        ts = datetime.fromisoformat(created_at).replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Could not parse snapshot timestamp %r; treating as stale", created_at)
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds()


def refresh_snapshot_once() -> None:
    """Build a fresh grouped snapshot and persist it. Synchronous; safe to run in a thread."""
    started = time.monotonic()
    zulip_site = os.environ.get("ZULIP_SITE", "")
    raw_grouped = build_grouped(zulip_site, classify_fn=classify_cached)
    raw_bucket_count = len(raw_grouped)
    grouped = consolidate_buckets(raw_grouped, DEFAULT_MAX_PARENT_CATEGORIES)
    db.put_snapshot(grouped)
    elapsed = time.monotonic() - started
    logger.info(
        "checkin snapshot refreshed in %.1fs (%d -> %d buckets, %d total entries)",
        elapsed,
        raw_bucket_count,
        len(grouped),
        sum(len(v) for v in grouped.values()),
    )


async def refresh_snapshot_loop(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
    """Run forever: refresh the check-in snapshot every interval_seconds.

    On startup, refreshes immediately if there is no snapshot or it is older
    than interval_seconds. Errors are logged but never crash the loop.
    """
    while True:
        age = _seconds_since_snapshot()
        if age is None or age >= interval_seconds:
            try:
                await asyncio.to_thread(refresh_snapshot_once)
            except Exception:
                logger.exception("checkin snapshot refresh failed; will retry next cycle")
            sleep_for = interval_seconds
        else:
            sleep_for = interval_seconds - age
            logger.info(
                "checkin snapshot is %.0fs old; next refresh in %.0fs", age, sleep_for
            )
        await asyncio.sleep(sleep_for)
