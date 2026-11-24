import io
import json
import random
import threading
import time

import numpy as np
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from climate_chat.bedrock import BedrockEmbeddingClient
from climate_chat.openrouter import EmbeddingError

MODEL = "amazon.titan-embed-text-v2:0"
DIM = 4


class FakeBedrock:
    """invoke_model returning a vector derived from the text, so order can be checked."""

    def __init__(self, dimension=DIM, error=None, jitter=False):
        self.dimension, self.error, self.jitter = dimension, error, jitter
        self.calls = []
        self.lock = threading.Lock()

    def invoke_model(self, *, modelId, body):
        request = json.loads(body)
        with self.lock:
            self.calls.append((modelId, request))
        if self.error:
            raise self.error
        if self.jitter:
            time.sleep(random.uniform(0, 0.01))
        text = request["inputText"]
        vector = [float(len(text))] + [0.0] * (self.dimension - 1)
        payload = {"embedding": vector, "inputTextTokenCount": len(text.split())}
        return {"body": io.BytesIO(json.dumps(payload).encode())}


def client(fake=None, **kwargs):
    return BedrockEmbeddingClient(MODEL, DIM, fake or FakeBedrock(), **kwargs)


def test_bedrock_request_body():
    fake = FakeBedrock()
    client(fake).embed_query("Solar is useless at night")
    assert fake.calls == [
        (MODEL, {"inputText": "Solar is useless at night", "dimensions": DIM, "normalize": True})
    ]


def test_bedrock_query_has_no_prefix():
    fake = FakeBedrock()
    client(fake).embed_query("CO2 is plant food")
    assert fake.calls[0][1]["inputText"] == "CO2 is plant food"


def test_bedrock_query_returns_float32_vector():
    vector = client().embed_query("abc")
    assert vector.dtype == np.float32 and vector.shape == (DIM,)


def test_bedrock_counts_tokens():
    c = client()
    c.embed_documents(["one two", "three four five"])
    c.embed_query("six")
    assert c.tokens_used == 6


def test_bedrock_documents_keep_order():
    texts = ["x" * n for n in range(1, 41)]
    vectors = client(FakeBedrock(jitter=True), workers=4).embed_documents(texts)
    assert vectors.shape == (40, DIM)
    assert list(vectors[:, 0]) == [float(n) for n in range(1, 41)]


def test_bedrock_no_documents():
    assert client().embed_documents([]).shape == (0, DIM)


def test_bedrock_dimension_mismatch():
    with pytest.raises(EmbeddingError, match=r"1024-d vectors, expected 4"):
        client(FakeBedrock(dimension=1024)).embed_query("abc")


@pytest.mark.parametrize(
    "error",
    [
        ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "InvokeModel"),
        EndpointConnectionError(endpoint_url="https://bedrock-runtime.eu-west-2.amazonaws.com"),
    ],
)
def test_bedrock_error_becomes_embedding_error(error):
    with pytest.raises(EmbeddingError):
        client(FakeBedrock(error=error)).embed_query("abc")


@pytest.mark.live
def test_titan_live_query():
    """One real Titan V2 call through Bedrock with the .env AWS profile."""
    from climate_chat.config import load_settings
    from climate_chat.embeddings import embedding_client

    settings = load_settings()
    live = embedding_client(MODEL, 1024, settings=settings)
    vector = live.embed_query("Solar panels are useless because they don't generate at night.")
    assert vector.shape == (1024,)
    assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-3
    assert live.tokens_used > 0
