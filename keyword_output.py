# keyword_output.py
"""CSV/JSON 落地。"""
import csv
import datetime
import json
import re
from pathlib import Path


def _safe_name(keyword: str) -> str:
    return re.sub(r"[^\w一-龥]+", "_", keyword).strip("_") or "keyword"


def output_dir_for(keyword: str, base: str = "output") -> Path:
    today = datetime.date.today().isoformat()
    d = Path(base) / f"keyword_{_safe_name(keyword)}_{today}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_products(rows: list, out_dir: Path, keyword: str) -> None:
    json_path = out_dir / "products.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out_dir / "products.csv"
    headers = sorted({k for r in rows for k in r.keys()})
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow({h: r.get(h, "") for h in headers})

    write_products_xlsx(rows, out_dir)  # 同步产出 Excel 表格


def _xlsx_cell(v):
    """列表/字典转 JSON 字符串，便于在表格单元格里展示。"""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def write_products_xlsx(rows: list, out_dir: Path) -> None:
    """Excel 表格：表头作列（加粗 + 冻结首行），每商品一行，全字段。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "products"
    headers = sorted({k for r in rows for k in r.keys()})
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for r in rows:
        ws.append([_xlsx_cell(r.get(h, "")) for h in headers])
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(max(len(h) + 2, 10), 40)
    wb.save(out_dir / "products.xlsx")


def write_market_overview(overview: dict, out_dir: Path, keyword: str) -> None:
    (out_dir / "market_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "market_overview.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for k, v in overview.items():
            writer.writerow([k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v])
