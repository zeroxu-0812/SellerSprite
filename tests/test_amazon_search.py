from amazon_search import parse_price_detail, split_about_bullets, _has_deal


def test_has_deal():
    # 真实 deal 信号：dealBadge 徽标 / 倒计时
    assert _has_deal('<span class="dealBadge aok-relative">Limited time deal</span>')
    assert _has_deal('<div id="dealsCountdownTimer"></div>')
    assert _has_deal('<div id="deals_countdown_timer"></div>')
    assert _has_deal('<div id="deal_expiry_timer"></div>')
    # 非 deal：普通划线价 / 空
    assert not _has_deal('<span class="a-text-strike">$34.99</span>')
    assert not _has_deal('')
    assert not _has_deal(None)


def test_parse_price_detail_with_deal():
    # 真实 deal：dealBadge + 现价 a-offscreen + 划线价 a-text-strike → 折扣%
    html = ('<span class="dealBadge">Limited time deal</span>'
            '<span class="a-price"><span class="a-offscreen">HKD70.49</span></span>'
            '<span class="a-text-strike"> HKD&nbsp;78.33 </span>')
    d = parse_price_detail(html)
    assert d["price_current"] == 70.49          # 第一个 a-offscreen = 现价
    assert d["list_price"] == 78.33             # 划线价 = 折扣前
    assert d["discount_off_list_pct"] == round((78.33 - 70.49) / 78.33 * 100, 1)


def test_parse_price_detail_no_deal_returns_none():
    # 非 deal：有划线价但无 dealBadge → 折扣全 None（不把 MSRP 划线价当折扣）
    html = ('<span class="a-price"><span class="a-offscreen">HKD70.49</span></span>'
            '<span class="a-text-strike"> HKD&nbsp;78.33 </span>')
    d = parse_price_detail(html)
    assert d["price_current"] is None
    assert d["list_price"] is None
    assert d["discount_off_list_pct"] is None


def test_parse_price_detail_drops_implausible_discount():
    # deal 页但抓到错误现价(HKD1.72，变体/样品价) → 99% 伪折扣 → 丢弃（折扣 None）
    html = ('<span class="dealBadge">Limited time deal</span>'
            '<span class="a-offscreen">HKD1.72</span>'
            '<span class="a-text-strike"> HKD&nbsp;195.9 </span>')
    d = parse_price_detail(html)
    assert d["discount_off_list_pct"] is None


def test_split_about_bullets_basic():
    text = "\n".join([
        "Magnesium cream for muscles and joints",
        "Fast absorbing, non-greasy formula",
        "See more",
        "",
        "ab",                       # 过短，过滤
        "With MSM, Arnica & B6",
    ])
    assert split_about_bullets(text) == [
        "Magnesium cream for muscles and joints",
        "Fast absorbing, non-greasy formula",
        "With MSM, Arnica & B6",
    ]


def test_split_about_bullets_empty():
    assert split_about_bullets("") == []
    assert split_about_bullets(None) == []


def test_split_about_bullets_caps_at_20():
    many = "\n".join(f"bullet number {i}" for i in range(30))
    assert len(split_about_bullets(many)) == 20
    assert split_about_bullets(many)[0] == "bullet number 0"
