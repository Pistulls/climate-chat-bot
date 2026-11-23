from pathlib import Path

import pytest

from climate_chat.config import ConfigError, load_settings, parse_dotenv, repo_root

BASE = {"MODEL_EMBEDDING": "qwen/qwen3-embedding-8b", "EMBEDDING_DIMENSION": "4096"}


def settings(env=None, dotenv="", **environ):
    path = Path("/nonexistent/.env")
    if dotenv:
        import tempfile

        path = Path(tempfile.mkdtemp()) / ".env"
        path.write_text(dotenv)
    return load_settings(env, environ={**BASE, **environ}, dotenv_path=path)


class TestParseDotenv:
    def test_reads_keys_and_skips_comments_and_blanks(self):
        text = "# comment\n\nA=1\n  B = two words \nexport C=3\nnot a pair\n"
        assert parse_dotenv(text) == {"A": "1", "B": "two words", "C": "3"}

    def test_strips_matching_quotes_only(self):
        assert parse_dotenv("A=\"x\"\nB='y'\nC=\"z'") == {"A": "x", "B": "y", "C": "\"z'"}

    def test_keeps_equals_signs_in_values(self):
        assert parse_dotenv("KEY=abc==") == {"KEY": "abc=="}


class TestLoadSettings:
    def test_defaults_to_dev(self):
        s = settings()
        assert (s.env, s.vector_bucket, s.sources_index, s.region) == (
            "dev",
            "climate-chat-dev-vectors",
            "sources",
            "eu-west-2",
        )

    def test_env_argument_picks_that_envs_bucket_even_if_vector_bucket_is_set(self):
        s = settings("prod", APP_ENV="dev", VECTOR_BUCKET="climate-chat-dev-vectors")
        assert (s.env, s.vector_bucket) == ("prod", "climate-chat-prod-vectors")

    def test_process_environment_wins_over_dotenv(self):
        s = settings(dotenv="SOURCES_INDEX=from-file\n", SOURCES_INDEX="from-env")
        assert s.sources_index == "from-env"

    def test_dotenv_used_when_not_in_environment(self):
        assert settings(dotenv="CACHE_INDEX=from-file\n").cache_index == "from-file"

    def test_placeholders_count_as_unset(self):
        s = settings(INGEST_OPENROUTER_API_KEY="<openrouter-ingest-key>")
        assert s.ingest_openrouter_api_key is None

    def test_rejects_unknown_env(self):
        with pytest.raises(ConfigError, match="env must be one of"):
            settings("staging")

    def test_requires_embedding_model(self):
        with pytest.raises(ConfigError, match="MODEL_EMBEDDING"):
            load_settings(environ={"EMBEDDING_DIMENSION": "4096"}, dotenv_path=Path("/nope"))

    def test_rejects_non_numeric_dimension(self):
        with pytest.raises(ConfigError, match="integer"):
            settings(EMBEDDING_DIMENSION="big")

    def test_ingest_key_param_is_the_ssm_name(self):
        assert settings().ingest_key_param == "/climate-chat/ingest/openrouter-api-key"


def test_repo_root_finds_pyproject():
    assert (repo_root() / "pyproject.toml").is_file()
