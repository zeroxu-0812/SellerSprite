# tests/test_output_writer.py
import json
from output_writer import write_products, write_market_overview, prepare_output_dir, clean_row


def test_prepare_output_dir_wipes_previous(tmp_path):
    """扁平单份：每次 prepare 都清空目录内旧文件与子目录，只留最新一次。"""
    base = tmp_path / "out"
    d = prepare_output_dir(base=str(base))
    assert d == base
    (d / "stale.json").write_text("x", encoding="utf-8")          # 上次的旧文件
    sub = d / "old_run"; sub.mkdir(); (sub / "a.json").write_text("y", encoding="utf-8")  # 上次的旧子目录

    d2 = prepare_output_dir(base=str(base))                       # 再次准备 → 清空
    assert d2 == base
    assert not (d2 / "stale.json").exists()
    assert not (d2 / "old_run").exists()
    assert d2.is_dir()                                            # 目录本身保留


def test_write_products_json(tmp_path):
    rows = [{"asin": "A", "price": 9.99, "units": 100}, {"asin": "B", "price": 19.99}]
    d = tmp_path / "out"; d.mkdir()
    write_products(rows, d)
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
    write_products(rows, d)
    item = json.loads((d / "products.json").read_text(encoding="utf-8"))[0]
    assert "questions" not in item and "url" not in item
    assert "bsr_list" not in item
    assert item["asin"] == "B0XX" and item["price"] == 8.99
    assert item["bsr_list__main_rank"] == 5 and item["image_large"] == "https://x"
    # clean_row 单测
    assert clean_row({"a": 1, "b": None, "bsr_list": "[]"}) == {"a": 1}


def test_write_market_overview(tmp_path):
    d = tmp_path / "out"; d.mkdir()
    write_market_overview({"avg_price": 20.0, "sample_size": 3}, d)
    assert (d / "market_overview.json").exists()
    assert not (d / "market_overview.csv").exists()    # 不再产出 CSV
