# tests/test_output_writer.py
import json
from output_writer import write_products, write_market_overview, output_dir_for, clean_row


def test_output_dir_uses_date_prefix(tmp_path):
    d = output_dir_for("asins_2", base=str(tmp_path))
    assert "asins_2" in d.name
    assert "keyword_" not in d.name     # 不再带 keyword_ 前缀


def test_write_products_json(tmp_path):
    rows = [{"asin": "A", "price": 9.99, "units": 100}, {"asin": "B", "price": 19.99}]
    d = tmp_path / "out"; d.mkdir()
    write_products(rows, d, "asins_2")
    json_path = d / "products.json"
    assert json_path.exists()
    assert not (d / "products.csv").exists()     # 不再产出 CSV
    assert not (d / "products.xlsx").exists()    # 不再产出 XLSX
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["asin"] == "A"


def test_products_json_cleaned_dedup_maximal(tmp_path):
    """products.json 去重 + 最大保留：丢空值与冗余原始 JSON，保留其余能爬到的字段。"""
    rows = [{
        "asin": "B0XX", "title": "Magnesium", "price": 8.99, "units": 61,
        "questions": None, "url": None,                        # 空值 → 丢
        "bsr_list": '[{"rank": 5}]',                           # 冗余原始 JSON → 丢（已有 bsr_list__main_rank）
        "bsr_list__main_rank": 5, "image_large": "https://x",  # 保留
    }]
    d = tmp_path / "out"; d.mkdir()
    write_products(rows, d, "asins_1")
    item = json.loads((d / "products.json").read_text(encoding="utf-8"))[0]
    assert "questions" not in item and "url" not in item
    assert "bsr_list" not in item
    assert item["asin"] == "B0XX" and item["price"] == 8.99
    assert item["bsr_list__main_rank"] == 5 and item["image_large"] == "https://x"
    # clean_row 单测
    assert clean_row({"a": 1, "b": None, "bsr_list": "[]"}) == {"a": 1}


def test_write_market_overview(tmp_path):
    d = tmp_path / "out"; d.mkdir()
    write_market_overview({"avg_price": 20.0, "sample_size": 3}, d, "asins_3")
    assert (d / "market_overview.json").exists()
    assert not (d / "market_overview.csv").exists()    # 不再产出 CSV
