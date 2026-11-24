import io
import json
import urllib.error
import urllib.parse
from datetime import UTC, datetime

import pytest
from botocore.exceptions import ClientError

from climate_chat.service.api import ApiError
from climate_chat.service.guards import RateLimiter, client_ip, user_hash, verify_turnstile

# --- client_ip ---


def test_client_ip_ipv4():
    assert client_ip(
        {"cloudfront-viewer-address": "203.0.113.9:443"}, "cloudfront-viewer-address"
    ) == ("203.0.113.9")


def test_client_ip_ipv6():
    headers = {"cloudfront-viewer-address": "2001:db8::1:46532"}
    assert client_ip(headers, "cloudfront-viewer-address") == "2001:db8::1"


def test_client_ip_header_name_case_insensitive():
    headers = {"CloudFront-Viewer-Address": "203.0.113.9:443"}
    assert client_ip(headers, "cloudfront-viewer-address") == "203.0.113.9"


@pytest.mark.parametrize("headers", [{}, {"cloudfront-viewer-address": ""}])
def test_client_ip_missing_is_local(headers):
    assert client_ip(headers, "cloudfront-viewer-address") == "local"


# --- verify_turnstile ---


class FakeResponse(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode())
        self.status = status

    @classmethod
    def raw(cls, data, status=200):
        response = cls({}, status)
        response.seek(0)
        response.truncate()
        response.write(data)
        response.seek(0)
        return response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


HOSTS = ("climate-chat.example.org",)
PASS = {"success": True, "hostname": "climate-chat.example.org", "action": "chat"}


class FakeUrlopen:
    def __init__(self, payload=None, status=200, error=None):
        self.payload = payload if payload is not None else dict(PASS)
        self.status, self.error = status, error
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return FakeResponse(self.payload, self.status)


def test_turnstile_success():
    verify_turnstile("tok", "secret", "203.0.113.9", hostnames=HOSTS, urlopen=FakeUrlopen())


def test_turnstile_failure_is_403():
    fake = FakeUrlopen({"success": False, "error-codes": ["invalid-input-response"]})
    with pytest.raises(ApiError) as info:
        verify_turnstile("tok", "secret", "203.0.113.9", hostnames=HOSTS, urlopen=fake)
    assert (info.value.status, info.value.code) == (403, "turnstile_failed")


@pytest.mark.parametrize(
    "error",
    [TimeoutError(), urllib.error.URLError("down"), ConnectionResetError()],
)
def test_turnstile_unreachable_is_503(error):
    with pytest.raises(ApiError) as info:
        verify_turnstile(
            "tok", "secret", "203.0.113.9", hostnames=HOSTS, urlopen=FakeUrlopen(error=error)
        )
    assert (info.value.status, info.value.code) == (503, "unavailable")


def test_turnstile_server_error_is_503():
    error = urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b""))
    with pytest.raises(ApiError) as info:
        verify_turnstile(
            "tok", "secret", "203.0.113.9", hostnames=HOSTS, urlopen=FakeUrlopen(error=error)
        )
    assert info.value.status == 503


def test_turnstile_bad_json_is_503():
    class Garbled(FakeUrlopen):
        def __call__(self, request, timeout):
            return FakeResponse.raw(b"<html>not json</html>")

    with pytest.raises(ApiError) as info:
        verify_turnstile("tok", "secret", "203.0.113.9", hostnames=HOSTS, urlopen=Garbled())
    assert info.value.status == 503


def test_turnstile_sends_secret_and_ip():
    fake = FakeUrlopen()
    verify_turnstile("tok", "secret", "203.0.113.9", hostnames=HOSTS, urlopen=fake, timeout=2.5)
    request, timeout = fake.requests[0]
    assert request.full_url == "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    assert request.get_method() == "POST"
    assert urllib.parse.parse_qs(request.data.decode()) == {
        "secret": ["secret"],
        "response": ["tok"],
        "remoteip": ["203.0.113.9"],
    }
    assert timeout == 2.5


def test_turnstile_omits_local_ip():
    fake = FakeUrlopen()
    verify_turnstile("tok", "secret", "local", hostnames=HOSTS, urlopen=fake)
    assert "remoteip" not in urllib.parse.parse_qs(fake.requests[0][0].data.decode())


def _refused(payload, hostnames=HOSTS, token="tok"):
    fake = FakeUrlopen(payload)
    with pytest.raises(ApiError) as info:
        verify_turnstile(token, "secret", "203.0.113.9", hostnames=hostnames, urlopen=fake)
    assert (info.value.status, info.value.code) == (403, "turnstile_failed")
    return fake


def test_turnstile_long_token_is_403_without_call():
    assert _refused(PASS, token="x" * 2049).requests == []
    verify_turnstile("x" * 2048, "secret", "203.0.113.9", hostnames=HOSTS, urlopen=FakeUrlopen())


def test_turnstile_wrong_hostname_is_403():
    _refused({**PASS, "hostname": "evil.example"})
    _refused({k: v for k, v in PASS.items() if k != "hostname"})


def test_turnstile_hostname_match_ignores_case():
    payload = {**PASS, "hostname": "Climate-Chat.Example.ORG"}
    verify_turnstile("tok", "secret", "203.0.113.9", hostnames=HOSTS, urlopen=FakeUrlopen(payload))


def test_turnstile_wrong_action_is_403():
    _refused({**PASS, "action": "login"})


def test_turnstile_missing_action_is_403_for_real_keys():
    _refused({k: v for k, v in PASS.items() if k != "action"})
    _refused({**PASS, "action": "", "metadata": {"result_with_testing_key": False}})


def test_turnstile_missing_action_allowed_with_test_key():
    """Cloudflare's test secret reports hostname example.com and no action at all."""
    payload = {
        "success": True,
        "hostname": "example.com",
        "metadata": {"result_with_testing_key": True},
    }
    verify_turnstile(
        "tok", "secret", "local", hostnames=("example.com",), urlopen=FakeUrlopen(payload)
    )


def test_turnstile_test_key_still_needs_an_allowed_hostname():
    payload = {
        "success": True,
        "hostname": "example.com",
        "metadata": {"result_with_testing_key": True},
    }
    _refused(payload)


# --- RateLimiter ---

NOW = datetime(2026, 11, 24, 14, 5, 30, tzinfo=UTC)


class FakeDynamo:
    """update_item with ADD/condition semantics on one numeric attribute."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.calls = []

    def update_item(self, **kw):
        self.calls.append(kw)
        key = kw["Key"]["pk"]["S"]
        limit = int(kw["ExpressionAttributeValues"][":limit"]["N"])
        item = self.items.setdefault(key, {"count": 0})
        if item["count"] >= limit:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "no"}},
                "UpdateItem",
            )
        item["count"] += 1
        item.setdefault("expires_at", int(kw["ExpressionAttributeValues"][":exp"]["N"]))


def limiter(fake, per_minute=2, per_day=3):
    return RateLimiter(fake, "ratelimits", per_minute=per_minute, per_day=per_day)


def test_rate_limit_allows_under_limit():
    fake = FakeDynamo()
    limiter(fake).check("203.0.113.9", NOW)
    limiter(fake).check("203.0.113.9", NOW)


def test_rate_limit_minute_exceeded_is_429():
    fake = FakeDynamo()
    rl = limiter(fake, per_minute=2, per_day=100)
    rl.check("203.0.113.9", NOW)
    rl.check("203.0.113.9", NOW)
    with pytest.raises(ApiError) as info:
        rl.check("203.0.113.9", NOW)
    assert (info.value.status, info.value.code) == (429, "rate_limited")


def test_rate_limit_new_minute_resets():
    fake = FakeDynamo()
    rl = limiter(fake, per_minute=1, per_day=100)
    rl.check("203.0.113.9", NOW)
    rl.check("203.0.113.9", NOW.replace(minute=6))


def test_rate_limit_day_exceeded_is_429():
    fake = FakeDynamo()
    rl = limiter(fake, per_minute=100, per_day=2)
    rl.check("203.0.113.9", NOW)
    rl.check("203.0.113.9", NOW.replace(hour=15))
    with pytest.raises(ApiError) as info:
        rl.check("203.0.113.9", NOW.replace(hour=16))
    assert info.value.status == 429


def test_rate_limit_ips_counted_separately():
    fake = FakeDynamo()
    rl = limiter(fake, per_minute=1)
    rl.check("203.0.113.9", NOW)
    rl.check("198.51.100.7", NOW)


def test_rate_limit_keys_and_ttl():
    fake = FakeDynamo()
    limiter(fake).check("203.0.113.9", NOW)
    assert fake.items == {
        "ip#203.0.113.9#m#2026-11-24T14:05": {
            "count": 1,
            "expires_at": int(datetime(2026, 11, 24, 14, 6, tzinfo=UTC).timestamp()),
        },
        "ip#203.0.113.9#d#2026-11-24": {
            "count": 1,
            "expires_at": int(datetime(2026, 11, 25, tzinfo=UTC).timestamp()),
        },
    }
    assert all(c["TableName"] == "ratelimits" for c in fake.calls)


def test_rate_limit_other_dynamo_errors_propagate():
    class Broken:
        def update_item(self, **kw):
            raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "U")

    with pytest.raises(ClientError):
        limiter(Broken()).check("203.0.113.9", NOW)


# --- user_hash ---


def test_user_hash_stable_within_month():
    assert user_hash("k", "203.0.113.9", NOW) == user_hash(
        "k", "203.0.113.9", NOW.replace(day=1, hour=0)
    )


def test_user_hash_changes_across_months():
    assert user_hash("k", "203.0.113.9", NOW) != user_hash(
        "k", "203.0.113.9", NOW.replace(month=12)
    )


def test_user_hash_depends_on_key_and_ip():
    base = user_hash("k", "203.0.113.9", NOW)
    assert user_hash("other", "203.0.113.9", NOW) != base
    assert user_hash("k", "203.0.113.10", NOW) != base


def test_user_hash_is_16_hex():
    value = user_hash("k", "203.0.113.9", NOW)
    assert len(value) == 16
    int(value, 16)


def test_user_hash_matches_design_formula():
    import hashlib
    import hmac

    expected = hmac.new(b"k", b"2026-11|203.0.113.9", hashlib.sha256).hexdigest()[:16]
    assert user_hash("k", "203.0.113.9", NOW) == expected
