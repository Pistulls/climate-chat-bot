import dataclasses

from climate_chat.config import load_service_settings
from climate_chat.service.secrets import SecretStore

ENV = {
    "MODEL_EMBEDDING": "openai/text-embedding-3-small",
    "EMBEDDING_DIMENSION": "1536",
    "LOGS_TABLE": "logs",
    "RATELIMITS_TABLE": "ratelimits",
    "MODEL_CLASSIFY": "m",
    "MODEL_FACTS": "m",
    "MODEL_REPLY": "m",
    "MODEL_FALLBACK": "f",
    "APP_ENV": "prod",
    "TURNSTILE_HOSTNAMES": "climate-chat.example.org",
}


def make_settings(**environ):
    from pathlib import Path

    return load_service_settings(environ={**ENV, **environ}, dotenv_path=Path("/none/.env"))


class FakeSSM:
    def __init__(self):
        self.values = {
            "/climate-chat/prod/openrouter-api-key": "sk-ssm",
            "/climate-chat/prod/turnstile-secret-key": "ts-ssm",
            "/climate-chat/prod/log-hash-key": "hash-ssm",
        }
        self.calls = []

    def get_parameter(self, Name, WithDecryption):
        assert WithDecryption is True
        self.calls.append(Name)
        return {"Parameter": {"Value": self.values[Name]}}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_local_value_skips_ssm():
    ssm = FakeSSM()
    store = SecretStore(make_settings(OPENROUTER_API_KEY="sk-local"), ssm_client=ssm)
    assert store.openrouter_key() == "sk-local"
    assert ssm.calls == []


def test_ssm_values_by_parameter_name():
    store = SecretStore(make_settings(), ssm_client=FakeSSM())
    assert (store.openrouter_key(), store.turnstile_secret(), store.log_hash_key()) == (
        "sk-ssm",
        "ts-ssm",
        "hash-ssm",
    )


def test_ssm_value_cached_for_five_minutes():
    ssm, clock = FakeSSM(), Clock()
    store = SecretStore(make_settings(), ssm_client=ssm, clock=clock)
    store.turnstile_secret()
    clock.now += 299
    ssm.values["/climate-chat/prod/turnstile-secret-key"] = "rotated"
    assert store.turnstile_secret() == "ts-ssm"
    assert len(ssm.calls) == 1


def test_ssm_value_refetched_after_expiry():
    ssm, clock = FakeSSM(), Clock()
    store = SecretStore(make_settings(), ssm_client=ssm, clock=clock)
    store.turnstile_secret()
    clock.now += 301
    ssm.values["/climate-chat/prod/turnstile-secret-key"] = "rotated"
    assert store.turnstile_secret() == "rotated"
    assert len(ssm.calls) == 2


def test_ssm_client_created_lazily_from_settings(monkeypatch):
    settings = make_settings()
    ssm = FakeSSM()
    base = dataclasses.replace(settings.base)
    monkeypatch.setattr(type(base), "aws_client", lambda self, service: ssm)
    store = SecretStore(dataclasses.replace(settings, base=base))
    assert store.log_hash_key() == "hash-ssm"


def test_admin_key_from_env_locally_and_ssm_in_the_lambda():
    ssm = FakeSSM()
    ssm.values["/climate-chat/prod/admin-key"] = "admin-ssm"
    assert SecretStore(make_settings(ADMIN_KEY="admin-local"), ssm_client=ssm).admin_key() == (
        "admin-local"
    )
    assert SecretStore(make_settings(), ssm_client=ssm).admin_key() == "admin-ssm"
    assert ssm.calls == ["/climate-chat/prod/admin-key"]
