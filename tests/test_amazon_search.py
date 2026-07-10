from pathlib import Path
from amazon_search import extract_products_from_html, parse_price, parse_rating, parse_reviews

FIX = Path(__file__).parent / "fixtures" / "amazon_sample.html"


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
