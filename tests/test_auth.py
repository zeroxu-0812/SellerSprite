# tests/test_auth.py
import json
from pathlib import Path
from sellersprite_auth import KeepaTokenManager


def test_headers_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KEEPA_AUTH_TOKEN", "tok")
    monkeypatch.setenv("KEEPA_AUTH_FP", "fp")
    monkeypatch.setenv("KEEPA_RANDOM_TOKEN", "rt")
    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_EACH_RUN", "false")
    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_COMMAND", "")
    mgr = KeepaTokenManager(tmp_path / ".cache.json")
    headers = mgr.get_valid_headers({"accept": "application/json"})
    assert headers["auth-token"] == "tok"
    assert headers["auth-fp"] == "fp"
    assert headers["random-token"] == "rt"
    assert headers["accept"] == "application/json"  # base 头保留


def test_missing_headers_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_EACH_RUN", "false")
    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_COMMAND", "")
    for k in ("KEEPA_AUTH_TOKEN", "KEEPA_AUTH_FP", "KEEPA_RANDOM_TOKEN", "KEEPA_COOKIE"):
        monkeypatch.delenv(k, raising=False)
    mgr = KeepaTokenManager(tmp_path / ".cache.json")
    try:
        mgr.get_valid_headers({})
        assert False, "应抛 RuntimeError"
    except RuntimeError:
        assert True


def test_invalidate_cache(monkeypatch, tmp_path):
    cache = tmp_path / ".cache.json"
    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_EACH_RUN", "false")
    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_COMMAND", "")
    mgr = KeepaTokenManager(cache)
    mgr._save_cache({"auth-token": "t", "auth-fp": "f", "random-token": "r"})
    assert cache.exists()
    mgr.invalidate_cache()
    assert not cache.exists()
