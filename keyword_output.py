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


def write_market_overview(overview: dict, out_dir: Path, keyword: str) -> None:
    (out_dir / "market_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "market_overview.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for k, v in overview.items():
            writer.writerow([k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v])
