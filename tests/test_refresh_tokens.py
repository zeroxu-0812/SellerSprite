import hashlib
import json
from urllib.parse import parse_qs, urlparse

import refresh_tokens
from sellersprite_signing import sellersprite_token, extension_version_token


def test_build_signin_url_signs_email_and_md5_password(monkeypatch):
    monkeypatch.setenv("KEEPA_LOGIN_USERNAME", "me@example.com")
    monkeypatch.setenv("KEEPA_LOGIN_PASSWORD", "secret123")
    monkeypatch.setenv("KEEPA_LOGIN_VERSION", "5.0.4")
    monkeypatch.delenv("KEEPA_LOGIN_PASSWORD_MD5", raising=False)
    monkeypatch.delenv("KEEPA_LOGIN_URL", raising=False)

    url = refresh_tokens.build_signin_url()
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}

    md5pwd = hashlib.md5(b"secret123").hexdigest()
    expected_tk = sellersprite_token("me@example.com", md5pwd,
                                     ext_version=extension_version_token("5.0.4"))
    assert url.startswith("https://www.sellersprite.com/v2/extension/signin?")
    assert q["email"] == "me@example.com"
    assert q["password"] == md5pwd          # MD5 化
    assert q["tk"] == expected_tk           # tk 对 email+md5pwd 签名
    assert q["version"] == "5.0.4"


def test_build_signin_url_password_md5_disabled(monkeypatch):
    """允许直接填 MD5 哈希（MD5=false 时原样使用）。"""
    monkeypatch.setenv("KEEPA_LOGIN_USERNAME", "u")
    monkeypatch.setenv("KEEPA_LOGIN_PASSWORD", "71fd52f41d0cc70e34b268b6dcf3719b")
    monkeypatch.setenv("KEEPA_LOGIN_PASSWORD_MD5", "false")
    q = {k: v[0] for k, v in parse_qs(urlparse(refresh_tokens.build_signin_url()).query).items()}
    assert q["password"] == "71fd52f41d0cc70e34b268b6dcf3719b"   # 未再 MD5


def test_build_signin_url_requires_credentials(monkeypatch):
    monkeypatch.delenv("KEEPA_LOGIN_USERNAME", raising=False)
    monkeypatch.delenv("KEEPA_LOGIN_PASSWORD", raising=False)
    try:
        refresh_tokens.build_signin_url()
        assert False, "应抛 RuntimeError"
    except RuntimeError:
        assert True


def test_extract_headers_token_from_response_fp_random_from_env(monkeypatch):
    monkeypatch.setenv("KEEPA_AUTH_FP", "CLIENT_FP")
    monkeypatch.setenv("KEEPA_RANDOM_TOKEN", "CLIENT_RT")
    response = {"data": {"token": "FRESH_AUTH_TOKEN"}}
    h = refresh_tokens.extract_headers(response)
    assert h["auth-token"] == "FRESH_AUTH_TOKEN"   # 来自响应
    assert h["auth-fp"] == "CLIENT_FP"             # 来自 env（客户端稳定值）
    assert h["random-token"] == "CLIENT_RT"


def test_extract_headers_missing_token_raises(monkeypatch):
    monkeypatch.setenv("KEEPA_AUTH_FP", "FP")
    monkeypatch.setenv("KEEPA_RANDOM_TOKEN", "RT")
    try:
        refresh_tokens.extract_headers({"data": {}})
        assert False
    except RuntimeError:
        assert True


def test_extract_headers_missing_client_values_raises(monkeypatch):
    monkeypatch.delenv("KEEPA_AUTH_FP", raising=False)
    monkeypatch.delenv("KEEPA_RANDOM_TOKEN", raising=False)
    try:
        refresh_tokens.extract_headers({"data": {"token": "T"}})
        assert False
    except RuntimeError:
        assert True


class _FakeResp:
    def __init__(self, data):
        self._data = json.dumps(data).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._data


def test_login_uses_get_with_query(monkeypatch):
    monkeypatch.setenv("KEEPA_LOGIN_USERNAME", "u@x.com")
    monkeypatch.setenv("KEEPA_LOGIN_PASSWORD", "p")
    captured = {}
    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.method
        return _FakeResp({"data": {"token": "T"}})
    refresh_tokens.login(_urlopen=fake_urlopen)
    assert captured["method"] == "GET"
    assert "signin" in captured["url"]
    assert "email=u%40x.com" in captured["url"]   # 凭据在 query 串里


def test_main_outputs_token_json(monkeypatch, capsys):
    monkeypatch.setenv("KEEPA_TOKEN_TTL_SECONDS", "120")
    monkeypatch.setenv("KEEPA_AUTH_FP", "FP")
    monkeypatch.setenv("KEEPA_RANDOM_TOKEN", "RT")
    monkeypatch.setattr(refresh_tokens, "login", lambda: {"data": {"token": "T1"}})
    rc = refresh_tokens.main()
    payload = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert payload["auth-token"] == "T1"
    assert payload["auth-fp"] == "FP"
    assert payload["random-token"] == "RT"
    assert payload["ttl_seconds"] == 120


def test_main_returns_1_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(refresh_tokens, "login",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rc = refresh_tokens.main()
    assert rc == 1
    assert "boom" in capsys.readouterr().err
