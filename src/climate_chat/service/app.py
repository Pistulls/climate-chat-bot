"""The Lambda request handler: routing, the pre-LLM checks in order, logging.

`App` takes its collaborators as arguments so tests can pass fakes; `build_app()` wires up
the real ones from settings.
"""

from __future__ import annotations

import base64
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from climate_chat.config import ServiceSettings, load_service_settings
from climate_chat.service.api import ApiError, ok_response, parse_request
from climate_chat.service.guards import RateLimiter, client_ip, user_hash
from climate_chat.service.guards import verify_turnstile as real_verify_turnstile
from climate_chat.service.logs import log_item, write_log
from climate_chat.service.pipeline import Pipeline, PipelineResult, Trace
from climate_chat.service.secrets import SecretStore

CHAT_PATH = "/api/chat"
SMOKE_USER = "smoke"


class _Secrets(Protocol):
    def openrouter_key(self) -> str: ...
    def turnstile_secret(self) -> str: ...
    def log_hash_key(self) -> str: ...


class _Pipeline(Protocol):
    def run(
        self, comment: str, style: str, platform: str | None, trace: Trace
    ) -> PipelineResult: ...


def _internal() -> ApiError:
    return ApiError(500, "internal", "Sorry, something went wrong. Please try again.")


def _payload(result: PipelineResult) -> dict[str, Any]:
    return {
        "reply": result.reply,
        "citations": result.citations,
        "fallacy": result.fallacy,
        "cached": result.cached,
    }


class App:
    def __init__(
        self,
        *,
        settings: ServiceSettings,
        secrets: _Secrets,
        pipeline_factory: Callable[[str], _Pipeline],
        rate_limiter: Any,
        log_table: Any,
        verify_turnstile: Callable[[str, str, str], None] = real_verify_turnstile,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.settings = settings
        self.secrets = secrets
        self.pipeline_factory = pipeline_factory
        self.rate_limiter = rate_limiter
        self.log_table = log_table
        self.verify_turnstile = verify_turnstile
        self.now = now
        self._pipeline: tuple[str, _Pipeline] | None = None

    def pipeline(self) -> _Pipeline:
        """Built on first use and rebuilt when the OpenRouter key changes, so a rotated key
        is picked up within the secret cache window without a deploy."""
        key = self.secrets.openrouter_key()
        if self._pipeline is None or self._pipeline[0] != key:
            self._pipeline = (key, self.pipeline_factory(key))
        return self._pipeline[1]

    def handle(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        http = (event.get("requestContext") or {}).get("http")
        if http is not None:
            if event.get("rawPath") != CHAT_PATH:
                return ApiError(404, "not_found", "Not found.").to_response()
            if http.get("method") != "POST":
                return ApiError(405, "method_not_allowed", "Use POST.").to_response()
            request_id = event["requestContext"].get("requestId") or str(uuid.uuid4())
            return self._chat(event, request_id)
        # Direct invoke only: function URL events always carry requestContext.http.
        if isinstance(event.get("smoke"), str) and "requestContext" not in event:
            request_id = getattr(context, "aws_request_id", None) or str(uuid.uuid4())
            return self._smoke(event["smoke"], request_id)
        return ApiError(400, "bad_request", "Unsupported event.").to_response()

    def _chat(self, event: dict[str, Any], request_id: str) -> dict[str, Any]:
        body = event.get("body")
        if body and event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8", errors="replace")
        state = {"comment": "", "user_hash": ""}

        def run(trace: Trace) -> PipelineResult:
            s = self.settings
            request = parse_request(body, max_chars=s.max_comment_chars)
            state["comment"] = request.comment
            ip = client_ip(event.get("headers") or {}, s.client_ip_header)
            state["user_hash"] = self._user_hash(ip)
            self.verify_turnstile(request.turnstile_token, self.secrets.turnstile_secret(), ip)
            self.rate_limiter.check(ip, self.now())
            return self.pipeline().run(request.comment, request.style, request.platform, trace)

        return self._respond(run, request_id, state)

    def _user_hash(self, ip: str) -> str:
        """For the logs only, so a missing key must never fail the reply."""
        try:
            return user_hash(self.secrets.log_hash_key(), ip, self.now())
        except Exception as e:
            print(f"user_hash unavailable: {type(e).__name__}: {e}")
            return "unknown"

    def _smoke(self, comment: str, request_id: str) -> dict[str, Any]:
        state = {"comment": comment, "user_hash": SMOKE_USER}
        return self._respond(
            lambda trace: self.pipeline().run(comment, "match", None, trace), request_id, state
        )

    def _respond(
        self,
        run: Callable[[Trace], PipelineResult],
        request_id: str,
        state: dict[str, str],
    ) -> dict[str, Any]:
        trace, start = Trace(), time.monotonic()
        result: PipelineResult | None = None
        error: ApiError | None = None
        try:
            result = run(trace)
        except ApiError as e:
            error = e
        except Exception:
            traceback.print_exc()  # CloudWatch only; the reply never carries details
            error = _internal()
        finally:
            item = log_item(
                comment=state["comment"],
                user_hash=state["user_hash"],
                trace=trace,
                result=result,
                error_code=error.code if error else None,
                latency_ms=int((time.monotonic() - start) * 1000),
                now=self.now(),
                ttl_days=self.settings.log_ttl_days,
                request_id=request_id,
            )
            write_log(self.log_table, item)
        if error:
            return error.to_response()
        assert result is not None
        return ok_response(_payload(result))


def build_app(settings: ServiceSettings | None = None) -> App:
    """The real collaborators: OpenRouter, S3 Vectors, DynamoDB and SSM."""
    import boto3

    from climate_chat.openrouter import ChatClient, EmbeddingClient
    from climate_chat.service.cache import AnswerCache
    from climate_chat.vectors import VectorIndex, s3vectors_client

    s = settings or load_service_settings()
    vectors = s3vectors_client(s.base)
    sources = VectorIndex.sources(s.base, vectors)
    cache = AnswerCache(
        VectorIndex(s.base.vector_bucket, s.base.cache_index, vectors), s.cache_max_distance
    )

    def pipeline_factory(key: str) -> Pipeline:
        return Pipeline(
            chat=ChatClient.from_api_key(key, s.model_fallback),
            embedder=EmbeddingClient.from_settings(s.base, key),
            sources=sources,
            cache=cache,
            settings=s,
        )

    session = boto3.Session(profile_name=s.base.aws_profile, region_name=s.base.region)
    return App(
        settings=s,
        secrets=SecretStore(s, ssm_client=session.client("ssm")),
        pipeline_factory=pipeline_factory,
        rate_limiter=RateLimiter(
            session.client("dynamodb"),
            s.ratelimits_table,
            per_minute=s.rate_limit_per_minute,
            per_day=s.rate_limit_per_day,
        ),
        log_table=session.resource("dynamodb").Table(s.logs_table),
    )
