"""Settings shared by ingestion and the service.

Values come from the process environment first, then from the repo's `.env` file
(local development only; gitignored). The Lambda gets the same names from Terraform
(Infrastructure/app/hosting.tf), minus the secrets, which it reads from SSM.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ENVS = ("dev", "prod")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# SSM SecureString parameters created by Infrastructure/bootstrap.
SSM_PARAMS = {
    "ingest_openrouter": "/climate-chat/ingest/openrouter-api-key",
    "dev_openrouter": "/climate-chat/dev/openrouter-api-key",
    "prod_openrouter": "/climate-chat/prod/openrouter-api-key",
    "prod_turnstile": "/climate-chat/prod/turnstile-secret-key",
    "dev_log_hash": "/climate-chat/dev/log-hash-key",
    "prod_log_hash": "/climate-chat/prod/log-hash-key",
}

# Starting points from Design.md; tuned in plan 03 and overridden by environment variables.
DEFAULT_MAX_TOKENS = {"classify": 150, "facts": 1000, "reply": 200}
DEFAULT_CACHE_MAX_DISTANCE = 0.15


class ConfigError(Exception):
    """A required setting is missing or invalid."""


def repo_root(start: Path | None = None) -> Path:
    """The nearest directory above `start` that holds pyproject.toml."""
    here = (start or Path(__file__)).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    raise ConfigError(f"No pyproject.toml above {here}")


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines. Comments, blank lines and `export ` prefixes are allowed.

    Values may be wrapped in matching single or double quotes. Nothing is expanded or run.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_dotenv(path: Path) -> dict[str, str]:
    return parse_dotenv(path.read_text()) if path.is_file() else {}


def is_placeholder(value: str | None) -> bool:
    """True for unset values and `<...>` placeholders copied from .env.example."""
    return not value or (value.startswith("<") and value.endswith(">"))


@dataclass(frozen=True)
class Settings:
    env: str
    region: str
    vector_bucket: str
    sources_index: str
    cache_index: str
    model_embedding: str
    embedding_dimension: int
    ingest_openrouter_api_key: str | None
    aws_profile: str | None = None  # from .env for local runs; the Lambda uses its role

    @property
    def ingest_key_param(self) -> str:
        return SSM_PARAMS["ingest_openrouter"]

    def aws_client(self, service: str, **kwargs: Any) -> Any:
        """A boto3 client in this region, using AWS_PROFILE if set (it may come from .env,
        which boto3 doesn't read)."""
        import boto3

        session = boto3.Session(profile_name=self.aws_profile, region_name=self.region)
        return session.client(service, **kwargs)


class _Get(Protocol):
    def __call__(self, key: str, default: str | None = None) -> str | None: ...


def _reader(
    environ: Mapping[str, str] | None, dotenv_path: Path | None
) -> tuple[_Get, Callable[[str], str]]:
    """`get` and `require` over the process environment, falling back to `.env`."""
    file_values = load_dotenv(dotenv_path or repo_root() / ".env")
    merged = {**file_values, **(os.environ if environ is None else environ)}

    def get(key: str, default: str | None = None) -> str | None:
        value = merged.get(key)
        return default if is_placeholder(value) else value

    def require(key: str) -> str:
        value = get(key)
        if value is None:
            raise ConfigError(f"{key} is not set (see .env.example)")
        return value

    return get, require


def load_settings(
    env: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Settings:
    """Build Settings. `env` overrides APP_ENV and picks that env's vector bucket."""
    get, require = _reader(environ, dotenv_path)

    chosen = env or get("APP_ENV", "dev")
    if chosen not in ENVS:
        raise ConfigError(f"env must be one of {ENVS}, got {chosen!r}")

    # --env picks the bucket by name, so `--env prod` can't silently write to dev.
    bucket = (
        f"climate-chat-{chosen}-vectors"
        if env
        else get("VECTOR_BUCKET", f"climate-chat-{chosen}-vectors")
    )

    dimension = require("EMBEDDING_DIMENSION")
    if not dimension.isdigit():
        raise ConfigError(f"EMBEDDING_DIMENSION must be an integer, got {dimension!r}")

    return Settings(
        env=chosen,
        region=get("AWS_REGION", "eu-west-2"),
        vector_bucket=bucket,
        sources_index=get("SOURCES_INDEX", "sources"),
        cache_index=get("CACHE_INDEX", "response-cache"),
        model_embedding=require("MODEL_EMBEDDING"),
        embedding_dimension=int(dimension),
        ingest_openrouter_api_key=get("INGEST_OPENROUTER_API_KEY"),
        aws_profile=get("AWS_PROFILE"),
    )


@dataclass(frozen=True)
class ServiceSettings:
    """Settings for the /api/chat service. Secrets are given locally (from .env); in the
    Lambda they are None and are read from SSM by parameter name."""

    base: Settings
    logs_table: str
    ratelimits_table: str
    model_classify: str
    model_facts: str
    model_reply: str
    model_fallback: str
    rate_limit_per_minute: int
    rate_limit_per_day: int
    max_comment_chars: int
    log_ttl_days: int
    max_tokens: dict[str, int]
    cache_max_distance: float
    excluded_licences: tuple[str, ...]
    client_ip_header: str
    openrouter_key_param: str
    turnstile_secret_param: str
    log_hash_key_param: str
    openrouter_api_key: str | None
    turnstile_secret_key: str | None
    log_hash_key: str | None


def load_service_settings(
    *,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> ServiceSettings:
    base = load_settings(environ=environ, dotenv_path=dotenv_path)
    get, require = _reader(environ, dotenv_path)

    def positive_int(key: str, default: int) -> int:
        value = get(key)
        if value is None:
            return default
        if not value.isdigit() or int(value) == 0:
            raise ConfigError(f"{key} must be a positive integer, got {value!r}")
        return int(value)

    def distance(key: str, default: float) -> float:
        value = get(key)
        if value is None:
            return default
        try:
            number = float(value)
        except ValueError:
            number = -1.0
        if not 0.0 <= number <= 2.0:
            raise ConfigError(f"{key} must be a cosine distance between 0 and 2, got {value!r}")
        return number

    def param(key: str, name: str) -> str:
        return get(key) or f"/climate-chat/{base.env}/{name}"

    licences = get("EXCLUDED_LICENCES") or ""
    return ServiceSettings(
        base=base,
        logs_table=require("LOGS_TABLE"),
        ratelimits_table=require("RATELIMITS_TABLE"),
        model_classify=require("MODEL_CLASSIFY"),
        model_facts=require("MODEL_FACTS"),
        model_reply=require("MODEL_REPLY"),
        model_fallback=require("MODEL_FALLBACK"),
        rate_limit_per_minute=positive_int("RATE_LIMIT_PER_MINUTE", 10),
        rate_limit_per_day=positive_int("RATE_LIMIT_PER_DAY", 100),
        max_comment_chars=positive_int("MAX_COMMENT_CHARS", 1000),
        log_ttl_days=positive_int("LOG_TTL_DAYS", 90),
        max_tokens={
            role: positive_int(f"MAX_TOKENS_{role.upper()}", default)
            for role, default in DEFAULT_MAX_TOKENS.items()
        },
        cache_max_distance=distance("CACHE_MAX_DISTANCE", DEFAULT_CACHE_MAX_DISTANCE),
        excluded_licences=tuple(x.strip() for x in licences.split(",") if x.strip()),
        client_ip_header=(get("CLIENT_IP_HEADER") or "cloudfront-viewer-address").lower(),
        openrouter_key_param=param("OPENROUTER_KEY_PARAM", "openrouter-api-key"),
        turnstile_secret_param=param("TURNSTILE_SECRET_PARAM", "turnstile-secret-key"),
        log_hash_key_param=param("LOG_HASH_KEY_PARAM", "log-hash-key"),
        openrouter_api_key=get("OPENROUTER_API_KEY"),
        turnstile_secret_key=get("TURNSTILE_SECRET_KEY"),
        log_hash_key=get("LOG_HASH_KEY"),
    )
