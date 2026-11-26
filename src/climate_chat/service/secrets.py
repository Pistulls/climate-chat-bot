"""Secrets for the service: from .env locally, from SSM in the Lambda.

SSM values are cached in memory for 5 minutes, so a rotated key is picked up without a
deploy (Design.md, Secrets).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from climate_chat.config import ServiceSettings

TTL_SECONDS = 300


class SecretStore:
    def __init__(
        self,
        settings: ServiceSettings,
        ssm_client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._settings = settings
        self._ssm = ssm_client
        self._clock = clock
        self._cache: dict[str, tuple[str, float]] = {}

    def openrouter_key(self) -> str:
        s = self._settings
        return s.openrouter_api_key or self._from_ssm(s.openrouter_key_param)

    def turnstile_secret(self) -> str:
        s = self._settings
        return s.turnstile_secret_key or self._from_ssm(s.turnstile_secret_param)

    def log_hash_key(self) -> str:
        s = self._settings
        return s.log_hash_key or self._from_ssm(s.log_hash_key_param)

    def admin_key(self) -> str:
        """The key for GET /api/logs. SSM holds a placeholder until it is set."""
        s = self._settings
        return s.admin_key or self._from_ssm(s.admin_key_param)

    def _from_ssm(self, name: str) -> str:
        cached = self._cache.get(name)
        if cached and self._clock() - cached[1] < TTL_SECONDS:
            return cached[0]
        if self._ssm is None:
            self._ssm = self._settings.base.aws_client("ssm")
        value = self._ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
        self._cache[name] = (value, self._clock())
        return value
