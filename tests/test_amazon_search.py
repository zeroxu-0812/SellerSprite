from amazon_search import parse_price_detail


def test_parse_price_detail():
    # 模拟真实详情页：现价 a-offscreen 在前，划线价 a-text-strike
    html = ('<span class="a-price"><span class="a-offscreen">HKD70.49</span></span>'
            '<span class="a-text-strike"> HKD&nbsp;78.33 </span>')
    d = parse_price_detail(html)
    assert d["price_current"] == 70.49          # 第一个 a-offscreen = 现价
    assert d["list_price"] == 78.33             # 划线价 = 折扣前
    assert d["discount_off_list_pct"] == round((78.33 - 70.49) / 78.33 * 100, 1)


def test_parse_price_detail_no_discount():
    d = parse_price_detail('<span class="a-offscreen">$9.99</span>')  # 无划线价 → 无折扣
    assert d["price_current"] == 9.99
    assert d["list_price"] is None
    assert d["discount_off_list_pct"] is None
