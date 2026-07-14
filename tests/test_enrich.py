# tests/test_enrich.py
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import pytest
from sellersprite_enrich import (AuthExpiredError, BusinessError, build_competitor_url,
                                 is_auth_expired, lookup_asins, parse_quickview)

FIX = Path(__file__).parent / "fixtures" / "quickview_single.json"


def _load_config():
    return {
        "station": "US", "language": "zh_CN", "version": "5.0.4",
        "extension_id": "lnbmbgocenenhhhdojdielgnmeflbnfb", "source": "chrome",
        "quick_view": {"base_url": "https://e.sellersprite.com/v2/extension/competitor-lookup/quick-view",
                       "with_relation": True, "with_sale_trend": True},
    }


def test_build_competitor_url_signature():
    # competitor-lookup 端点：tk 仍对 asins 签名；URL 路径 .../competitor-lookup/US
    url = build_competitor_url(_load_config(), ["B0F1QHNFJP"])
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://e.sellersprite.com/v2/extension/competitor-lookup/US?")
    assert q["tk"] == ["678545.916405"]            # 抓包黄金值
    assert q["asins"] == ["B0F1QHNFJP"]
    assert q["version"] == ["5.0.4"]


def test_parse_quickview_items():
    payload = json.loads(FIX.read_text())
    items = parse_quickview(payload)
    assert len(items) == 1
    assert items[0]["asin"] == "B0GDY15VMN"
    assert items[0]["units"] == 1754
    assert items[0]["amount"] == 140302.45


def test_parse_quickview_normalizes_no_data_sentinel():
    # sellersprite 用 -1 表示"无数据"（真实抓包观测），应归一为 None，避免污染求和/输出
    payload = {"data": {"items": [{"asin": "X", "units": -1, "amount": -1, "profit": -1},
                                  {"asin": "Y", "units": 3537, "amount": 89026.29}]}, "code": "OK"}
    items = parse_quickview(payload)
    assert items[0]["units"] is None
    assert items[0]["amount"] is None
    assert items[0]["profit"] is None
    assert items[1]["units"] == 3537  # 真实值不受影响
    # 负值合法的字段（如 bsr_cr 增长率）不在哨兵清单内，保留
    payload2 = {"data": {"items": [{"asin": "Z", "bsr_cr": -22.37}]}}
    assert parse_quickview(payload2)[0]["bsr_cr"] == -22.37


def test_is_auth_expired():
    assert is_auth_expired({"code": 401}, 200) is True
    assert is_auth_expired({"message": "令牌过期"}, 200) is True
    assert is_auth_expired({"code": "OK"}, 200) is False
    assert is_auth_expired({}, 401) is True
    # 真实抓包观察到的 sellersprite 会话过期码（不只靠 message 文本判定）
    assert is_auth_expired({"code": "ERR_NEED_RE_AUTHORIZED", "message": "令牌过期，请退出再重新登录。"}, 200) is True
    assert is_auth_expired({"code": "ERR_GLOBAL_SESSION_EXPIRED"}, 200) is True


# --- lookup_asins: auth self-heal & business-error skip (Finding 2 & 4) ---

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
    result = lookup_asins(["B0GDY15VMN"], _enrich_config(), tm, {},
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
        lookup_asins(["B0GDY15VMN"], _enrich_config(), tm, {},
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
    result = lookup_asins(["B_OK1", "B_MID", "B_OK2"], cfg, tm, {},
                          _sleep=lambda _t: None, _request=fake_request)

    # The two OK batches collapsed to the same asin key; the mid batch was skipped.
    assert "B_MID" not in result
    assert result == {"B_OK": {"asin": "B_OK"}}
    assert tm.invalidate_calls == 0  # no auth heal on business errors


def test_delay_key_defaults_when_omitted():
    """顺序路径（workers=1）下，config 缺 delay_seconds_min/max 不能 KeyError；
    批间默认延时落在 5..8。"""
    cfg = _enrich_config()
    cfg["quick_view"]["batch_size"] = 1  # force >1 batch → delay path
    cfg["concurrency"] = {"workers": 1}   # 强制顺序路径，批间延时才生效

    def fake_request(url, headers, timeout):
        return 200, {"code": "OK", "data": {"items": [{"asin": "X"}]}}

    slept = []
    result = lookup_asins(["A", "B", "C"], cfg, _StubTokenManager(), {},
                          _sleep=lambda t: slept.append(t), _request=fake_request)
    assert len(result) == 1  # all batches → asin "X"
    # exactly two between-batch sleeps (3 batches), and within default 5..8 range
    assert len(slept) == 2
    assert all(5 <= t <= 8 for t in slept)


def test_lookup_concurrent_merges_all_batches():
    """workers>1 + 多批：并发跑，所有批次结果合并到 result；并发路径不发批间延时 sleep。"""
    cfg = _enrich_config()
    cfg["quick_view"]["batch_size"] = 1   # 每个 ASIN 一批 → 4 批
    cfg["concurrency"] = {"workers": 3}

    seen_urls = []

    def fake_request(url, headers, timeout):
        seen_urls.append(url)
        asin = parse_qs(urlparse(url).query)["asins"][0]
        return 200, {"code": "OK", "data": {"items": [{"asin": asin, "units": 1}]}}

    slept = []
    result = lookup_asins(["A1", "A2", "A3", "A4"], cfg, _StubTokenManager(), {},
                          _sleep=lambda t: slept.append(t), _request=fake_request)
    assert set(result.keys()) == {"A1", "A2", "A3", "A4"}   # 全部合并
    assert len(seen_urls) == 4                              # 每批各请求一次
    assert slept == []                                      # 并发路径不发批间延时
