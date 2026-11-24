"""One DynamoDB item per request (Design.md, Request logs). Never the client IP."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    if trace.claim is not None:
        entry["claim"] = trace.claim
    if trace.cards_category is not None:
        entry["cards_category"] = trace.cards_category
    return entry


def write_log(table: Any, item: dict[str, Any]) -> None:
    """Best effort: a failed log write is printed, never allowed to fail the reply."""
    try:
        table.put_item(Item=item)
    except Exception as e:
        print(f"log write failed: {type(e).__name__}: {e}")
