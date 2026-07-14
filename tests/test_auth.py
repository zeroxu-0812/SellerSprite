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


def test_concurrent_refresh_runs_command_once(monkeypatch, tmp_path):
    """并发调用 refresh_from_command：锁 + 双检缓存 → 登录命令只执行一次（其余线程复用缓存）。"""
    import threading

    marker = tmp_path / "refresh_calls.txt"
    script = tmp_path / "refresh.sh"
    payload = '{"auth-token":"t","auth-fp":"f","random-token":"r","ttl_seconds":5400}'
    script.write_text(
        "#!/bin/sh\n"
        f'echo x >> "{marker}"\n'
        f"printf '%s' '{payload}'\n"
    )
    script.chmod(0o755)

    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_EACH_RUN", "false")
    monkeypatch.setenv("KEEPA_TOKEN_REFRESH_COMMAND", str(script))

    mgr = KeepaTokenManager(tmp_path / ".cache.json")
    results, rlock = [], threading.Lock()

    def call():
        r = mgr.refresh_from_command() is not None
        with rlock:
            results.append(r)

    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(results)                                  # 8 个线程都拿到 headers
    assert marker.read_text().count("x") == 1            # 登录命令只跑了一次
