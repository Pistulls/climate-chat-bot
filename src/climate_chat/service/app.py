"""The Lambda request handler: routing, the pre-LLM checks in order, logging.

Two routes: POST /api/chat for everyone, and GET /api/logs (the request logs) for whoever
holds the admin key, sent as X-Admin-Key. A missing or wrong key gets the same 404 as any
unknown path. (Not Authorization: CloudFront's OAC signing replaces that header.)

`App` takes its collaborators as arguments so tests can pass fakes; `build_app()` wires up
the real ones from settings.
"""

from __future__ import annotations

import base64
import hmac
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import parse_qs

from climate_chat.config import ServiceSettings, load_service_settings
from climate_chat.service.api import ApiError, context_field, ok_response, parse_request
from climate_chat.service.guards import RateLimiter, client_ip, user_hash
from climate_chat.service.guards import verify_turnstile as real_verify_turnstile
from climate_chat.service.logs import BadCursor, log_item, read_logs, write_log
from climate_chat.service.pipeline import Pipeline, PipelineResult, Trace
from climate_chat.service.secrets import SecretStore

CHAT_PATH = "/api/chat"
LOGS_PATH = "/api/logs"
LOGS_PAGE_DEFAULT = 25
LOGS_PAGE_MAX = 100
# `openssl rand -base64 32` gives 44 characters. Anything much shorter is the bootstrap
# placeholder (CHANGE_ME) or a mistake, and must never unlock the logs.
MIN_ADMIN_KEY_CHARS = 32
SMOKE_USER = "smoke"


class _Secrets(Protocol):
    def openrouter_key(self) -> str: ...
    def turnstile_secret(self) -> str: ...
    def log_hash_key(self) -> str: ...
    def admin_key(self) -> str: ...


class _Pipeline(Protocol):
    def run(
        self, comment: str, style: str, platform: str | None, trace: Trace
    ) -> PipelineResult: ...


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "Not found.")


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
        verify_turnstile: Callable[..., None] = real_verify_turnstile,
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
            if event.get("rawPath") == LOGS_PATH:
                return self._logs(event, http.get("method"))
            if event.get("rawPath") != CHAT_PATH:
                return _not_found().to_response()
            if http.get("method") != "POST":
                return ApiError(405, "method_not_allowed", "Use POST.").to_response()
            request_id = event["requestContext"].get("requestId") or str(uuid.uuid4())
            return self._chat(event, request_id)
        # Direct invoke only: function URL events always carry requestContext.http.
        if isinstance(event.get("smoke"), str) and "requestContext" not in event:
            request_id = getattr(context, "aws_request_id", None) or str(uuid.uuid4())
            return self._smoke(event, request_id)
        return ApiError(400, "bad_request", "Unsupported event.").to_response()

    def _admin(self, event: dict[str, Any]) -> bool:
        """True only for the exact admin key, compared in constant time. A placeholder or
        short stored key unlocks nothing."""
        given = (event.get("headers") or {}).get("x-admin-key") or ""
        expected = self.secrets.admin_key()
        if len(expected) < MIN_ADMIN_KEY_CHARS:
            return False
        return hmac.compare_digest(given.encode(), expected.encode())

    def _logs(self, event: dict[str, Any], method: str | None) -> dict[str, Any]:
        """GET /api/logs?limit=25&cursor=...: one page of request logs, newest first."""
        try:
            if not self._admin(event):
                return _not_found().to_response()
        except Exception:
            traceback.print_exc()
            return _internal().to_response()
        if method != "GET":
            return ApiError(405, "method_not_allowed", "Use GET.").to_response()
        params = parse_qs(event.get("rawQueryString") or "")
        try:
            limit = int(params.get("limit", [str(LOGS_PAGE_DEFAULT)])[0])
        except ValueError:
            return ApiError(400, "bad_request", "limit must be a number.").to_response()
        try:
            page = read_logs(
                self.log_table,
                today=self.now().date(),
                days=self.settings.log_ttl_days,
                limit=max(1, min(limit, LOGS_PAGE_MAX)),
                cursor=params.get("cursor", [None])[0],
            )
        except BadCursor:
            return ApiError(400, "bad_cursor", "That page link is invalid.").to_response()
        except Exception as e:  # only the key holder sees this, so say what failed
            traceback.print_exc()
            hint = (
                " Sign in to AWS (aws sso login) and try again."
                if "token" in str(e).lower()
                else ""
            )
            message = f"Couldn't read {self.settings.logs_table}: {e}.{hint}"
            return ApiError(503, "logs_unavailable", message).to_response()
        response = ok_response({"table": self.settings.logs_table, **page})
        response["headers"] = {**response["headers"], "cache-control": "no-store"}
        return response

    def _chat(self, event: dict[str, Any], request_id: str) -> dict[str, Any]:
        body = event.get("body")
        if body and event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8", errors="replace")
        state: dict[str, str | None] = {"comment": "", "user_hash": ""}

        def run(trace: Trace) -> PipelineResult:
            s = self.settings
            request = parse_request(
                body,
                max_chars=s.max_comment_chars,
                max_subject_chars=s.max_subject_chars,
                max_thread_chars=s.max_thread_chars,
            )
            state.update(comment=request.comment, subject=request.subject, thread=request.thread)
            ip = client_ip(event.get("headers") or {}, s.client_ip_header)
            state["user_hash"] = self._user_hash(ip)
            self.verify_turnstile(
                request.turnstile_token,
                self.secrets.turnstile_secret(),
                ip,
                hostnames=s.turnstile_hostnames,
            )
            self.rate_limiter.check(ip, self.now())
            return self.pipeline().run(
                request.comment,
                request.style,
                request.platform,
                trace,
                subject=request.subject,
                thread=request.thread,
            )

        return self._respond(run, request_id, state)

    def _user_hash(self, ip: str) -> str:
        """For the logs only, so a missing key must never fail the reply."""
        try:
            return user_hash(self.secrets.log_hash_key(), ip, self.now())
        except Exception as e:
            print(f"user_hash unavailable: {type(e).__name__}: {e}")
            return "unknown"

    def _smoke(self, event: dict[str, Any], request_id: str) -> dict[str, Any]:
        comment = event["smoke"]
        state: dict[str, str | None] = {"comment": comment, "user_hash": SMOKE_USER}

        def run(trace: Trace) -> PipelineResult:
            s = self.settings
            subject = context_field(event, "subject", s.max_subject_chars)
            thread = context_field(event, "thread", s.max_thread_chars)
            state.update(subject=subject, thread=thread)
            return self.pipeline().run(
                comment, "match", None, trace, subject=subject, thread=thread
            )

        return self._respond(run, request_id, state)

    def _respond(
        self,
        run: Callable[[Trace], PipelineResult],
        request_id: str,
        state: dict[str, str | None],
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
                comment=state["comment"] or "",
                user_hash=state["user_hash"] or "",
                subject=state.get("subject"),
                thread=state.get("thread"),
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

    from climate_chat.embeddings import embedding_client
    from climate_chat.openrouter import ChatClient
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
            embedder=embedding_client(
                s.base.model_embedding, s.base.embedding_dimension, settings=s.base, api_key=key
            ),
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
