"""亚马逊商品详情页折扣抓取。

competitor-lookup 不返回折扣信息，靠抓 dp/<asin> 详情页补 list_price(划线价) /
discount_off_list_pct(折扣%)。解析层纯函数可测；fetch_product_discount 用 Playwright 实跑。"""
import re


def parse_price(text: str):
    m = re.search(r"(\d+(?:\.\d+)?)", (text or "").replace(",", ""))
    return float(m.group(1)) if m else None


def parse_price_detail(html: str) -> dict:
    """从亚马逊商品详情页 HTML 提取页面显示的折扣：
    list_price(折扣前/划线价)、price_current(折扣后/现价)、discount_off_list_pct(折扣%)。
    注意：页面价格受机房 geo-IP 影响可能是本地货币；折扣% 币种无关、最可靠。"""
    out = {"list_price": None, "price_current": None, "discount_off_list_pct": None}
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
        out["discount_off_list_pct"] = round(
            (out["list_price"] - out["price_current"]) / out["list_price"] * 100, 1)
    return out


def fetch_product_discount(asin: str, config: dict) -> dict:
    """用 Playwright 抓亚马逊商品详情页(dp/<asin>)，解析页面显示的折扣。best-effort。"""
    from playwright.sync_api import sync_playwright
    az = config["amazon"]
    url = f"{az['base_url']}/dp/{asin}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page_obj = browser.new_context(user_agent=az["user_agent"]).new_page()
            page_obj.goto(url, timeout=60000)
            html = page_obj.content()
        finally:
            browser.close()
    return parse_price_detail(html)
