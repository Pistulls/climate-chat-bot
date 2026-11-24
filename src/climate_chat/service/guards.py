"""Checks that run before any LLM call: client IP, Turnstile and the per-IP rate limit
(Design.md, Abuse protection), plus the hashed user id for the request logs."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from climate_chat.service.api import ApiError, unavailable

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
LOCAL_IP = "local"
TURNSTILE_ACTION = "chat"  # set by the UI's widget
MAX_TOKEN_CHARS = 2048  # Cloudflare's limit for a token


def client_ip(headers: dict[str, str], header_name: str) -> str:
    """The viewer IP from `CloudFront-Viewer-Address` (`ip:port`). The port is split off at
    the last colon, so IPv6 addresses, which contain colons, stay whole."""
    wanted = header_name.lower()
    value = next((v for k, v in headers.items() if k.lower() == wanted), "")
    if not value:
        return LOCAL_IP
    ip, _, _port = value.rpartition(":")
    return ip or value


def verify_turnstile(
    token: str,
    secret: str,
    remote_ip: str,
    *,
    hostnames: tuple[str, ...],
    action: str = TURNSTILE_ACTION,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 3.0,
) -> None:
    """Raise 403 unless Cloudflare accepts the token for one of `hostnames` and `action`
    (Design.md, Cloudflare Turnstile), and 503 if Cloudflare can't be asked: an outage
    there isn't the user's fault."""
    if len(token) > MAX_TOKEN_CHARS:
        raise _turnstile_failed()
    fields = {"secret": secret, "response": token}
    if remote_ip != LOCAL_IP:
        fields["remoteip"] = remote_ip
    request = urllib.request.Request(
        SITEVERIFY_URL, data=urllib.parse.urlencode(fields).encode(), method="POST"
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise unavailable()
            result = json.loads(response.read())
    except (OSError, ValueError) as e:  # URLError, HTTPError and timeouts are OSErrors
        raise unavailable() from e
    if result.get("success") is not True:
        raise _turnstile_failed()
    hostname = result.get("hostname")
    if not isinstance(hostname, str) or hostname.lower() not in hostnames:
        raise _turnstile_failed()
    # Cloudflare's test secret reports no action; only it sets result_with_testing_key.
    metadata = result.get("metadata")
    test_key = isinstance(metadata, dict) and metadata.get("result_with_testing_key") is True
    if result.get("action") != action and not (test_key and not result.get("action")):
        raise _turnstile_failed()


def _turnstile_failed() -> ApiError:
    return ApiError(403, "turnstile_failed", "The bot check failed. Please try again.")


class RateLimiter:
    """One DynamoDB counter per IP per window, incremented only while under the limit."""

    def __init__(self, client: Any, table: str, *, per_minute: int, per_day: int):
        self.client = client
        self.table = table
        self.per_minute = per_minute
        self.per_day = per_day

    def check(self, ip: str, now: datetime) -> None:
        minute = now.replace(second=0, microsecond=0)
        day = minute.replace(hour=0, minute=0)
        self._count(
            f"ip#{ip}#m#{minute:%Y-%m-%dT%H:%M}", self.per_minute, minute + timedelta(minutes=1)
        )
        self._count(f"ip#{ip}#d#{day:%Y-%m-%d}", self.per_day, day + timedelta(days=1))

    def _count(self, key: str, limit: int, window_end: datetime) -> None:
        try:
            self.client.update_item(
                TableName=self.table,
                Key={"pk": {"S": key}},
                UpdateExpression="ADD #c :one SET expires_at = if_not_exists(expires_at, :exp)",
                ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
                ExpressionAttributeNames={"#c": "count"},
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":limit": {"N": str(limit)},
                    ":exp": {"N": str(int(window_end.timestamp()))},
                },
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ApiError(
                    429, "rate_limited", "Too many requests. Please wait a little and try again."
                ) from None
            raise


def user_hash(key: str, ip: str, now: datetime) -> str:
    """HMAC-SHA256(key, "<YYYY-MM>|<ip>"), first 16 hex characters (Design.md, Request logs)."""
    message = f"{now:%Y-%m}|{ip}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()[:16]
