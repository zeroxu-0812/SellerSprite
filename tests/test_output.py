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


def test_write_products_xlsx(tmp_path):
    from openpyxl import load_workbook
    rows = [{"asin": "A", "price": 10.5, "tags": ["x", "y"]},
            {"asin": "B", "price": 20, "tags": []}]
    d = tmp_path / "out"; d.mkdir()
    write_products(rows, d, "kw")  # 内部会同步产出 products.xlsx
    wb = load_workbook(d / "products.xlsx")
    ws = wb.active
    header = [c.value for c in ws[1]]
    assert "asin" in header and "price" in header
    assert ws.freeze_panes == "A2"           # 冻结首行
    assert ws["A1"].font.bold is True        # 表头加粗
    asins = {ws.cell(row=r, column=header.index("asin") + 1).value for r in range(2, ws.max_row + 1)}
    assert asins == {"A", "B"}


def test_write_report(tmp_path):
    from keyword_output import write_report
    rows = [{"asin": "B0XXX", "title": "Test Product", "price": 9.99,
             "units": 400, "questions": None, "url": None,
             "amz_unit_trend": {"202505": 4000, "202506": 9000}}]
    d = tmp_path / "out"; d.mkdir()
    write_report(rows, {"avg_price": 9.99, "sample_size": 1}, d, "kw")
    text = (d / "report.md").read_text(encoding="utf-8")
    # 转置表头
    assert "| 字段 | 值 |" in text
    # 非空字段 + 中文标签出现
    assert "ASIN" in text and "月销量" in text and "销量趋势(月)" in text
    # 仅保留可获取数据：空字段（提问数/链接）不出现其标签
    assert "提问数" not in text and "链接" not in text
    # 嵌套数据被美化（JSON）
    assert "4000" in text and "9000" in text
