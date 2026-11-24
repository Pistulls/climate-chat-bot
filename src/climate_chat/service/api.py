"""Request parsing and JSON responses for POST /api/chat (Design.md, Front end and API)."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Any

STYLES = ("match", "neutral")
PLATFORMS = ("x", "youtube", "facebook")

JSON_HEADERS = {"content-type": "application/json"}


class ApiError(Exception):
    """An error reply: HTTP status, a stable code for the UI and a human-readable message."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message

    def to_response(self) -> dict[str, Any]:
        return _response(self.status, {"error": self.code, "message": self.message})


@dataclass(frozen=True)
class ChatRequest:
    comment: str
    turnstile_token: str
    platform: str | None
    style: str


def unavailable() -> ApiError:
    """503: a dependency we can't do without (OpenRouter credit, Cloudflare) is unavailable."""
    return ApiError(503, "unavailable", "Sorry, I can't answer right now. Please try later.")


def upstream_error() -> ApiError:
    """502: a model call failed, or its output failed the checks after one retry."""
    return ApiError(
        502, "upstream_error", "Sorry, I couldn't write a sourced reply. Please try again."
    )


def ok_response(payload: dict[str, Any]) -> dict[str, Any]:
    return _response(200, payload)


def _response(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": JSON_HEADERS,
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _bad(message: str) -> ApiError:
    return ApiError(400, "bad_request", message)


def parse_request(body: str | None, *, max_chars: int) -> ChatRequest:
    """Validate the body. Free checks only: the length cap comes before the token check,
    and a missing token is a 403 without any call to Cloudflare."""
    try:
        data = json.loads(body or "")
    except json.JSONDecodeError:
        raise _bad("The request body must be JSON.") from None
    if not isinstance(data, dict):
        raise _bad("The request body must be a JSON object.")

    comment = data.get("comment")
    if not isinstance(comment, str) or not comment.strip():
        raise _bad("comment must be a non-empty string.")
    # NFC, so an accent typed as a separate combining mark counts once.
    comment = unicodedata.normalize("NFC", comment.strip())

    style = data.get("style") or "match"
    if style not in STYLES:
        raise _bad(f"style must be one of {', '.join(STYLES)}.")
    platform = data.get("platform") or None
    if platform is not None and platform not in PLATFORMS:
        raise _bad(f"platform must be one of {', '.join(PLATFORMS)}.")

    # len() counts code points, so an emoji or an accented letter is one character.
    if len(comment) > max_chars:
        raise ApiError(
            400, "comment_too_long", f"The comment must be {max_chars} characters or fewer."
        )

    token = data.get("turnstile_token")
    if not isinstance(token, str) or not token:
        raise ApiError(403, "turnstile_failed", "The bot check is missing. Please try again.")

    return ChatRequest(comment=comment, turnstile_token=token, platform=platform, style=style)
