"""编排层测试：证明 ASIN → enrich → 折扣 → merge → overview → write 链路接通。

不触网、不需要真实 token：用 monkeypatch 替换 enrich / 折扣抓取，使用真实的
field_merge / market_overview / output_writer 完成端到端落盘验证。"""
import json
import sys
import types
from pathlib import Path

import asin_pipeline
from sellersprite_auth import KeepaTokenManager


# --- stubs ---

_FAKE_LOOKUP = {
    "B0F1QHNFJP": {"asin": "B0F1QHNFJP", "title": "Magnum Solace", "price": 9.99,
                   "rating": 4.4, "reviews": 7800, "units": 38925, "amount": 388860.75},
    "B09PVMTM9W": {"asin": "B09PVMTM9W", "title": "LIFE-FLO", "price": 11.45,
                   "rating": 4.3, "reviews": 3000, "units": 12287, "amount": 143635.03},
}


def _stub_lookup(asins, config, token_manager, base_headers, *args, **kwargs):
    return {a: dict(_FAKE_LOOKUP[a]) for a in asins if a in _FAKE_LOOKUP}


def _stub_detail(items, config):
    for asin in items:
        items[asin]["discount_off_list_pct"] = 30.0
        price = items[asin].get("price")
        if isinstance(price, (int, float)) and price > 0:
            items[asin]["list_price"] = round(price / (1 - 0.30), 2)
        items[asin]["about"] = ["要点一", "要点二"]


# --- 端到端 ---

def test_process_asins_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(asin_pipeline, "lookup_asins", _stub_lookup)
    monkeypatch.setattr(asin_pipeline, "_enrich_detail", _stub_detail)
    monkeypatch.setattr(asin_pipeline, "ROOT", tmp_path)

    config = {"quick_view": {"batch_size": 20}, "concurrency": {"workers": 2}}
    token_manager = KeepaTokenManager(tmp_path / ".token_cache.json")
    # render_html 读 ROOT/products.html 模板；ROOT 被 monkeypatch 到 tmp_path，放一个最小模板
    (tmp_path / "products.html").write_text(
        '<script>const DATA = /*__DATA__*/{}/*__END__*/;</script>', encoding="utf-8")

    result = asin_pipeline.process_asins(["B0F1QHNFJP", "B09PVMTM9W"], config, token_manager)

    assert result["products"] == 2
    out_dir = Path(result["out_dir"])
    assert out_dir == tmp_path / "output"          # 扁平单份：直接 output/，无带日期子目录

    # 仅 JSON 落盘（无 CSV / XLSX / report）+ 自包含 HTML
    assert (out_dir / "products.json").exists()
    assert (out_dir / "market_overview.json").exists()
    assert (out_dir / "products.html").exists()
    assert not (out_dir / "products.csv").exists()
    assert not (out_dir / "products.xlsx").exists()
    assert not (out_dir / "report.md").exists()

    products = json.loads((out_dir / "products.json").read_text(encoding="utf-8"))
    titles = {p["title"] for p in products}
    assert "Magnum Solace" in titles
    # 折扣字段经 stub 注入 + 由 USD 现价反推划线价
    magnum = next(p for p in products if p["asin"] == "B0F1QHNFJP")
    assert magnum["discount_off_list_pct"] == 30.0
    assert magnum["list_price"] == round(9.99 / 0.70, 2)
    # 派生字段：商品链接（url 由 asin 派生）
    assert magnum["url"] == "https://www.amazon.com/dp/B0F1QHNFJP"

    # HTML 自包含渲染：数据已内联注入
    html = (out_dir / "products.html").read_text(encoding="utf-8")
    assert '"asin": "B0F1QHNFJP"' in html
    assert '"sample_size": 2' in html


# --- 输入解析（粘贴 / 文件）---

def test_parse_asins_dedup():
    asins = asin_pipeline.parse_asins("b0f1qhnfjp, B0F1QHNFJP, b09pvmtm9w")
    assert asins == ["B0F1QHNFJP", "B09PVMTM9W"]   # 大写归一 + 去重


def test_parse_asins_handles_mixed_separators():
    asins = asin_pipeline.parse_asins("B0F1QHNFJP B09PVMTM9W\nB06XXP8YRL")
    assert asins == ["B0F1QHNFJP", "B09PVMTM9W", "B06XXP8YRL"]


def test_read_asins_input_from_file(tmp_path):
    f = tmp_path / "asins.txt"
    f.write_text("# 我的清单\nB0F1QHNFJP, b09pvmtm9w\nB06XXP8YRL\n", encoding="utf-8")
    asins = asin_pipeline.read_asins_input(str(f))
    assert asins == ["B0F1QHNFJP", "B09PVMTM9W", "B06XXP8YRL"]


def test_read_asins_input_from_paste():
    asins = asin_pipeline.read_asins_input("B0F1QHNFJP B09PVMTM9W")
    assert asins == ["B0F1QHNFJP", "B09PVMTM9W"]


# --- 多行输入合并（_read_input）---

def test_read_input_single_line(monkeypatch):
    """单行手动输入：select 报告无更多数据 → 行为等同 input()。"""
    monkeypatch.setattr("builtins.input", lambda p: "B0F1QHNFJP B09PVMTM9W")
    monkeypatch.setattr(asin_pipeline.select, "select",
                        lambda r, w, x, t: ([], [], []))
    assert asin_pipeline._read_input("> ") == "B0F1QHNFJP B09PVMTM9W"


def test_read_input_merges_multiline_paste(monkeypatch):
    """多行粘贴：select 先报告有数据、再报告无 → 合并首行与后续行。"""
    monkeypatch.setattr("builtins.input", lambda p: "B0F1QHNFJP")
    states = iter([([sys.stdin], [], []), ([], [], [])])
    monkeypatch.setattr(asin_pipeline.select, "select",
                        lambda r, w, x, t: next(states))
    monkeypatch.setattr(asin_pipeline.sys, "stdin",
                        types.SimpleNamespace(readline=lambda: "B09PVMTM9W\n"))
    merged = asin_pipeline._read_input("> ")
    assert "B0F1QHNFJP" in merged and "B09PVMTM9W" in merged
    assert asin_pipeline.parse_asins(merged) == ["B0F1QHNFJP", "B09PVMTM9W"]
