from market_overview import derive_market_overview


def test_basic_overview():
    rows = [
        {"asin": "A", "price": 10.0, "rating": 4.5, "reviews": 100, "units": 50, "amount": 500.0},
        {"asin": "B", "price": 20.0, "rating": 4.0, "reviews": 200, "units": 30, "amount": 600.0},
        {"asin": "C", "price": 30.0, "rating": 5.0, "reviews": 50, "units": 90, "amount": 2700.0},
    ]
    ov = derive_market_overview(rows, result_count=10000)
    assert ov["result_count"] == 10000
    assert ov["sample_size"] == 3
    assert ov["avg_price"] == 20.0
    assert ov["avg_rating"] == round((4.5 + 4.0 + 5.0) / 3, 2)
    assert ov["avg_reviews"] == round((100 + 200 + 50) / 3, 2)
    assert ov["total_units"] == 170
    assert ov["total_amount"] == 3800.0
    # Top10 集中度：Top1(=90) 占 90/170
    assert ov["top10_units_share"] == round(90 / 170, 4)


def test_empty_rows():
    ov = derive_market_overview([], result_count=None)
    assert ov["sample_size"] == 0
    assert ov["avg_price"] is None
