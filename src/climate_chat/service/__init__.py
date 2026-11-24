"""The /api/chat service (plan 03). `handler` is the Lambda entry point."""

from __future__ import annotations

from typing import Any

_app = None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Builds the app once per Lambda container, then reuses it across requests."""
    global _app
    if _app is None:
        from climate_chat.service.app import build_app

        _app = build_app()
    return _app.handle(event, context)
