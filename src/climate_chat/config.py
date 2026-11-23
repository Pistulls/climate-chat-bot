"""Settings shared by ingestion and the service.

Values come from the process environment first, then from the repo's `.env` file
(local development only; gitignored). The Lambda gets the same names from Terraform
(Infrastructure/app/hosting.tf), minus the secrets, which it reads from SSM.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENVS = ("dev", "prod")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# SSM SecureString parameters created by Infrastructure/bootstrap.
SSM_PARAMS = {
    "ingest_openrouter": "/climate-chat/ingest/openrouter-api-key",
    "dev_openrouter": "/climate-chat/dev/openrouter-api-key",
    "prod_openrouter": "/climate-chat/prod/openrouter-api-key",
    "prod_turnstile": "/climate-chat/prod/turnstile-secret-key",
}


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


def load_settings(
    env: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Settings:
    """Build Settings. `env` overrides APP_ENV and picks that env's vector bucket."""
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
