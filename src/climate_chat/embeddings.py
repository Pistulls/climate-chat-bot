"""Picks the embedding client for a model id (Design.md, Models; plan 06).

Ids starting `amazon.` are called through AWS Bedrock with the caller's AWS credentials
(the Lambda's role, or the .env profile). Anything else goes through OpenRouter and needs
an API key. Both clients have the same interface.
"""

from __future__ import annotations

from typing import Any

from botocore.config import Config

from climate_chat.bedrock import BedrockEmbeddingClient
from climate_chat.openrouter import EmbeddingClient

# Replies: fail fast so a stuck call can't use up the Lambda's 30 s.
SERVICE_CONFIG = Config(
    retries={"mode": "standard", "max_attempts": 3}, connect_timeout=2, read_timeout=5
)
# Ingestion: ride out Titan's 300,000 tokens-a-minute quota.
INGEST_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 12}, read_timeout=30)


def uses_bedrock(model: str) -> bool:
    return model.startswith("amazon.")


def embedding_client(
    model: str,
    dimension: int,
    *,
    settings: Any,
    api_key: str | None = None,
    for_ingest: bool = False,
) -> BedrockEmbeddingClient | EmbeddingClient:
    """`settings` provides `aws_client(service, **kwargs)` (config.Settings)."""
    if uses_bedrock(model):
        config = INGEST_CONFIG if for_ingest else SERVICE_CONFIG
        return BedrockEmbeddingClient(
            model, dimension, settings.aws_client("bedrock-runtime", config=config)
        )
    if not api_key:
        raise ValueError(f"{model} is called through OpenRouter and needs an API key")
    return EmbeddingClient.for_model(model, dimension, api_key)
