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


# ---- 易读报告 report.md：转置表格（字段竖列）、仅非空、嵌套美化、中文标签 ----

FIELD_LABELS = {
    "asin": "ASIN", "parent": "父ASIN", "title": "标题", "brand": "品牌",
    "price": "价格(USD)", "currency": "货币", "symbol": "货币符号",
    "units": "月销量", "month_units": "月出单", "units_growth": "销量增长%",
    "amount": "销售额", "amount_growth": "销售额增长%", "sub_total_amount": "子体销售额",
    "profit": "利润", "fba": "FBA费",
    "rating": "评分", "reviews": "评论数", "reviews_delta": "评论增长数",
    "reviews_rate": "评论增长率%", "questions": "提问数",
    "bsr": "BSR排名", "bsr_list__main_rank": "主类目排名", "bsr_list__sub_rank": "子类目排名",
    "bsr_label": "主类目", "bsr_id": "类目ID", "bsr_cr": "BSR变化率%", "bsr_cv": "BSR变化值",
    "lqs": "Listing质量分", "node_label_path": "类目路径", "node_label_paths_locale": "类目(中)",
    "sellers": "卖家数", "seller_name": "卖家", "seller_type": "卖家类型", "seller_id": "卖家ID",
    "seller_dto__business_name": "卖家公司", "seller_dto__nation_name": "卖家国别",
    "seller_dto__nation_code": "卖家国别码", "seller_dto__business_address": "卖家地址",
    "available": "上架时间戳", "available_days": "上架天数",
    "weight": "商品重量", "pkg_weight": "包装重量", "dimension": "商品尺寸",
    "pkg_dimensions": "包装尺寸", "pkg_dimension_type": "包装类型码",
    "pkg_dimension_type_cn_label": "包装类型", "pkg_volume_weights": "体积重",
    "variations": "变体数", "sku": "SKU", "badges": "标签",
    "image": "封面图(200px)", "image_zoom": "封面图(600px)", "image_large": "封面图(高清)", "url": "链接",
    "amz_unit_trend": "销量趋势(月)",
}

# 报告里跳过的原始重复字段（信息已在扁平化/标量字段里，避免冗余）
_REPORT_SKIP = {"bsr_list", "amz_unit_trends", "trends"}

_REPORT_ORDER = [
    "asin", "parent", "title", "brand", "url",
    "price", "currency", "units", "month_units", "units_growth", "amount", "amount_growth",
    "sub_total_amount", "profit", "fba",
    "rating", "reviews", "reviews_delta", "reviews_rate", "questions",
    "bsr", "bsr_list__main_rank", "bsr_list__sub_rank", "bsr_label", "bsr_id", "bsr_cr", "bsr_cv", "lqs",
    "node_label_path", "node_label_paths_locale",
    "sellers", "seller_name", "seller_type", "seller_id",
    "seller_dto__business_name", "seller_dto__nation_name", "seller_dto__nation_code",
    "seller_dto__business_address",
    "available", "available_days",
    "weight", "pkg_weight", "dimension", "pkg_dimensions", "pkg_dimension_type",
    "pkg_dimension_type_cn_label", "pkg_volume_weights", "variations", "sku", "badges",
    "image", "image_zoom", "image_large", "amz_unit_trend",
]


def _is_empty(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _readable_cell(v) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, indent=2).replace("\n", "<br>")
    return str(v)


def write_report(rows: list, overview: dict, out_dir: Path, keyword: str) -> None:
    """易读 Markdown 报告：每个商品一个转置表格（字段名竖列 | 值），仅含非空字段。"""
    lines = [f"# {keyword} · 数据报告", ""]
    if overview:
        lines.append(f"> 样本 {overview.get('sample_size')} | 均价 {overview.get('avg_price')} | "
                     f"均评分 {overview.get('avg_rating')} | 均评论 {overview.get('avg_reviews')} | "
                     f"总销量 {overview.get('total_units')} | 总销售额 {overview.get('total_amount')} | "
                     f"Top10集中度 {overview.get('top10_units_share')}")
        lines.append("")
    for idx, r in enumerate(rows, 1):
        title = (r.get("title") or r.get("asin") or f"商品{idx}")
        lines.append(f"## {idx}. {r.get('asin', '')} — {str(title)[:60]}")
        lines.append("")
        lines.append("| 字段 | 值 |")
        lines.append("|---|---|")
        ordered = [k for k in _REPORT_ORDER if k in r]
        ordered += sorted(k for k in r if k not in _REPORT_ORDER)
        seen = set()
        for k in ordered:
            if k in seen or k in _REPORT_SKIP:
                continue
            seen.add(k)
            v = r.get(k)
            if _is_empty(v):
                continue
            lines.append(f"| {FIELD_LABELS.get(k, k)} | {_readable_cell(v)} |")
        lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
