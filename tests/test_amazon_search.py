from pathlib import Path
from amazon_search import extract_products_from_html, parse_price, parse_rating, parse_reviews

FIX = Path(__file__).parent / "fixtures" / "amazon_sample.html"
REAL_DOM_FIX = Path(__file__).parent / "fixtures" / "amazon_real_dom.html"


def test_extract_two_products():
    html = FIX.read_text(encoding="utf-8")
    products = extract_products_from_html(html)
    assert len(products) == 2
    asins = {p["asin"] for p in products}
    assert asins == {"B0GDY15VMN", "B07JQCVBBZ"}
    gogokiwi = next(p for p in products if p["asin"] == "B0GDY15VMN")
    assert gogokiwi["price"] == 79.99
    assert gogokiwi["rating"] == 4.6
    assert gogokiwi["reviews"] == 730
    assert "Gogokiwi" in gogokiwi["title"]


def test_parse_helpers():
    assert parse_price("$79.99") == 79.99
    assert parse_rating("4.6 out of 5 stars") == 4.6
    assert parse_reviews("730") == 730


def test_parse_helpers_real_amazon_formats():
    # Live Amazon emits prices with non-USD currency prefixes and nbsp,
    # ratings identical to the fixture, and review counts with K/M suffixes
    # inside parentheses, e.g. "(69.4K)".
    assert parse_price("HKD 176.16") == 176.16
    assert parse_rating("4.5 out of 5 stars") == 4.5
    assert parse_reviews("(69.4K)") == 69400
    assert parse_reviews("1.2M") == 1200000
    assert parse_reviews("1,0279") == 10279


def test_extract_skips_non_product_cards():
    # Sponsor cards / navigation blocks use empty or non-ASIN data-asin values
    # and must not produce product entries.
    html = (
        '<div data-asin=""><div></div></div>'
        '<div data-asin="notanasin"><div></div></div>'
    )
    assert extract_products_from_html(html) == []


def test_extract_real_dom_fixture():
    # Regression for the highest-risk parser hardening (Task 8 Finding 2):
    # div-depth tracking, title-link selection via a-text-normal/s-line-clamp
    # with the _saw_title_link latch, capture-guard mutual exclusion, and K/M
    # review decoding. Validated previously only by a one-off live smoke.
    html = REAL_DOM_FIX.read_text(encoding="utf-8")
    products = extract_products_from_html(html)

    assert len(products) == 1
    p = products[0]
    assert p["asin"] == "B08N5WRWNW"

    # The real title link must win over the aria-hidden image link and the
    # color-swatch a-link-normal links that follow it.
    assert p["title"].startswith("GPX Thick Yoga Mat")
    assert "Blue" not in p["title"]
    assert "Black" not in p["title"]

    # a-offscreen price must win over the aria-hidden price-parts span.
    assert p["price"] == 36.98
    assert p["rating"] == 4.5
    # "1.2K" must decode to 1200.
    assert p["reviews"] == 1200

