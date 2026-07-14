# output_writer.py
"""JSON 落地：products.json（每商品一行，去重 + 最大保留）+ market_overview.json。"""
import datetime
import json
import re
from pathlib import Path


def _safe_name(label: str) -> str:
    return re.sub(r"[^\w一-龥]+", "_", label).strip("_") or "asins"


def output_dir_for(label: str, base: str = "output") -> Path:
    today = datetime.date.today().isoformat()
    d = Path(base) / f"{_safe_name(label)}_{today}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# 冗余原始 JSON 字段：信息已在扁平化/标量字段里，JSON 串重复，丢弃。
_REDUNDANT_RAW = {"bsr_list", "amz_unit_trends", "trends"}


def _is_empty(v) -> bool:
    if v is None or v == "" or v == [] or v == {}:
        return True
    # 字符串化的空容器（flatten 后 list/dict 变 JSON 串）："{}"/"[]"/"null"
    if isinstance(v, str) and v.strip() in {"{}", "[]", "null"}:
        return True
    return False


def clean_row(row: dict) -> dict:
    """去重 + 最大保留：丢弃空值，以及与扁平化/标量字段重复的原始 JSON（bsr_list 等）。
    其余能爬到的字段全部保留。"""
    return {k: v for k, v in row.items()
            if k not in _REDUNDANT_RAW and not _is_empty(v)}


def write_products(rows: list, out_dir: Path, label: str) -> None:
    """products.json：去重 + 最大保留的清洗版（丢空值与冗余原始 JSON）。"""
    cleaned = [clean_row(r) for r in rows]
    (out_dir / "products.json").write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def write_market_overview(overview: dict, out_dir: Path, label: str) -> None:
    (out_dir / "market_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
