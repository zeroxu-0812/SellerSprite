# output_writer.py
"""扁平单份 JSON 落地：每次运行前清空 output，只保留最新一次的
products.json + market_overview.json（products.html 由 html_render 另写）。"""
import json
import shutil
from pathlib import Path


def prepare_output_dir(base: str = "output") -> Path:
    """扁平单份输出目录：清空 base 内所有旧文件 / 子目录后返回 base。
    保证 output 永远只含最新一次结果，代码库干净。"""
    d = Path(base)
    d.mkdir(parents=True, exist_ok=True)
    for child in d.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
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


def write_products(rows: list, out_dir: Path) -> None:
    """products.json：去重 + 最大保留的清洗版（丢空值与冗余原始 JSON）。"""
    cleaned = [clean_row(r) for r in rows]
    (out_dir / "products.json").write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def write_market_overview(overview: dict, out_dir: Path) -> None:
    (out_dir / "market_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
