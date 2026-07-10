from field_merge import camel_to_snake, flatten_record, merge_record, to_number


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


def test_merge_single_source_no_annotation():
    amazon = {"asin": "B0GDY15VMN", "price": 79.99, "rating": 4.6}
    enrich = {"asin": "B0GDY15VMN", "units": 1754, "amount": 140302.45}
    merged = merge_record(amazon, enrich)
    assert merged["asin"] == "B0GDY15VMN"
    assert merged["price"] == 79.99          # 仅亚马逊有，裸值
    assert merged["units"] == 1754            # 仅卖家精灵有，裸值
    assert merged["amount"] == 140302.45


def test_merge_conflict_annotated():
    amazon = {"asin": "X", "sellers": 6, "bsr": 4907}
    enrich = {"asin": "X", "sellers": 4, "bsr": 4470}
    merged = merge_record(amazon, enrich)
    assert merged["sellers"] == "6(亚马逊) / 4(卖家精灵)"
    assert merged["bsr"] == "4907(亚马逊) / 4470(卖家精灵)"


def test_merge_same_value_single():
    amazon = {"asin": "X", "brand": "gogoKIWI"}
    enrich = {"asin": "X", "brand": "gogoKIWI"}
    merged = merge_record(amazon, enrich)
    assert merged["brand"] == "gogoKIWI"


def test_to_number():
    assert to_number(79.99) == 79.99
    assert to_number("1754") == 1754.0
    assert to_number("5 pounds") == 5.0
    assert to_number(None) is None
