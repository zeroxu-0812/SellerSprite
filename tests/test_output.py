# tests/test_output.py
import csv
import json
from pathlib import Path
from keyword_output import write_products, write_market_overview, output_dir_for


def test_output_dir_uses_date_prefix(tmp_path):
    d = output_dir_for("yoga mat", base=str(tmp_path))
    # _safe_name replaces spaces with underscores
    assert "yoga_mat" in d.name
    assert "keyword_" in d.name


def test_write_products_csv_json(tmp_path):
    rows = [{"asin": "A", "price": "10(亚马逊) / 12(卖家精灵)"}, {"asin": "B", "price": "9"}]
    d = tmp_path / "out"
    d.mkdir()
    write_products(rows, d, "yoga mat")
    csv_path = d / "products.csv"
    json_path = d / "products.json"
    assert csv_path.exists() and json_path.exists()
    data = json.loads(json_path.read_text())
    assert len(data) == 2
    # CSV is utf-8-sig (Excel-friendly); strip BOM on read
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))
        assert reader[0]["asin"] == "A"


def test_write_market_overview(tmp_path):
    d = tmp_path / "out"; d.mkdir()
    write_market_overview({"avg_price": 20.0, "sample_size": 3}, d, "kw")
    assert (d / "market_overview.csv").exists()
    assert (d / "market_overview.json").exists()
