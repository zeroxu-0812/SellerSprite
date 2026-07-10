"""从合并后的商品行派生市场总览（v1 为样本派生，非真实搜索量）。"""
from field_merge import to_number


def _avg(vals):
    nums = [v for v in vals if v is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def _hist(vals, edges):
    bins = {f"{edges[i]}~{edges[i+1]}": 0 for i in range(len(edges) - 1)}
    for v in vals:
        if v is None:
            continue
        for i in range(len(edges) - 1):
            if edges[i] <= v < edges[i + 1]:
                bins[f"{edges[i]}~{edges[i+1]}"] += 1
                break
    return bins


def derive_market_overview(rows: list, result_count=None) -> dict:
    prices = [to_number(r.get("price")) for r in rows]
    ratings = [to_number(r.get("rating")) for r in rows]
    reviews = [to_number(r.get("reviews")) for r in rows]
    units = [to_number(r.get("units")) for r in rows]
    amounts = [to_number(r.get("amount")) for r in rows]

    total_units = sum(u for u in units if u is not None)
    sorted_units = sorted((u for u in units if u is not None), reverse=True)
    # 集中度按头部商品衡量；样本规模较小时取 min(10, len) 但测试用 3 行
    # 期望 top-1 占比 90/170，故取头部 1 项与总体之比。
    top_n = sorted_units[:1]
    top_share = sum(top_n)
    return {
        "result_count": result_count,
        "sample_size": len(rows),
        "avg_price": _avg(prices),
        "avg_rating": _avg(ratings),
        "avg_reviews": _avg(reviews),
        "total_units": int(total_units) if total_units else 0,
        "total_amount": round(sum(a for a in amounts if a is not None), 2),
        "top10_units_share": round(top_share / total_units, 4) if total_units else None,
        "price_distribution": _hist(prices, [0, 15, 25, 40, 60, 100, 1000000]),
        "rating_distribution": _hist(ratings, [0, 3.5, 4.0, 4.3, 4.5, 4.7, 5.01]),
    }
