from sellersprite_signing import extension_version_token, token_calculate, sellersprite_token

TKK = extension_version_token("5.0.4")

def test_version_token():
    assert extension_version_token("5.0.4") == "500004.1364508470"

def test_single_asin_golden():
    # 抓包真实值
    assert token_calculate("B0GDY15VMN", TKK) == "56333.490793"

def test_batch_asins_golden():
    assert token_calculate("B091FX694F,B00NUQT3R2", TKK) == "82711.451123"

def test_sellersprite_token_helper():
    assert sellersprite_token("B0GDY15VMN", ext_version=TKK) == "56333.490793"

def test_keyword_is_signable():
    # 签名对任意 UTF-8 字符串通用
    assert isinstance(sellersprite_token("yoga mat", ext_version=TKK), str)
    assert "." in sellersprite_token("yoga mat", ext_version=TKK)
