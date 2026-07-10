# tests/test_enrich.py
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import pytest
from sellersprite_enrich import (AuthExpiredError, BusinessError, build_quickview_url,
                                 enrich_asins, is_auth_expired, parse_quickview)

FIX = Path(__file__).parent / "fixtures" / "quickview_single.json"


def _load_config():
    return {
        "station": "US", "language": "zh_CN", "version": "5.0.4",
        "extension_id": "lnbmbgocenenhhhdojdielgnmeflbnfb", "source": "chrome",
        "quick_view": {"base_url": "https://e.sellersprite.com/v2/extension/competitor-lookup/quick-view",
                       "with_relation": True, "with_sale_trend": True},
    }


def test_build_url_signature_batch():
    url = build_quickview_url(_load_config(), ["B091FX694F", "B00NUQT3R2"])
    q = parse_qs(urlparse(url).query)
    assert q["tk"] == ["82711.451123"]            # 抓包黄金值
    assert q["asins"] == ["B091FX694F,B00NUQT3R2"]
    assert q["version"] == ["5.0.4"]
    assert q["withRelation"] == ["true"]


def test_parse_quickview_items():
    payload = json.loads(FIX.read_text())
    items = parse_quickview(payload)
    assert len(items) == 1
    assert items[0]["asin"] == "B0GDY15VMN"
    assert items[0]["units"] == 1754
    assert items[0]["amount"] == 140302.45


def test_is_auth_expired():
    assert is_auth_expired({"code": 401}, 200) is True
    assert is_auth_expired({"message": "令牌过期"}, 200) is True
    assert is_auth_expired({"code": "OK"}, 200) is False
    assert is_auth_expired({}, 401) is True
    # 真实抓包观察到的 sellersprite 会话过期码（不只靠 message 文本判定）
    assert is_auth_expired({"code": "ERR_NEED_RE_AUTHORIZED", "message": "令牌过期，请退出再重新登录。"}, 200) is True
    assert is_auth_expired({"code": "ERR_GLOBAL_SESSION_EXPIRED"}, 200) is True


# --- enrich_asins: auth self-heal & business-error skip (Finding 2 & 4) ---

def _enrich_config():
    return {
        "station": "US", "language": "zh_CN", "version": "5.0.4",
        "extension_id": "lnbmbgocenenhhhdojdielgnmeflbnfb", "source": "chrome",
        "quick_view": {"base_url": "https://e.sellersprite.com/v2/extension/competitor-lookup/quick-view",
                       "batch_size": 20, "retry_attempts": 2},
    }


class _StubTokenManager:
    """Minimal stand-in for KeepaTokenManager: records heal calls."""

    def __init__(self):
        self.invalidate_calls = 0
        self.refresh_calls = 0

    def get_valid_headers(self, base):
        h = dict(base)
        h["x-test"] = "ok"
        return h

    def invalidate_cache(self):
        self.invalidate_calls += 1

    def refresh_from_command(self):
        self.refresh_calls += 1


def test_auth_self_heal_then_success():
    """First call returns auth-expired; heal happens; second call succeeds.
    invalidate_cache + refresh_from_command each called exactly once."""
    success_payload = {"code": "OK", "data": {"items": [{"asin": "B0GDY15VMN", "units": 1754}]}}
    calls = {"n": 0}

    def fake_request(url, headers, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return 401, {"code": "TOKEN_EXPIRED", "message": "令牌过期"}
        return 200, success_payload

    tm = _StubTokenManager()
    result = enrich_asins(["B0GDY15VMN"], _enrich_config(), tm, {},
                          _sleep=lambda _t: None, _request=fake_request)

    assert result == {"B0GDY15VMN": {"asin": "B0GDY15VMN", "units": 1754}}
    assert tm.invalidate_calls == 1
    assert tm.refresh_calls == 1
    assert calls["n"] == 2  # healed exactly once


def test_auth_expired_persists_raises():
    """Two consecutive auth-expiry responses (before and after the single heal)
    must raise AuthExpiredError, not retry indefinitely."""
    def fake_request(url, headers, timeout):
        return 401, {"code": "TOKEN_EXPIRED", "message": "令牌过期"}

    tm = _StubTokenManager()
    with pytest.raises(AuthExpiredError):
        enrich_asins(["B0GDY15VMN"], _enrich_config(), tm, {},
                      _sleep=lambda _t: None, _request=fake_request)
    # heal attempted exactly once before giving up
    assert tm.invalidate_calls == 1
    assert tm.refresh_calls == 1


def test_business_error_skips_batch_and_continues():
    """A business error on one batch must be skipped; earlier & later batches
    keep their results. Multi-batch run exercises the delay-key defaults too."""
    cfg = _enrich_config()
    cfg["quick_view"]["batch_size"] = 1  # one ASIN per batch

    def fake_request(url, headers, timeout):
        # middle ASIN triggers a business error
        if "B_MID" in url:
            return 200, {"code": "BUSINESS_FAIL", "message": "限流"}
        return 200, {"code": "OK", "data": {"items": [{"asin": "B_OK"}]}}

    tm = _StubTokenManager()
    result = enrich_asins(["B_OK1", "B_MID", "B_OK2"], cfg, tm, {},
                          _sleep=lambda _t: None, _request=fake_request)

    # The two OK batches collapsed to the same asin key; the mid batch was skipped.
    assert "B_MID" not in result
    assert result == {"B_OK": {"asin": "B_OK"}}
    assert tm.invalidate_calls == 0  # no auth heal on business errors


def test_delay_key_defaults_when_omitted():
    """config without delay_seconds_min/max must not KeyError on a multi-batch run."""
    cfg = _enrich_config()
    cfg["quick_view"]["batch_size"] = 1  # force >1 batch → delay path

    def fake_request(url, headers, timeout):
        return 200, {"code": "OK", "data": {"items": [{"asin": "X"}]}}

    slept = []
    result = enrich_asins(["A", "B", "C"], cfg, _StubTokenManager(), {},
                          _sleep=lambda t: slept.append(t), _request=fake_request)
    assert len(result) == 1  # all batches → asin "X"
    # exactly two between-batch sleeps (3 batches), and within default 5..8 range
    assert len(slept) == 2
    assert all(5 <= t <= 8 for t in slept)
