from types import SimpleNamespace

import numpy as np
import openai
import pytest

from climate_chat.config import load_settings
from climate_chat.openrouter import (
    PROVIDER_ROUTING,
    CreditCapReached,
    EmbeddingClient,
    EmbeddingError,
    query_text,
    resolve_ingest_api_key,
)

DIM = 4


class FakeEmbeddings:
    """Stands in for client.embeddings; records calls and returns vector i = [i, i, i, i]."""

    def __init__(self, dim=DIM, shuffle=False, drop=0, error=None, usage=True):
        self.calls = []
        self.dim, self.shuffle, self.drop, self.error, self.usage = dim, shuffle, drop, error, usage

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        n = len(kwargs["input"]) - self.drop
        data = [SimpleNamespace(index=i, embedding=[float(i)] * self.dim) for i in range(n)]
        if self.shuffle:
            data.reverse()
        usage = SimpleNamespace(prompt_tokens=10 * n) if self.usage else None
        return SimpleNamespace(data=data, usage=usage)


def make(fake, batch_size=64, model="qwen/qwen3-embedding-8b"):
    return EmbeddingClient(model, DIM, SimpleNamespace(embeddings=fake), batch_size=batch_size)


def status_error(code):
    err = openai.APIStatusError.__new__(openai.APIStatusError)
    err.status_code = code
    return err


class TestEmbedDocuments:
    def test_returns_float32_rows_in_input_order(self):
        out = make(FakeEmbeddings(shuffle=True)).embed_documents(["a", "b", "c"])
        assert out.dtype == np.float32
        assert out.shape == (3, DIM)
        assert out[:, 0].tolist() == [0.0, 1.0, 2.0]

    def test_batches_requests(self):
        fake = FakeEmbeddings()
        out = make(fake, batch_size=2).embed_documents(["a", "b", "c", "d", "e"])
        assert [c["input"] for c in fake.calls] == [["a", "b"], ["c", "d"], ["e"]]
        assert out.shape == (5, DIM)

    def test_sends_model_float_encoding_and_provider_routing(self):
        fake = FakeEmbeddings()
        make(fake).embed_documents(["a"])
        call = fake.calls[0]
        assert call["model"] == "qwen/qwen3-embedding-8b"
        assert call["encoding_format"] == "float"
        assert call["extra_body"] == PROVIDER_ROUTING == {"provider": {"data_collection": "deny"}}

    def test_documents_are_sent_without_a_prefix(self):
        fake = FakeEmbeddings()
        make(fake).embed_documents(["solar output"])
        assert fake.calls[0]["input"] == ["solar output"]

    def test_empty_input_makes_no_call(self):
        fake = FakeEmbeddings()
        assert make(fake).embed_documents([]).shape == (0, DIM)
        assert fake.calls == []

    def test_counts_tokens(self):
        client = make(FakeEmbeddings(), batch_size=2)
        client.embed_documents(["a", "b", "c"])
        assert client.tokens_used == 30

    def test_missing_usage_is_tolerated(self):
        client = make(FakeEmbeddings(usage=False))
        client.embed_documents(["a"])
        assert client.tokens_used == 0


class TestFailures:
    def test_wrong_dimension(self):
        with pytest.raises(EmbeddingError, match="returned 3-d vectors, expected 4"):
            make(FakeEmbeddings(dim=3)).embed_documents(["a"])

    def test_missing_embeddings(self):
        with pytest.raises(EmbeddingError, match="Expected 2 embeddings, got 1"):
            make(FakeEmbeddings(drop=1)).embed_documents(["a", "b"])

    def test_402_means_credit_cap(self):
        with pytest.raises(CreditCapReached):
            make(FakeEmbeddings(error=status_error(402))).embed_documents(["a"])

    def test_other_status_errors_pass_through(self):
        with pytest.raises(openai.APIStatusError):
            make(FakeEmbeddings(error=status_error(400))).embed_documents(["a"])


class TestQueries:
    def test_qwen_queries_get_the_instruction_prefix(self):
        text = query_text("qwen/qwen3-embedding-8b", "solar is useless at night")
        assert text.startswith("Instruct: ")
        assert text.endswith("\nQuery: solar is useless at night")

    def test_openai_queries_are_sent_as_is(self):
        assert query_text("openai/text-embedding-3-small", "q") == "q"

    def test_embed_query_returns_one_vector_with_prefix(self):
        fake = FakeEmbeddings()
        vec = make(fake).embed_query("q")
        assert vec.shape == (DIM,)
        assert fake.calls[0]["input"][0].startswith("Instruct: ")


class TestResolveIngestApiKey:
    def settings(self, **environ):
        return load_settings(
            environ={"MODEL_EMBEDDING": "m", "EMBEDDING_DIMENSION": "4", **environ},
            dotenv_path=__import__("pathlib").Path("/nope"),
        )

    def test_prefers_env_value(self):
        class NoSSM:
            def get_parameter(self, **_):
                raise AssertionError("SSM must not be called")

        s = self.settings(INGEST_OPENROUTER_API_KEY="from-env")
        assert resolve_ingest_api_key(s, NoSSM()) == "from-env"

    def test_falls_back_to_ssm_with_decryption(self):
        calls = []

        class SSM:
            def get_parameter(self, **kwargs):
                calls.append(kwargs)
                return {"Parameter": {"Value": "from-ssm"}}

        s = self.settings(INGEST_OPENROUTER_API_KEY="<openrouter-ingest-key>")
        assert resolve_ingest_api_key(s, SSM()) == "from-ssm"
        name = "/climate-chat/ingest/openrouter-api-key"
        assert calls == [{"Name": name, "WithDecryption": True}]


# --- ChatClient (plan 03) ---

SCHEMA = {
    "type": "object",
    "properties": {"claim": {"type": "string"}},
    "required": ["claim"],
    "additionalProperties": False,
}
MESSAGES = [{"role": "user", "content": "hi"}]


class FakeCompletions:
    """Stands in for client.chat.completions; records calls and returns one canned reply."""

    def __init__(self, content='{"claim": "x"}', error=None, cost=0.00012, reasoning=0):
        self.calls = []
        self.content, self.error, self.cost, self.reasoning = content, error, cost, reasoning

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        usage = SimpleNamespace(
            prompt_tokens=80,
            completion_tokens=40,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=self.reasoning),
            model_extra={"cost": self.cost} if self.cost is not None else {},
        )
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(
            model="openai/gpt-6-luna", choices=[SimpleNamespace(message=message)], usage=usage
        )


def chat(fake):
    from climate_chat.openrouter import ChatClient

    return ChatClient(SimpleNamespace(chat=SimpleNamespace(completions=fake)), "openai/gpt-6-luna")


class TestChatClient:
    def test_complete_sends_fallback_and_routing(self):
        fake = FakeCompletions()
        chat(fake).complete("anthropic/claude-haiku-5.5", MESSAGES, max_tokens=150, schema=SCHEMA)
        call = fake.calls[0]
        assert call["model"] == "anthropic/claude-haiku-5.5"
        assert call["messages"] == MESSAGES
        assert call["max_tokens"] == 150
        body = call["extra_body"]
        assert body["models"] == ["anthropic/claude-haiku-5.5", "openai/gpt-6-luna"]
        assert body["provider"] == {"data_collection": "deny", "require_parameters": True}
        assert call["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "output", "strict": True, "schema": SCHEMA},
        }

    def test_complete_sends_no_temperature(self):
        fake = FakeCompletions()
        chat(fake).complete("m", MESSAGES, max_tokens=150, schema=SCHEMA)
        assert "temperature" not in fake.calls[0]
        assert "temperature" not in fake.calls[0]["extra_body"]

    def test_complete_reasoning_off_by_default(self):
        fake = FakeCompletions()
        client = chat(fake)
        client.complete("m", MESSAGES, max_tokens=150, schema=SCHEMA)
        client.complete("m", MESSAGES, max_tokens=150, schema=SCHEMA, reasoning=True)
        assert [c["extra_body"]["reasoning"] for c in fake.calls] == [
            {"enabled": False},
            {"enabled": True},
        ]

    def test_complete_maps_402(self):
        fake = FakeCompletions(error=status_error(402))
        with pytest.raises(CreditCapReached):
            chat(fake).complete("m", MESSAGES, max_tokens=150, schema=SCHEMA)

    def test_complete_other_errors_propagate(self):
        fake = FakeCompletions(error=status_error(500))
        with pytest.raises(openai.APIStatusError):
            chat(fake).complete("m", MESSAGES, max_tokens=150, schema=SCHEMA)

    def test_complete_reads_usage_and_cost(self):
        result = chat(FakeCompletions(reasoning=7)).complete(
            "m", MESSAGES, max_tokens=150, schema=SCHEMA
        )
        assert result.text == '{"claim": "x"}'
        assert result.model == "openai/gpt-6-luna"  # the model that actually served it
        assert (result.prompt_tokens, result.completion_tokens) == (80, 40)
        assert result.reasoning_tokens == 7
        assert result.cost == pytest.approx(0.00012)

    def test_complete_missing_cost_is_zero(self):
        result = chat(FakeCompletions(cost=None)).complete(
            "m", MESSAGES, max_tokens=150, schema=SCHEMA
        )
        assert result.cost == 0.0

    def test_complete_empty_content_returns_empty_text(self):
        result = chat(FakeCompletions(content=None)).complete(
            "m", MESSAGES, max_tokens=150, schema=SCHEMA
        )
        assert result.text == ""
