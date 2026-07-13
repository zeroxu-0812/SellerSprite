"""编排层测试：证明 search → enrich → merge → overview → write 链路接通。

不触网、不需要真实 token：用 monkeypatch 替换 search/enrich，使用真实的
field_merge / market_overview / keyword_output 完成端到端落盘验证。
"""
from pathlib import Path

import keyword_pipeline
from sellersprite_auth import KeepaTokenManager


# --- stubs ---

_FAKE_PRODUCTS = [
    {"asin": "B00AAA111", "title": "Yoga Mat Pro", "price": 29.99, "rating": 4.5, "reviews": 1200},
    {"asin": "B00BBB222", "title": "Yoga Mat Lite", "price": 19.99, "rating": 4.2, "reviews": 800},
]

_FAKE_ENRICH = {
    "B00AAA111": {"asin": "B00AAA111", "units": 1000, "amount": 29990.0},
    "B00BBB222": {"asin": "B00BBB222", "units": 500, "amount": 9995.0},
}


def _stub_search(keyword, config):
    return [dict(p) for p in _FAKE_PRODUCTS]


def _stub_enrich(asins, config, token_manager, base_headers, *args, **kwargs):
    return {a: dict(_FAKE_ENRICH[a]) for a in asins if a in _FAKE_ENRICH}


# --- test ---

def test_process_keyword_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(keyword_pipeline, "search_amazon_paginated", _stub_search)
    monkeypatch.setattr(keyword_pipeline, "lookup_asins", _stub_enrich)

    # 把输出根目录重定向到 tmp，避免污染仓库 output/
    monkeypatch.setattr(keyword_pipeline, "ROOT", tmp_path)

    config = {
        "quick_view": {"batch_size": 20, "delay_seconds_min": 0, "delay_seconds_max": 0},
        "amazon": {"max_pages": 1},
    }
    token_manager = KeepaTokenManager(tmp_path / ".token_cache.json")

    result = keyword_pipeline.process_keyword("test kw", config, token_manager)

    # 返回值契约
    assert result["products"] == 2
    out_dir = Path(result["out_dir"])
    assert out_dir.exists()
    assert out_dir.parent == tmp_path / "output"
    assert out_dir.name.startswith("keyword_test_kw_")

    # 真实落盘校验
    assert (out_dir / "products.csv").exists()
    assert (out_dir / "products.json").exists()
    assert (out_dir / "market_overview.json").exists()
    assert (out_dir / "market_overview.csv").exists()

    # products.csv 至少含表头 + 2 行数据
    csv_text = (out_dir / "products.csv").read_text(encoding="utf-8-sig")
    data_lines = [ln for ln in csv_text.splitlines()[1:] if ln.strip()]
    assert len(data_lines) == 2

    # 单源 flatten 后增强字段仍在（competitor-lookup 数据）
    assert "1000" in csv_text or "29990" in csv_text


# --- ASIN 模式（competitor-lookup）---

def test_is_asin_list():
    assert keyword_pipeline.is_asin_list("B0F1QHNFJP") is True
    assert keyword_pipeline.is_asin_list("B0F1QHNFJP, B09PVMTM9W") is True
    assert keyword_pipeline.is_asin_list("B0F1QHNFJP B09PVMTM9W,B06XXP8YRL") is True
    assert keyword_pipeline.is_asin_list("magnesium cream") is False      # 关键词
    assert keyword_pipeline.is_asin_list("B0F1QHNFJP extra") is False     # 混了非 ASIN
    assert keyword_pipeline.is_asin_list("") is False


def test_parse_asin_list_dedup():
    asins = keyword_pipeline.parse_asin_list("b0f1qhnfjp, B0F1QHNFJP, b09pvmtm9w")
    assert asins == ["B0F1QHNFJP", "B09PVMTM9W"]   # 大写归一 + 去重


_FAKE_LOOKUP = {
    "B0F1QHNFJP": {"asin": "B0F1QHNFJP", "title": "Magnum Solace", "price": 117.53,
                   "rating": 4.4, "reviews": 7800, "units": 38925, "amount": 388860.75},
    "B09PVMTM9W": {"asin": "B09PVMTM9W", "title": "LIFE-FLO", "price": 11.45,
                   "rating": 4.3, "reviews": 3000, "units": 12287, "amount": 143635.03},
}


def _stub_lookup(asins, config, token_manager, base_headers, *args, **kwargs):
    return {a: dict(_FAKE_LOOKUP[a]) for a in asins if a in _FAKE_LOOKUP}


def test_process_asins_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(keyword_pipeline, "lookup_asins", _stub_lookup)
    monkeypatch.setattr(keyword_pipeline, "ROOT", tmp_path)
    config = {"quick_view": {"batch_size": 20, "delay_seconds_min": 0, "delay_seconds_max": 0}}
    token_manager = KeepaTokenManager(tmp_path / ".token_cache.json")

    result = keyword_pipeline.process_asins(["B0F1QHNFJP", "B09PVMTM9W"], config, token_manager)

    assert result["products"] == 2
    out_dir = Path(result["out_dir"])
    assert "asins_2" in out_dir.name                  # output_dir_for 会加 keyword_ 前缀
    assert (out_dir / "products.csv").exists()
    assert (out_dir / "market_overview.json").exists()
    # competitor-lookup 单源数据：title/price/units 都在（单格单值，无来源标注）
    csv_text = (out_dir / "products.csv").read_text(encoding="utf-8-sig")
    assert "Magnum Solace" in csv_text
    assert "38925" in csv_text

