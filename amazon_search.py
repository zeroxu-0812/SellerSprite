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
    m = re.search(r"([\d,]+)", text or "")
    return int(m.group(1).replace(",", "")) if m else None


class _AmazonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.products = []
        self._asin_ctx = None
        self._capture = None  # ("title"|"price"|"rating"|"reviews", buffer)

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "div" and attrs_d.get("data-asin"):
            asin = attrs_d["data-asin"]
            if ASIN_RE.match(asin):
                self._asin_ctx = {"asin": asin}
        if self._asin_ctx is None:
            return
        cls = attrs_d.get("class", "") or ""
        if tag == "a" and "a-link-normal" in cls and self._capture is None:
            self._capture = ("title", [])
        elif tag == "span" and "a-offscreen" in cls:
            self._capture = ("price", [])
        elif tag == "span" and "a-icon-alt" in cls:
            self._capture = ("rating", [])
        elif tag == "span" and "s-underline-text" in cls:
            self._capture = ("reviews", [])

    def handle_data(self, data):
        if self._capture is not None:
            self._capture[1].append(data)

    def handle_endtag(self, tag):
        if self._capture is not None and tag == "span":
            kind, buf = self._capture
            text = "".join(buf).strip()
            if kind == "title" and self._asin_ctx is not None and "title" not in self._asin_ctx:
                self._asin_ctx["title"] = text
            elif kind == "price":
                self._asin_ctx["price"] = parse_price(text)
            elif kind == "rating":
                self._asin_ctx["rating"] = parse_rating(text)
            elif kind == "reviews":
                self._asin_ctx["reviews"] = parse_reviews(text)
            self._capture = None
        if tag == "div" and self._asin_ctx is not None:
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
        ctx = browser.new_context(user_agent=az["user_agent"])
        page_obj = ctx.new_page()
        page_obj.goto(url, timeout=60000)
        page_obj.wait_for_selector("[data-asin]", timeout=30000)
        html = page_obj.content()
        browser.close()
    return extract_products_from_html(html)


def search_amazon_paginated(keyword: str, config: dict) -> list:
    az = config["amazon"]
    all_products = []
    seen = set()
    for page in range(1, int(az.get("max_pages", 1)) + 1):
        products = search_amazon(keyword, config, page=page)
        for p in products:
            if p["asin"] not in seen:
                seen.add(p["asin"])
                all_products.append(p)
        time.sleep(random.uniform(az["page_delay_seconds_min"], az["page_delay_seconds_max"]))
    return all_products
