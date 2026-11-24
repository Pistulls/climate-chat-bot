"""Embeddings and chat completions through OpenRouter's OpenAI-compatible API.

Shared by ingestion (documents) and the service (queries), so both embed the same way.
Documents are embedded as they are; queries get the model's instruction prefix, which
asymmetric retrieval models such as Qwen3-Embedding are trained to expect.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import openai

from climate_chat.config import OPENROUTER_BASE_URL, Settings

DEFAULT_BATCH_SIZE = 64
MAX_RETRIES = 5  # the SDK retries 408/409/429/5xx with exponential backoff

# Ask OpenRouter to route only to providers that don't keep or train on the data.
PROVIDER_ROUTING = {"provider": {"data_collection": "deny"}}

# Chat calls run inside the Lambda's 30 s budget, so they retry less and time out sooner.
CHAT_MAX_RETRIES = 2
CHAT_TIMEOUT_S = 20

QUERY_TASK = "Given a climate-sceptic claim, retrieve passages with evidence about it"


class EmbeddingError(Exception):
    """OpenRouter returned something unusable."""


class CreditCapReached(EmbeddingError):
    """HTTP 402: this OpenRouter key's credit cap is spent. Retrying won't help."""


def query_text(model: str, text: str) -> str:
    """The query as the model expects it. Only Qwen3 embeddings use an instruction."""
    if model.startswith("qwen/qwen3-embedding"):
        return f"Instruct: {QUERY_TASK}\nQuery: {text}"
    return text


class _EmbeddingsAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _Client(Protocol):
    embeddings: _EmbeddingsAPI


@dataclass
class EmbeddingClient:
    model: str
    dimension: int
    client: _Client
    batch_size: int = DEFAULT_BATCH_SIZE
    tokens_used: int = field(default=0, init=False)

    @classmethod
    def from_settings(cls, settings: Settings, api_key: str, **kwargs: Any) -> EmbeddingClient:
        return cls.for_model(
            settings.model_embedding, settings.embedding_dimension, api_key, **kwargs
        )

    @classmethod
    def for_model(cls, model: str, dimension: int, api_key: str, **kwargs: Any) -> EmbeddingClient:
        """A client for any model, e.g. each candidate in the embedding bake-off."""
        client = openai.OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            max_retries=MAX_RETRIES,
            timeout=60,
        )
        return cls(model, dimension, client, **kwargs)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """One float32 row per text, in the same order."""
        rows = [
            self._embed_batch(texts[i : i + self.batch_size])
            for i in range(0, len(texts), self.batch_size)
        ]
        return np.vstack(rows) if rows else np.empty((0, self.dimension), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed_batch([query_text(self.model, text)])[0]

    def _embed_batch(self, batch: Sequence[str]) -> np.ndarray:
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=list(batch),
                encoding_format="float",
                extra_body=PROVIDER_ROUTING,
            )
        except openai.APIStatusError as e:
            if e.status_code == 402:
                raise CreditCapReached(
                    "OpenRouter returned 402: this key's credit cap is spent"
                ) from e
            raise

        data = sorted(response.data or [], key=lambda d: d.index)
        if len(data) != len(batch):
            raise EmbeddingError(f"Expected {len(batch)} embeddings, got {len(data)}")
        vectors = np.asarray([d.embedding for d in data], dtype=np.float32)
        if vectors.shape[1] != self.dimension:
            raise EmbeddingError(
                f"{self.model} returned {vectors.shape[1]}-d vectors, expected {self.dimension}"
            )
        if response.usage is not None:
            self.tokens_used += response.usage.prompt_tokens
        return vectors


@dataclass(frozen=True)
class ChatResult:
    text: str  # "" when the model returned no answer; the caller decides what that means
    model: str  # the model that served the request (the fallback, if it was used)
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost: float  # USD, from OpenRouter's usage.cost


class ChatClient:
    """Chat completions with JSON-schema output (Design.md, LLM).

    Every call names the fallback model, routes only to providers that deny data collection
    and support every parameter sent (so the schema is enforced), turns reasoning off unless
    asked, and never sends `temperature`, which neither configured model supports.
    """

    def __init__(self, client: Any, fallback: str):
        self.client = client
        self.fallback = fallback

    @classmethod
    def from_api_key(cls, api_key: str, fallback: str) -> ChatClient:
        client = openai.OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            max_retries=CHAT_MAX_RETRIES,
            timeout=CHAT_TIMEOUT_S,
        )
        return cls(client, fallback)

    def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        schema: dict[str, Any],
        reasoning: bool = False,
    ) -> ChatResult:
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "output", "strict": True, "schema": schema},
                },
                extra_body={
                    "models": [model, self.fallback],
                    "provider": {**PROVIDER_ROUTING["provider"], "require_parameters": True},
                    "reasoning": {"enabled": reasoning},
                },
            )
        except openai.APIStatusError as e:
            if e.status_code == 402:
                raise CreditCapReached(
                    "OpenRouter returned 402: this key's credit cap is spent"
                ) from e
            raise

        usage = response.usage
        details = getattr(usage, "completion_tokens_details", None)
        extra = getattr(usage, "model_extra", None) or {}
        return ChatResult(
            text=response.choices[0].message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            reasoning_tokens=getattr(details, "reasoning_tokens", None) or 0,
            cost=float(extra.get("cost") or 0.0),
        )


def resolve_ingest_api_key(settings: Settings, ssm_client: Any | None = None) -> str:
    """INGEST_OPENROUTER_API_KEY from .env, else the ingest SSM parameter."""
    if settings.ingest_openrouter_api_key:
        return settings.ingest_openrouter_api_key
    if ssm_client is None:
        ssm_client = settings.aws_client("ssm")
    response = ssm_client.get_parameter(Name=settings.ingest_key_param, WithDecryption=True)
    return response["Parameter"]["Value"]
