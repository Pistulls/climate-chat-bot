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

    def test_aws_profile_from_dotenv(self):
        assert settings(dotenv="AWS_PROFILE=dev-admin\n").aws_profile == "dev-admin"
        assert settings().aws_profile is None

    def test_ingest_key_param_is_the_ssm_name(self):
        assert settings().ingest_key_param == "/climate-chat/ingest/openrouter-api-key"


def test_repo_root_finds_pyproject():
    assert (repo_root() / "pyproject.toml").is_file()


SERVICE = {
    **BASE,
    "LOGS_TABLE": "climate-chat-dev-logs",
    "RATELIMITS_TABLE": "climate-chat-dev-ratelimits",
    "MODEL_CLASSIFY": "anthropic/claude-haiku-5.5",
    "MODEL_FACTS": "anthropic/claude-haiku-5.5",
    "MODEL_REPLY": "anthropic/claude-haiku-5.5",
    "MODEL_FALLBACK": "openai/gpt-6-luna",
}


def service_settings(drop=(), **environ):
    from climate_chat.config import load_service_settings

    merged = {k: v for k, v in {**SERVICE, **environ}.items() if k not in drop}
    return load_service_settings(environ=merged, dotenv_path=Path("/nonexistent/.env"))


class TestServiceSettings:
    def test_service_settings_defaults(self):
        s = service_settings()
        assert s.base.vector_bucket == "climate-chat-dev-vectors"
        assert (s.logs_table, s.ratelimits_table) == (
            "climate-chat-dev-logs",
            "climate-chat-dev-ratelimits",
        )
        assert (s.model_classify, s.model_fallback) == (
            "anthropic/claude-haiku-5.5",
            "openai/gpt-6-luna",
        )
        assert (s.rate_limit_per_minute, s.rate_limit_per_day) == (10, 100)
        assert (s.max_comment_chars, s.log_ttl_days) == (1000, 90)
        assert s.max_tokens == {"classify": 200, "facts": 1000, "reply": 300}
        assert s.cache_max_distance == 0.15
        assert s.excluded_licences == ()
        assert s.client_ip_header == "cloudfront-viewer-address"
        assert s.openrouter_key_param == "/climate-chat/dev/openrouter-api-key"
        assert s.turnstile_secret_param == "/climate-chat/dev/turnstile-secret-key"
        assert s.log_hash_key_param == "/climate-chat/dev/log-hash-key"
        assert (s.openrouter_api_key, s.turnstile_secret_key, s.log_hash_key) == (None,) * 3

    def test_service_settings_reads_overrides(self):
        s = service_settings(
            RATE_LIMIT_PER_MINUTE="3",
            RATE_LIMIT_PER_DAY="30",
            MAX_COMMENT_CHARS="500",
            LOG_TTL_DAYS="7",
            MAX_TOKENS_CLASSIFY="120",
            MAX_TOKENS_FACTS="600",
            MAX_TOKENS_REPLY="250",
            CACHE_MAX_DISTANCE="0.1",
            CLIENT_IP_HEADER="x-forwarded-for",
            OPENROUTER_KEY_PARAM="/climate-chat/prod/openrouter-api-key",
            OPENROUTER_API_KEY="sk-local",
            TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
            LOG_HASH_KEY="local-hash-key",
        )
        assert (s.rate_limit_per_minute, s.rate_limit_per_day) == (3, 30)
        assert (s.max_comment_chars, s.log_ttl_days) == (500, 7)
        assert s.max_tokens == {"classify": 120, "facts": 600, "reply": 250}
        assert s.cache_max_distance == 0.1
        assert s.client_ip_header == "x-forwarded-for"
        assert s.openrouter_key_param == "/climate-chat/prod/openrouter-api-key"
        assert s.openrouter_api_key == "sk-local"
        assert s.turnstile_secret_key == "1x0000000000000000000000000000000AA"
        assert s.log_hash_key == "local-hash-key"

    def test_excluded_licences_parsed(self):
        s = service_settings(EXCLUDED_LICENCES="non-commercial, restricted")
        assert s.excluded_licences == ("non-commercial", "restricted")

    def test_blank_excluded_licences_is_empty(self):
        assert service_settings(EXCLUDED_LICENCES=" , ").excluded_licences == ()

    @pytest.mark.parametrize("missing", ["LOGS_TABLE", "RATELIMITS_TABLE", "MODEL_FACTS"])
    def test_service_settings_requires_tables_and_models(self, missing):
        with pytest.raises(ConfigError, match=missing):
            service_settings(drop=(missing,))

    @pytest.mark.parametrize(
        ("key", "value"),
        [("RATE_LIMIT_PER_DAY", "ten"), ("MAX_TOKENS_REPLY", "-5"), ("CACHE_MAX_DISTANCE", "x")],
    )
    def test_service_settings_rejects_bad_numbers(self, key, value):
        with pytest.raises(ConfigError, match=key):
            service_settings(**{key: value})

    def test_prod_param_names_follow_app_env(self):
        s = service_settings(APP_ENV="prod")
        assert s.log_hash_key_param == "/climate-chat/prod/log-hash-key"


def test_tuned_max_tokens_defaults():
    from climate_chat.config import DEFAULT_MAX_TOKENS

    assert DEFAULT_MAX_TOKENS == {"classify": 200, "facts": 1000, "reply": 300}
