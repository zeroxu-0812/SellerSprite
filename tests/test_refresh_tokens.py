import hashlib
import json
from urllib.parse import parse_qs

import refresh_tokens
from sellersprite_signing import sellersprite_token, extension_version_token


def test_build_payload_signs_email_and_md5_password(monkeypatch):
    monkeypatch.setenv("KEEPA_LOGIN_USERNAME", "me@example.com")
    monkeypatch.setenv("KEEPA_LOGIN_PASSWORD", "secret123")
    monkeypatch.setenv("KEEPA_LOGIN_VERSION", "5.0.4")
    monkeypatch.delenv("KEEPA_LOGIN_PASSWORD_MD5", raising=False)

    body = refresh_tokens.build_payload()
    q = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}

    md5pwd = hashlib.md5(b"secret123").hexdigest()
    expected_tk = sellersprite_token("me@example.com", md5pwd,
                                     ext_version=extension_version_token("5.0.4"))
    assert q["email"] == "me@example.com"
    assert q["password"] == md5pwd          # MD5 化
    assert q["tk"] == expected_tk           # tk 对 email+md5pwd 签名
    assert q["version"] == "5.0.4"


def test_build_payload_requires_credentials(monkeypatch):
    monkeypatch.delenv("KEEPA_LOGIN_USERNAME", raising=False)
    monkeypatch.delenv("KEEPA_LOGIN_PASSWORD", raising=False)
    try:
        refresh_tokens.build_payload()
        assert False, "应抛 RuntimeError"
    except RuntimeError:
        assert True


def test_extract_headers_default_paths():
    response = {"data": {"token": "TKN"}, "auth-fp": "FP", "random-token": "RT", "cookie": "C"}
    h = refresh_tokens.extract_headers(response)
    assert h["auth-token"] == "TKN"
    assert h["auth-fp"] == "FP"
    assert h["random-token"] == "RT"
    assert h["cookie"] == "C"


def test_extract_headers_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("KEEPA_AUTH_FP", "ENV_FP")
    response = {"data": {"token": "TKN"}, "random-token": "RT"}  # 缺 auth-fp
    h = refresh_tokens.extract_headers(response)
    assert h["auth-fp"] == "ENV_FP"


def test_extract_headers_missing_required_raises():
    try:
        refresh_tokens.extract_headers({"data": {}})  # 三个必需全缺
        assert False
    except RuntimeError:
        assert True


class _FakeResp:
    def __init__(self, data):
        self._data = json.dumps(data).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._data


def test_login_uses_injected_urlopen(monkeypatch):
    monkeypatch.setenv("KEEPA_LOGIN_URL", "https://example.com/login")
    monkeypatch.setenv("KEEPA_LOGIN_USERNAME", "u@x.com")
    monkeypatch.setenv("KEEPA_LOGIN_PASSWORD", "p")
    captured = {}
    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["data"] = req.data
        return _FakeResp({"data": {"token": "T"}, "auth-fp": "F", "random-token": "R"})
    result = refresh_tokens.login(_urlopen=fake_urlopen)
    assert result["data"]["token"] == "T"
    assert "example.com/login" in captured["url"]
    assert b"email=u%40x.com" in captured["data"]   # 表单 POST


def test_main_outputs_token_json(monkeypatch, capsys):
    monkeypatch.setenv("KEEPA_TOKEN_TTL_SECONDS", "120")
    monkeypatch.setenv("KEEPA_AUTH_TOKEN", "")  # 确保 fallback 不触发
    # 替换 login 为返回固定响应
    monkeypatch.setattr(refresh_tokens, "login",
                        lambda: {"data": {"token": "T1"}, "auth-fp": "F1", "random-token": "R1", "cookie": "C1"})
    rc = refresh_tokens.main()
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert rc == 0
    assert payload["auth-token"] == "T1"
    assert payload["auth-fp"] == "F1"
    assert payload["random-token"] == "R1"
    assert payload["cookie"] == "C1"
    assert payload["ttl_seconds"] == 120


def test_main_returns_1_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(refresh_tokens, "login", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rc = refresh_tokens.main()
    err = capsys.readouterr().err
    assert rc == 1
    assert "boom" in err
