"""亚马逊商品详情页抓取：折扣 + About this item。

competitor-lookup 不返回折扣/描述，靠抓 dp/<asin> 详情页补 list_price(划线价) /
discount_off_list_pct(折扣%) 与 about(feature-bullets 要点)。解析层纯函数可测；
fetch_product_detail 用 Playwright 实跑。"""
import re

# 折扣% 超过此阈值几乎必是抓错现价（取到变体/样品价等），按伪折扣丢弃。
_MAX_PLAUSIBLE_DISCOUNT_PCT = 90


def split_about_bullets(raw_text: str) -> list:
    """把 #feature-bullets 区块文本拆成要点列表，过滤噪音。
    输入来自 Playwright inner_text（按换行分隔的要点）。空/过短/"See more"等过滤，上限 20 条。"""
    if not raw_text:
        return []
    drop = {"see more", "see less", "see all"}
    out = []
    for line in raw_text.splitlines():
        t = line.strip()
        if not t or len(t) <= 2:
            continue
        if t.lower() in drop:
            continue
        out.append(t)
    return out[:20]


def parse_price(text: str):
    m = re.search(r"(\d+(?:\.\d+)?)", (text or "").replace(",", ""))
    return float(m.group(1)) if m else None


def _has_deal(html: str) -> bool:
    """亚马逊详情页是否为真实限时 deal：dealBadge 徽标 或 倒计时存在。
    仅普通划线价(MSRP)而无 deal 徽标不算 deal（避免把吊牌价当折扣）。"""
    if not html:
        return False
    return bool(re.search(
        r'class="[^"]*dealBadge|dealsCountdownTimer|deals_countdown_timer|deal_expiry_timer',
        html))


def parse_price_detail(html: str) -> dict:
    """从亚马逊商品详情页 HTML 提取页面显示的折扣：
    list_price(折扣前/划线价)、price_current(折扣后/现价)、discount_off_list_pct(折扣%)。
    仅当页面是真实限时 deal（_has_deal）才取折扣；否则返回全 None，避免普通 MSRP 划线价被误当折扣。
    注意：页面价格受机房 geo-IP 影响可能是本地货币；折扣% 币种无关、最可靠。"""
    out = {"list_price": None, "price_current": None, "discount_off_list_pct": None}
    if not _has_deal(html):
        return out  # 非 deal：不取折扣
    # 现价：第一个 a-offscreen 价格（主价格组件通常在最前）
    offs = re.findall(r'a-offscreen">([^<]{1,25})<', html)
    nums = [parse_price(t) for t in offs]
    nums = [n for n in nums if n]
    if nums:
        out["price_current"] = nums[0]
    # 折扣前(划线/吊牌价)：a-text-strike 后的数字
    m = re.search(r"a-text-strike[^0-9]{0,25}([\d,]+(?:\.\d+)?)", html)
    if m:
        out["list_price"] = parse_price(m.group(1))
    if out["list_price"] and out["price_current"] and out["list_price"] > out["price_current"]:
        disc = round(
            (out["list_price"] - out["price_current"]) / out["list_price"] * 100, 1)
        if disc <= _MAX_PLAUSIBLE_DISCOUNT_PCT:
            out["discount_off_list_pct"] = disc
        # 超 90% 的"折扣"几乎必是抓错现价（取到变体/样品价）→ 不设，避免伪折扣
    return out


def fetch_product_detail(asin: str, config: dict) -> dict:
    """用 Playwright 抓亚马逊详情页(dp/<asin>)，解析折扣 + About this item。best-effort。"""
    from playwright.sync_api import sync_playwright
    az = config["amazon"]
    url = f"{az['base_url']}/dp/{asin}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page_obj = browser.new_context(user_agent=az["user_agent"]).new_page()
            page_obj.goto(url, timeout=60000)
            html = page_obj.content()
            try:
                feat_li = page_obj.query_selector_all('#feature-bullets ul li')
                bullets_text = "\n".join(el.inner_text().strip() for el in feat_li)
            except Exception:
                bullets_text = ""
        finally:
            browser.close()
    detail = parse_price_detail(html)
    detail["about"] = split_about_bullets(bullets_text)
    return detail
