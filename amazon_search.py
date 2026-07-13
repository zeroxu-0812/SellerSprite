"""Leg A：亚马逊搜索抓取。解析层纯函数可测；search_amazon 用 Playwright 实跑。"""
import random
import re
import time
import urllib.parse
from html.parser import HTMLParser

ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


def parse_price(text: str):
    m = re.search(r"(\d+(?:\.\d+)?)", (text or "").replace(",", ""))
    return float(m.group(1)) if m else None


def parse_rating(text: str):
    m = re.search(r"(\d(?:\.\d)?)\s*out of", text or "")
    return float(m.group(1)) if m else None


def parse_reviews(text: str):
    """Parse review counts. Handles plain ints, comma-grouped ('1,0279'),
    and K/M suffixes as seen on live Amazon ('(69.4K)', '1.2M')."""
    if not text:
        return None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*([KkMm])?", text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    return int(num)


class _AmazonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.products = []
        self._asin_ctx = None
        self._div_depth = 0  # nesting depth of the data-asin card
        self._capture = None  # ("title"|"price"|"rating"|"reviews", buffer)
        self._saw_title_link = False  # per-card: prefer the rich title link

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "div" and attrs_d.get("data-asin") and self._asin_ctx is None:
            asin = attrs_d["data-asin"]
            if ASIN_RE.match(asin):
                self._asin_ctx = {"asin": asin}
                self._div_depth = 1
                self._saw_title_link = False
                return
        if self._asin_ctx is None:
            return
        if tag == "div":
            self._div_depth += 1
        cls = attrs_d.get("class", "") or ""
        if self._capture is None:
            if tag == "a" and "title" not in self._asin_ctx:
                # The real product title link carries s-line-clamp / a-text-normal.
                # Color-swatch and other ancillary a-link-normal links do not, so
                # requiring one of those markers avoids grabbing the wrong link.
                is_title = (
                    "a-link-normal" in cls
                    and attrs_d.get("aria-hidden") != "true"
                    and ("s-line-clamp" in cls or "a-text-normal" in cls)
                )
                # Fixture has only a plain "a-link-normal" title link; accept it as
                # a fallback when no richer marker is present.
                is_fallback = (
                    "a-link-normal" in cls
                    and attrs_d.get("aria-hidden") != "true"
                    and "s-no-outline" not in cls
                )
                if is_title or (is_fallback and not self._saw_title_link):
                    if is_title:
                        self._saw_title_link = True
                    self._capture = ("title", [])
            elif tag == "span" and "a-offscreen" in cls:
                self._capture = ("price", [])
            elif tag == "span" and "a-icon-alt" in cls:
                self._capture = ("rating", [])
            elif tag == "span" and "s-underline-text" in cls:
                self._capture = ("reviews", [])

    def handle_startendtag(self, tag, attrs):
        # self-closing tags (e.g. <img/>); don't inflate div depth
        if self._asin_ctx is None:
            return

    def handle_data(self, data):
        if self._capture is not None:
            self._capture[1].append(data)

    def handle_endtag(self, tag):
        if self._capture is not None:
            kind = self._capture[0]
            # Title spans the whole <a> element (which may contain nested
            # <span>s); flush it on </a>. The other captures are single spans.
            flush_tag = "a" if kind == "title" else "span"
            if tag == flush_tag:
                _, buf = self._capture
                text = "".join(buf).strip()
                if kind == "title" and self._asin_ctx is not None and "title" not in self._asin_ctx:
                    self._asin_ctx["title"] = re.sub(r"\s+", " ", text)
                elif kind == "price":
                    self._asin_ctx["price"] = parse_price(text)
                elif kind == "rating":
                    self._asin_ctx["rating"] = parse_rating(text)
                elif kind == "reviews":
                    self._asin_ctx["reviews"] = parse_reviews(text)
                self._capture = None
        if tag == "div" and self._asin_ctx is not None:
            self._div_depth -= 1
            if self._div_depth == 0:
                if self._asin_ctx.get("title"):
                    self.products.append(self._asin_ctx)
                self._asin_ctx = None


def extract_products_from_html(html: str) -> list:
    p = _AmazonParser()
    p.feed(html)
    return p.products


def search_amazon(keyword: str, config: dict, page: int = 1) -> list:
    """用 Playwright 抓一页亚马逊搜索结果。需要 `pip install playwright && playwright install chromium`。"""
    from playwright.sync_api import sync_playwright
    az = config["amazon"]
    url = f"{az['base_url']}/s?" + urllib.parse.urlencode({"k": keyword, "page": page})
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=az["user_agent"])
            page_obj = ctx.new_page()
            page_obj.goto(url, timeout=60000)
            page_obj.wait_for_selector("[data-asin]", timeout=30000)
            html = page_obj.content()
        finally:
            browser.close()
    return extract_products_from_html(html)


def search_amazon_paginated(keyword: str, config: dict) -> list:
    az = config["amazon"]
    all_products = []
    seen = set()
    for page in range(1, int(az.get("max_pages", 1)) + 1):
        try:
            products = search_amazon(keyword, config, page=page)
        except Exception as e:
            # A single blocked/timeout/captcha page must not abort the whole
            # crawl: skip it and keep whatever earlier pages yielded. Playwright
            # raises playwright.sync_api.TimeoutError (a subclass of Exception)
            # on navigation/wait timeouts; other transient fetch errors land
            # here too. Printed, not swallowed.
            print(f"⚠️ 第 {page} 页抓取失败，跳过: {e}")
            continue
        for p in products:
            if p["asin"] not in seen:
                seen.add(p["asin"])
                all_products.append(p)
        time.sleep(random.uniform(az["page_delay_seconds_min"], az["page_delay_seconds_max"]))
    return all_products


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
