"""Daily S3 mirror of the `traces` collection.

APScheduler-driven; runs at 02:00 local time when `trace_s3_archive_enabled`.
Dumps yesterday's trace docs as JSONL to `s3://<bucket>/traces/YYYY-MM-DD/spans.jsonl`.
No-op when the flag is off. No-op when S3 is not configured (logs + returns).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config.settings import settings

logger = logging.getLogger(__name__)


def run_daily_archive(target_date: datetime | None = None) -> dict[str, Any]:
    """Archive one calendar day of traces to S3.

    Args:
        target_date: UTC date to archive (naive datetime OK). Defaults to
            yesterday (UTC) so that a 02:00 job captures the previous day.

    Returns:
        {"status": "skipped"|"ok"|"error", "count": int, "s3_key": str}
    """
    if not settings.trace_s3_archive_enabled:
        return {"status": "skipped", "reason": "trace_s3_archive_enabled=false"}
    bucket = settings.aws_default_bucket
    if not bucket:
        logger.warning("run_daily_archive: no aws_default_bucket configured; skipping")
        return {"status": "skipped", "reason": "no bucket configured"}

    if target_date is None:
        target_date = datetime.now(tz=timezone.utc) - timedelta(days=1)
    day = target_date.astimezone(timezone.utc).date()
    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    try:
        from src.service.database.connections.mongodb_connection import get_mongodb_client
        from src.service.s3 import get_s3_client

        client = get_mongodb_client()
        collection = client[settings.mongodb_db_name][settings.trace_mongodb_collection]
        cursor = collection.find(
            {"start_time": {"$gte": day_start, "$lt": day_end}},
            {"_id": 0},
        )
        lines = []
        count = 0
        for doc in cursor:
            lines.append(json.dumps(doc, default=str))
            count += 1
        body = "\n".join(lines).encode("utf-8")

        key = f"{settings.trace_s3_prefix.rstrip('/')}/{day.isoformat()}/spans.jsonl"
        s3 = get_s3_client()
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/x-ndjson")
        logger.info("run_daily_archive: wrote %d spans to s3://%s/%s", count, bucket, key)
        return {"status": "ok", "count": count, "s3_key": key}
    except Exception:
        logger.exception("run_daily_archive: failed")
        return {"status": "error", "count": 0, "s3_key": ""}
