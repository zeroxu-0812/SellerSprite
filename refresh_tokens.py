#!/usr/bin/env python3
"""自动登录卖家精灵拿新鲜 token。

stdout 输出 JSON：{auth-token, auth-fp, random-token, cookie, ttl_seconds}，
供 KeepaTokenManager.refresh_from_command() 消费。

机制：POST 表单到卖家精灵登录 API（email + MD5(password) + tk 签名），
从响应里提取 token。登录 URL / 字段路径均可在 .env 配置（不同版本可能漂移）。
"""
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sellersprite_signing import sellersprite_token, extension_version_token

EXTENSION_ID = "lnbmbgocenenhhhdojdielgnmeflbnfb"


def _truthy(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y"}


def load_env() -> None:
    p = Path(__file__).resolve().parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _get_by_path(data, path: str):
    """按 'a.b.c' 取嵌套值。"""
    cur = data
    for seg in (path or "").split("."):
        seg = seg.strip()
        if seg == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def build_payload() -> bytes:
    email = (os.getenv("KEEPA_LOGIN_USERNAME") or "").strip()
    password = (os.getenv("KEEPA_LOGIN_PASSWORD") or "").strip()
    if not email or not password:
        raise RuntimeError("缺少 KEEPA_LOGIN_USERNAME / KEEPA_LOGIN_PASSWORD")
    if _truthy("KEEPA_LOGIN_PASSWORD_MD5", default=True):
        password = hashlib.md5(password.encode("utf-8")).hexdigest()
    version = (os.getenv("KEEPA_LOGIN_VERSION") or "5.0.4").strip()
    tk = sellersprite_token(email, password, ext_version=extension_version_token(version))
    payload = {
        "email": email,
        "password": password,
        "version": version,
        "language": (os.getenv("KEEPA_LOGIN_LANGUAGE") or "zh_CN").strip(),
        "extension": (os.getenv("KEEPA_LOGIN_EXTENSION_ID") or EXTENSION_ID).strip(),
        "source": (os.getenv("KEEPA_LOGIN_SOURCE") or "chrome").strip(),
        "tk": tk,
    }
    return urlencode(payload).encode("utf-8")


def login(_urlopen=urlopen) -> dict:
    url = (os.getenv("KEEPA_LOGIN_URL") or "").strip()
    if not url:
        raise RuntimeError("缺少 KEEPA_LOGIN_URL（卖家精灵登录 API 地址，需抓包获取）")
    body = build_payload()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with _urlopen(req, timeout=float(os.getenv("KEEPA_LOGIN_TIMEOUT_SECONDS", "20"))) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        text = ""
        try:
            text = exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"HTTP {exc.code}: {text or exc.reason}") from exc


def extract_headers(response: dict) -> dict:
    """从登录响应提取 token。路径可在 .env 配置，默认匹配参考实现。"""
    headers = {}
    paths = {
        "auth-token": (os.getenv("KEEPA_RESPONSE_AUTH_TOKEN_PATH") or "data.token").strip(),
        "auth-fp": (os.getenv("KEEPA_RESPONSE_AUTH_FP_PATH") or "auth-fp").strip(),
        "random-token": (os.getenv("KEEPA_RESPONSE_RANDOM_TOKEN_PATH") or "random-token").strip(),
        "cookie": (os.getenv("KEEPA_RESPONSE_COOKIE_PATH") or "cookie").strip(),
    }
    for key, path in paths.items():
        value = _get_by_path(response, path)
        if value is not None and str(value).strip():
            headers[key] = str(value).strip()
    # 缺失字段回退到现有 env（支持"只刷部分"）
    fallback = {"auth-token": "KEEPA_AUTH_TOKEN", "auth-fp": "KEEPA_AUTH_FP",
                "random-token": "KEEPA_RANDOM_TOKEN", "cookie": "KEEPA_COOKIE"}
    for key, env_key in fallback.items():
        if not headers.get(key):
            value = (os.getenv(env_key) or "").strip()
            if value:
                headers[key] = value
    missing = [k for k in ("auth-token", "auth-fp", "random-token") if not headers.get(k)]
    if missing:
        raise RuntimeError("登录响应未取到完整 token，缺少: " + ", ".join(missing) +
                           "。请检查 KEEPA_RESPONSE_*_PATH。")
    return headers


def main() -> int:
    load_env()
    try:
        response = login()
        headers = extract_headers(response)
    except Exception as exc:  # noqa: BLE001
        print(f"refresh_tokens failed: {exc}", file=sys.stderr)
        return 1
    output = {
        "auth-token": headers["auth-token"],
        "auth-fp": headers["auth-fp"],
        "random-token": headers["random-token"],
        "cookie": headers.get("cookie", ""),
        "ttl_seconds": int(os.getenv("KEEPA_TOKEN_TTL_SECONDS", "5400")),
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
