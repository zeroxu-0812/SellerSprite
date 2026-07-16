# asin_pipeline.py
"""编排 + CLI 交互入口：输入 ASIN（粘贴或文件）→ competitor-lookup 并发增强 → JSON 落地。"""
import json
import os
import re
import select
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sellersprite_auth import KeepaTokenManager
from amazon_search import fetch_product_detail
from sellersprite_enrich import lookup_asins, AuthExpiredError
from field_merge import flatten_record, large_image_url, product_url, available_date, trend_pairs_to_map
from html_render import render_html
from market_overview import derive_market_overview
from output_writer import prepare_output_dir, write_products, write_market_overview

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def load_env():
    """从 .env 读环境变量（零依赖实现）。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _print_summary(rows: list) -> None:
    """终端直接打印爬取数据摘要表（关键字段，USD）。"""
    cols = [("ASIN", "asin", 11), ("标题", "title", 26), ("现价$", "price", 7),
            ("折扣前$", "list_price", 8), ("折扣%", "discount_off_list_pct", 6),
            ("月销", "units", 7), ("销售额$", "amount", 11), ("评分", "rating", 5),
            ("评论", "reviews", 6), ("卖家", "seller_name", 14)]

    def cell(r, key):
        v = r.get(key)
        if v is None or v == "":
            return ""
        s = str(v)
        if key == "title":
            s = s[:24]
        return s

    header = [name for name, _, _ in cols]
    table = [[cell(r, k) for _, k, _ in cols] for r in rows]
    widths = [max(len(header[i]), max((len(row[i]) for row in table), default=0), w)
              for i, (_, _, w) in enumerate(cols)]

    def fmt(row):
        return "  ".join(row[i][:widths[i]].ljust(widths[i]) for i in range(len(cols)))

    print()
    print(fmt(header))
    print("  ".join("-" * widths[i] for i in range(len(cols))))
    for row in table:
        print(fmt(row))


def _emit_rows(rows: list) -> dict:
    """统一收尾：派生市场总览 + 清空旧输出 + 落地 JSON + 渲染 HTML + 打印摘要。
    rows 为扁平后的单源商品行。每次只保留最新一次输出（扁平单份）。"""
    for r in rows:
        r["image_large"] = large_image_url(r.get("image"))        # 派生 1500px 高清封面链接
        r["url"] = product_url(r.get("asin"))                     # 派生商品详情页跳转链接
        r["available_date"] = available_date(r.get("available"))  # 上架时间戳 → yyyy-mm-dd
        r["parent_unit_trend"] = trend_pairs_to_map(r.get("trends"))  # 派生父体月销趋势（trends → {YYYYMM:n}）
    overview = derive_market_overview(rows)
    out_dir = prepare_output_dir(base=str(ROOT / "output"))   # 清空上一次输出
    write_products(rows, out_dir)
    write_market_overview(overview, out_dir)
    render_html(rows, overview, ROOT / "products.html", out_dir / "products.html")
    _print_summary(rows)
    print(f"\n📊 市场总览（样本 {overview['sample_size']}）:")
    print(f"   均价 {overview['avg_price']} | 均评分 {overview['avg_rating']} | 均评论 {overview['avg_reviews']}")
    print(f"   样本总销量 {overview['total_units']} | 总销售额 {overview['total_amount']}")
    print(f"   Top10 集中度 {overview['top10_units_share']}")
    print(f"💾 已保存到 {out_dir}（products.json + market_overview.json + products.html，已清空上次输出）")
    print(f"🌐 双击查看: {out_dir / 'products.html'}")
    return {"products": len(rows), "out_dir": str(out_dir)}


def _enrich_detail(items: dict, config: dict) -> None:
    """并发抓亚马逊详情页拿【折扣% + About this item】。折扣% 用 competitor 准确 USD 现价
    反推折扣前价；about 取 feature-bullets 要点。best-effort，单个失败不影响整体。"""
    workers = max(1, int((config.get("concurrency") or {}).get("workers", 3)))
    asins = [a for a in items if a]
    if not asins:
        return
    print(f"   亚马逊详情页(折扣+About): {len(asins)} 个 ASIN（并发 {workers}）...")

    def fetch_one(asin):
        try:
            return asin, fetch_product_detail(asin, config)
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠️ {asin} 详情抓取失败，跳过: {e}")
            return asin, {}

    results = {}
    if workers == 1 or len(asins) <= 1:
        for asin in asins:
            a, detail = fetch_one(asin)
            results[a] = detail
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for asin, detail in ex.map(fetch_one, asins):
                results[asin] = detail

    for asin, detail in results.items():
        disc = detail.get("discount_off_list_pct")
        items[asin]["discount_off_list_pct"] = disc
        price = items[asin].get("price")           # competitor 准确 USD 现价（折扣后）
        if disc and isinstance(price, (int, float)) and price > 0:
            # USD 折扣前价 = 现价 / (1 - 折扣%)
            items[asin]["list_price"] = round(price / (1 - disc / 100), 2)
        items[asin]["about"] = detail.get("about") or []


def process_asins(asins: list, config: dict, token_manager) -> dict:
    """ASIN 模式：competitor-lookup 单接口拿全量数据（57 字段）+ 亚马逊详情页折扣。"""
    print(f"\n🔎 competitor-lookup: {len(asins)} 个 ASIN")
    items = lookup_asins(asins, config, token_manager, {"accept": "application/json"})
    print(f"   卖家精灵返回 {len(items)} 条（每条 57 字段）")
    _enrich_detail(items, config)   # 亚马逊详情页：折扣 + About this item
    rows = [flatten_record(it) for it in items.values()]
    if not rows:
        print("   ⚠️ 无数据")
        return {}
    return _emit_rows(rows)


_ASIN_RE = re.compile(r"[A-Z0-9]{10}")


def parse_asins(text: str) -> list:
    """从文本（逗号/空格/换行分隔）提取 ASIN，大写归一 + 去重，保序。"""
    seen, out = set(), []
    for p in _ASIN_RE.findall(text.upper()):
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def read_asins_input(raw: str) -> list:
    """输入是已存在的文件路径 → 读文件；否则当 ASIN 串。返回去重 ASIN 列表。"""
    candidate = Path(raw)
    if candidate.is_file():
        print(f"   📄 从文件读取: {candidate}")
        text = candidate.read_text(encoding="utf-8")
    else:
        text = raw
    return parse_asins(text)


def _read_input(prompt: str) -> str:
    """读一行输入；若为多行粘贴（stdin 缓冲区还有待读行）则自动合并全部行。
    单行手动输入时缓冲区为空，行为等同 input()——多行粘贴不再被截断到首行。"""
    chunks = [input(prompt)]
    try:
        while select.select([sys.stdin], [], [], 0.1)[0]:
            nxt = sys.stdin.readline()
            if not nxt:  # EOF
                break
            chunks.append(nxt)
    except (OSError, ValueError):
        # select 不可用（Windows 对文件描述符 / 某些重定向场景）：退化为单行
        pass
    return "".join(chunks)


def main():
    load_env()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    token_manager = KeepaTokenManager(ROOT / ".token_cache.json")
    print("=== 卖家精灵 ASIN 爬虫 ===（输入 q 退出）")
    print("提示：粘贴 ASIN（逗号/空格/换行分隔，多行粘贴自动合并），或输入含 ASIN 的文件路径")
    while True:
        try:
            raw = _read_input("\n输入 ASIN 或文件路径: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见"); break
        if not raw:
            continue
        if raw.lower() in {"q", "quit", "exit"}:
            print("再见"); break
        asins = read_asins_input(raw)
        if not asins:
            print("⚠️ 未识别到 ASIN，请检查输入")
            continue
        try:
            process_asins(asins, config, token_manager)
        except AuthExpiredError as e:
            print(f"❌ 鉴权失效: {e}（请检查 .env 里的登录账号 / auth-fp / random-token）")
        except Exception as e:
            print(f"❌ 出错: {e}")


if __name__ == "__main__":
    main()
