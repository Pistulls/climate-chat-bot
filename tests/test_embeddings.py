import pytest

from climate_chat.bedrock import BedrockEmbeddingClient
from climate_chat.embeddings import embedding_client, uses_bedrock
from climate_chat.openrouter import EmbeddingClient

TITAN = "amazon.titan-embed-text-v2:0"


class FakeSettings:
    def __init__(self):
        self.clients = []

    def aws_client(self, service, **kwargs):
        self.clients.append((service, kwargs))
        return object()


def test_uses_bedrock_by_model_id():
    assert uses_bedrock(TITAN)
    assert not uses_bedrock("openai/text-embedding-3-small")


def test_amazon_model_uses_bedrock():
    settings = FakeSettings()
    client = embedding_client(TITAN, 1024, settings=settings)
    assert isinstance(client, BedrockEmbeddingClient)
    assert (client.model, client.dimension) == (TITAN, 1024)
    assert [service for service, _ in settings.clients] == ["bedrock-runtime"]


def test_other_models_use_openrouter():
    settings = FakeSettings()
    client = embedding_client("openai/text-embedding-3-small", 1536, settings=settings, api_key="k")
    assert isinstance(client, EmbeddingClient)
    assert (client.model, client.dimension) == ("openai/text-embedding-3-small", 1536)
    assert settings.clients == []


def test_openrouter_model_needs_api_key():
    with pytest.raises(ValueError, match="API key"):
        embedding_client("openai/text-embedding-3-small", 1536, settings=FakeSettings())


def _config(for_ingest):
    settings = FakeSettings()
    embedding_client(TITAN, 1024, settings=settings, for_ingest=for_ingest)
    return settings.clients[0][1]["config"]


def test_service_client_uses_standard_retries_and_timeouts():
    """A stuck call mustn't use up the Lambda's 30 s budget."""
    config = _config(for_ingest=False)
    assert config.retries == {"mode": "standard", "max_attempts": 3}
    assert (config.connect_timeout, config.read_timeout) == (2, 5)


def test_ingest_client_uses_adaptive_retries():
    """Ingestion rides out the 300,000 tokens-a-minute quota instead of failing."""
    config = _config(for_ingest=True)
    assert config.retries == {"mode": "adaptive", "max_attempts": 12}
