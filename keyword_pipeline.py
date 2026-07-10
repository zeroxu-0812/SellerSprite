# keyword_pipeline.py
"""编排 + CLI 交互入口。"""
import json
import os
from pathlib import Path

from sellersprite_auth import KeepaTokenManager
from amazon_search import search_amazon_paginated
from sellersprite_enrich import enrich_asins, AuthExpiredError
from field_merge import merge_record
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


def process_keyword(keyword: str, config: dict, token_manager) -> dict:
    print(f"\n🔍 搜索亚马逊: {keyword}")
    products = search_amazon_paginated(keyword, config)
    print(f"   亚马逊抓到 {len(products)} 个商品")
    if not products:
        print("   ⚠️ 未抓到商品（可能被反爬），跳过")
        return {}

    asins = [p["asin"] for p in products]
    print(f"   增强 quick-view: {len(asins)} 个 ASIN ...")
    enriched = enrich_asins(asins, config, token_manager, {"accept": "application/json"})
    print(f"   卖家精灵返回 {len(enriched)} 个增强")

    merged = [merge_record(p, enriched.get(p["asin"], {})) for p in products]
    overview = derive_market_overview(merged, result_count=None)

    out_dir = output_dir_for(keyword, base=str(ROOT / "output"))
    write_products(merged, out_dir, keyword)
    write_market_overview(overview, out_dir, keyword)

    print(f"\n📊 市场总览（样本 {overview['sample_size']}）:")
    print(f"   均价 {overview['avg_price']} | 均评分 {overview['avg_rating']} | 均评论 {overview['avg_reviews']}")
    print(f"   样本总销量 {overview['total_units']} | 总销售额 {overview['total_amount']}")
    print(f"   Top10 集中度 {overview['top10_units_share']}")
    print(f"💾 已保存到 {out_dir}")
    return {"products": len(merged), "out_dir": str(out_dir)}


def main():
    load_env()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    token_manager = KeepaTokenManager(ROOT / ".token_cache.json")
    print("=== 卖家精灵关键词搜索爬虫 ===（输入 q 退出）")
    while True:
        try:
            keyword = input("\n输入关键词: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见"); break
        if not keyword:
            continue
        if keyword.lower() in {"q", "quit", "exit"}:
            print("再见"); break
        try:
            process_keyword(keyword, config, token_manager)
        except AuthExpiredError as e:
            print(f"❌ 鉴权失效: {e}（请更新 .env 里的 token）")
        except Exception as e:
            print(f"❌ 出错: {e}")


if __name__ == "__main__":
    main()
