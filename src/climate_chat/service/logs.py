"""One DynamoDB item per request (Design.md, Request logs). Never the client IP."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from climate_chat.service.pipeline import PipelineResult, Trace


def _money(value: float) -> Decimal:
    # DynamoDB numbers come from Decimal; round away float noise first.
    return Decimal(str(round(value, 10)))


def log_item(
    *,
    comment: str,
    user_hash: str,
    trace: Trace,
    result: PipelineResult | None,
    error_code: str | None,
    latency_ms: int,
    now: datetime,
    ttl_days: int,
    request_id: str,
    subject: str | None = None,
    thread: str | None = None,
) -> dict[str, Any]:
    """`pk` is the UTC day and `sk` the time plus request id, so one day's requests are a
    single partition, in time order."""
    now = now.astimezone(UTC)
    calls = [
        {
            "role": role,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "reasoning_tokens": r.reasoning_tokens,
            "cost": _money(r.cost),
        }
        for role, r in trace.calls
    ]
    entry: dict[str, Any] = {
        "pk": f"day#{now:%Y-%m-%d}",
        "sk": f"{now:%Y-%m-%dT%H:%M:%S}.{now.microsecond // 1000:03d}Z#{request_id}",
        "expires_at": int((now + timedelta(days=ttl_days)).timestamp()),
        "comment": comment,
        "user_hash": user_hash,
        "cached": trace.cached,
        "outcome": result.outcome if result else f"error:{error_code}",
        "latency_ms": latency_ms,
        "calls": calls,
        "cost": sum((c["cost"] for c in calls), Decimal(0)),
    }
    if subject:
        entry["subject"] = subject
    if thread:
        entry["thread"] = thread
    if trace.claim is not None:
        entry["claim"] = trace.claim
    if trace.cards_category is not None:
        entry["cards_category"] = trace.cards_category
    if trace.failures:
        entry["failures"] = trace.failures
    return entry


def write_log(table: Any, item: dict[str, Any]) -> None:
    """Best effort: a failed log write is printed, never allowed to fail the reply."""
    try:
        table.put_item(Item=item)
    except Exception as e:
        print(f"log write failed: {type(e).__name__}: {e}")


# --- Reading, for the local logs page (service/local.py only, never the Lambda) ---


class BadCursor(ValueError):
    """A paging cursor that this module didn't issue."""


def _encode_cursor(day: date, start: dict[str, Any] | None) -> str:
    raw = json.dumps({"day": day.isoformat(), "start": start}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[date, dict[str, Any] | None]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
        day = date.fromisoformat(data["day"])
        start = data.get("start")
        if start is not None and not (isinstance(start, dict) and set(start) == {"pk", "sk"}):
            raise ValueError("bad start key")
        return day, start
    except (binascii.Error, ValueError, KeyError, TypeError) as e:
        raise BadCursor(str(e)) from e


def _plain(value: Any) -> Any:
    """DynamoDB numbers come back as Decimal; JSON wants int or float."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _public(item: dict[str, Any]) -> dict[str, Any]:
    time, _, request_id = item["sk"].partition("#")
    out = {k: _plain(v) for k, v in item.items() if k not in ("pk", "sk", "expires_at")}
    return {"time": time, "request_id": request_id, **out}


def read_logs(
    table: Any, *, today: date, days: int, limit: int, cursor: str | None
) -> dict[str, Any]:
    """One page of request logs, newest first. Each UTC day is its own partition, so this
    reads today's backwards, then the day before, and so on, no further back than `days`
    (the log TTL: older items are gone). `next` resumes where the page stopped, or is
    None when the window is exhausted. A page can end exactly on the last item, in which
    case the next one is empty."""
    day, start = _decode_cursor(cursor) if cursor else (today, None)
    oldest = today - timedelta(days=days - 1)
    items: list[dict[str, Any]] = []
    while len(items) < limit and day >= oldest:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": "pk = :pk",
            "ExpressionAttributeValues": {":pk": f"day#{day.isoformat()}"},
            "ScanIndexForward": False,
            "Limit": limit - len(items),
        }
        if start:
            kwargs["ExclusiveStartKey"] = start
        response = table.query(**kwargs)
        items.extend(_public(i) for i in response.get("Items", []))
        start = response.get("LastEvaluatedKey")
        if not start:
            day -= timedelta(days=1)
    more = day >= oldest
    return {"items": items, "next": _encode_cursor(day, start) if more else None}
