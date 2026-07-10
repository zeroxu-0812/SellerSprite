# tests/test_enrich.py
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from sellersprite_enrich import build_quickview_url, is_auth_expired, parse_quickview

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
