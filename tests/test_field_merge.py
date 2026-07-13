from field_merge import camel_to_snake, flatten_record, large_image_url, to_number


def test_camel_to_snake():
    assert camel_to_snake("monthUnits") == "month_units"
    assert camel_to_snake("bsrList") == "bsr_list"
    assert camel_to_snake("asin") == "asin"


def test_flatten_nested_dict_list():
    rec = {"bsrList": [{"rank": 22, "id": "3422301", "main": False},
                       {"rank": 4907, "id": "sporting-goods", "main": True}]}
    flat = flatten_record(rec)
    assert flat["bsr_list__main_rank"] == 4907
    assert flat["bsr_list__sub_rank"] == 22


def test_flatten_dict_value():
    rec = {"relationKeyword": {"ads": 30, "nature": 222, "total": 245}}
    flat = flatten_record(rec)
    assert flat["relation_keyword__ads"] == 30
    assert flat["relation_keyword__total"] == 245


def test_to_number():
    assert to_number(79.99) == 79.99
    assert to_number("1754") == 1754.0
    assert to_number("5 pounds") == 5.0
    assert to_number(None) is None


def test_large_image_url():
    base = "https://images-na.ssl-images-amazon.com/images/I/"
    # 200px 缩略图 → 1500px 高清（同 ID 换尺寸标识）
    assert large_image_url(base + "819zRrAuQRL._AC_US200_.jpg") == base + "819zRrAuQRL._AC_SL1500_.jpg"
    # 600px → 1500px
    assert large_image_url(base + "819zRrAuQRL._AC_US600_.jpg") == base + "819zRrAuQRL._AC_SL1500_.jpg"
    assert large_image_url(None) is None
    assert large_image_url("") is None
    # 非亚马逊图床：原样返回
    assert large_image_url("https://example.com/x.jpg") == "https://example.com/x.jpg"
