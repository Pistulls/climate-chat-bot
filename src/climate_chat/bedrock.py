"""Embeddings from Amazon Titan Text V2 on AWS Bedrock (Design.md, Models; plan 06).

Same interface as `openrouter.EmbeddingClient`, so ingestion (documents) and the service
(queries) embed the same way whichever provider the model id picks. Titan takes one text
per call and needs no query prefix. Any AWS error becomes `EmbeddingError`, which the
pipeline turns into 502 `upstream_error`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Protocol

import numpy as np
from botocore.exceptions import BotoCoreError, ClientError

from climate_chat.openrouter import EmbeddingError

DEFAULT_WORKERS = 2  # this account's Titan quota is 300,000 tokens a minute


class _BedrockRuntime(Protocol):
    def invoke_model(self, *, modelId: str, body: str) -> dict[str, Any]: ...


@dataclass
class BedrockEmbeddingClient:
    model: str
    dimension: int
    client: _BedrockRuntime
    workers: int = DEFAULT_WORKERS
    tokens_used: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """One float32 row per text, in the same order."""
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        with ThreadPoolExecutor(self.workers) as pool:
            return np.vstack(list(pool.map(self._embed, texts)))

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)

    def _embed(self, text: str) -> np.ndarray:
        body = {"inputText": text, "dimensions": self.dimension, "normalize": True}
        try:
            response = self.client.invoke_model(modelId=self.model, body=json.dumps(body))
            data = json.loads(response["body"].read())
        except (ClientError, BotoCoreError) as e:
            raise EmbeddingError(f"Bedrock {self.model}: {e}") from e
        vector = np.asarray(data.get("embedding") or [], dtype=np.float32)
        if vector.shape != (self.dimension,):
            raise EmbeddingError(
                f"{self.model} returned {vector.size}-d vectors, expected {self.dimension}"
            )
        with self._lock:
            self.tokens_used += int(data.get("inputTextTokenCount", 0))
        return vector
