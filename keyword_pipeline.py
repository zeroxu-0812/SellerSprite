# keyword_pipeline.py
"""编排 + CLI 交互入口。"""
import json
import os
import re
from pathlib import Path

from sellersprite_auth import KeepaTokenManager
from amazon_search import search_amazon_paginated
from sellersprite_enrich import lookup_asins, AuthExpiredError
from field_merge import flatten_record, large_image_url
from market_overview import derive_market_overview
from keyword_output import output_dir_for, write_products, write_market_overview

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


def _emit_rows(rows: list, name: str) -> dict:
    """统一收尾：派生市场总览 + 落地 CSV/JSON + 打印摘要。rows 为扁平后的单源商品行。"""
    for r in rows:
        r["image_large"] = large_image_url(r.get("image"))   # 派生 1500px 高清封面链接
    overview = derive_market_overview(rows, result_count=None)
    out_dir = output_dir_for(name, base=str(ROOT / "output"))
    write_products(rows, out_dir, name)
    write_market_overview(overview, out_dir, name)
    print(f"\n📊 市场总览（样本 {overview['sample_size']}）:")
    print(f"   均价 {overview['avg_price']} | 均评分 {overview['avg_rating']} | 均评论 {overview['avg_reviews']}")
    print(f"   样本总销量 {overview['total_units']} | 总销售额 {overview['total_amount']}")
    print(f"   Top10 集中度 {overview['top10_units_share']}")
    print(f"💾 已保存到 {out_dir}")
    return {"products": len(rows), "out_dir": str(out_dir)}


def process_keyword(keyword: str, config: dict, token_manager) -> dict:
    """关键词模式：亚马逊搜索拿 ASIN 排序列表 → competitor-lookup 全量增强（单源，准确 USD）。"""
    print(f"\n🔍 搜索亚马逊: {keyword}")
    products = search_amazon_paginated(keyword, config)
    print(f"   亚马逊抓到 {len(products)} 个商品")
    if not products:
        print("   ⚠️ 未抓到商品（可能被反爬），跳过")
        return {}

    asins = [p["asin"] for p in products]
    print(f"   competitor-lookup 全量增强: {len(asins)} 个 ASIN ...")
    items = lookup_asins(asins, config, token_manager, {"accept": "application/json"})
    print(f"   卖家精灵返回 {len(items)} 条（每条 57 字段）")
    # 按亚马逊关键词排序展开，跳过无增强数据的 ASIN
    rows = [flatten_record(items[p["asin"]]) for p in products if p["asin"] in items]
    if not rows:
        print("   ⚠️ 无增强数据，跳过")
        return {}
    return _emit_rows(rows, keyword)


ASIN_TOKEN = re.compile(r"[A-Z0-9]{10}")


def is_asin_list(text: str) -> bool:
    """输入是否全部是 ASIN（逗号/空格分隔，每段 10 位大写字母数字）。"""
    parts = [p for p in re.split(r"[,\s]+", text.strip().upper()) if p]
    return bool(parts) and all(len(p) == 10 and ASIN_TOKEN.fullmatch(p) for p in parts)


def parse_asin_list(text: str) -> list:
    seen, out = set(), []
    for p in re.findall(r"[A-Z0-9]{10}", text.upper()):
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def process_asins(asins: list, config: dict, token_manager) -> dict:
    """ASIN 模式：competitor-lookup 单接口拿全量数据。"""
    print(f"\n🔎 competitor-lookup: {len(asins)} 个 ASIN")
    items = lookup_asins(asins, config, token_manager, {"accept": "application/json"})
    print(f"   卖家精灵返回 {len(items)} 条（每条 57 字段）")
    rows = [flatten_record(it) for it in items.values()]
    if not rows:
        print("   ⚠️ 无数据")
        return {}
    return _emit_rows(rows, f"asins_{len(rows)}")


def main():
    load_env()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    token_manager = KeepaTokenManager(ROOT / ".token_cache.json")
    print("=== 卖家精灵关键词搜索爬虫 ===（输入 q 退出）")
    print("提示：输入【关键词】走亚马逊搜索；输入【ASIN】(逗号/空格分隔多个) 走 competitor-lookup 全量查询")
    while True:
        try:
            keyword = input("\n输入关键词或 ASIN: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见"); break
        if not keyword:
            continue
        if keyword.lower() in {"q", "quit", "exit"}:
            print("再见"); break
        try:
            if is_asin_list(keyword):
                process_asins(parse_asin_list(keyword), config, token_manager)
            else:
                process_keyword(keyword, config, token_manager)
        except AuthExpiredError as e:
            print(f"❌ 鉴权失效: {e}（请更新 .env 里的 token）")
        except Exception as e:
            print(f"❌ 出错: {e}")


if __name__ == "__main__":
    main()
