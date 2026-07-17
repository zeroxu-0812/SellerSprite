#!/usr/bin/env python3
"""自动登录卖家精灵刷新 auth-token。

已实测验证的流程（GET）：
  GET https://www.sellersprite.com/v2/extension/signin
      ?email=<user>&password=<md5>&tk=<sig(email+md5pwd)>&version&language&extension&source
  响应 data.token = 新鲜 auth-token。
  auth-fp / random-token 是客户端稳定值（signin 不返回），从 .env 读取。

stdout 输出 JSON {auth-token, auth-fp, random-token, cookie, ttl_seconds}，
供 KeepaTokenManager.refresh_from_command() 消费。
"""
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
from urllib.request import Request, urlopen

from sellersprite_signing import sellersprite_token, extension_version_token

DEFAULT_LOGIN_URL = "https://www.sellersprite.com/v2/extension/signin"
EXTENSION_ID = "lnbmbgocenenhhhdojdielgnmeflbnfb"
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
ROOT = Path(__file__).resolve().parent
CLIENT_TOKENS_PATH = ROOT / ".client_tokens.json"


def _truthy(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y"}


def load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_or_create_client_tokens(path: Path = CLIENT_TOKENS_PATH) -> dict:
    """生成并缓存扩展客户端稳定值。

    卖家精灵 signin 只返回 auth-token，不返回 auth-fp/random-token。旧实现要求从
    Chrome 扩展抓包复制这两个值；这里改为在本地生成一组稳定值，降低 .env 配置门槛。
    如果线上接口后续对 auth-fp 格式收紧，仍可用 KEEPA_AUTH_FP/KEEPA_RANDOM_TOKEN 覆盖。
    """
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("auth-fp") and data.get("random-token"):
                return {"auth-fp": str(data["auth-fp"]), "random-token": str(data["random-token"])}
        except (OSError, json.JSONDecodeError):
            pass
    data = {
        "auth-fp": uuid.uuid4().hex,
        "random-token": str(uuid.uuid4()),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _get_by_path(data, path: str):
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


def build_signin_url() -> str:
    email = (os.getenv("KEEPA_LOGIN_USERNAME") or "").strip()
    password = (os.getenv("KEEPA_LOGIN_PASSWORD") or "").strip()
    if not email or not password:
        raise RuntimeError("缺少 KEEPA_LOGIN_USERNAME / KEEPA_LOGIN_PASSWORD")
    if _truthy("KEEPA_LOGIN_PASSWORD_MD5", default=True):
        password = hashlib.md5(password.encode("utf-8")).hexdigest()
    version = (os.getenv("KEEPA_LOGIN_VERSION") or "5.0.4").strip()
    tk = sellersprite_token(email, password, ext_version=extension_version_token(version))
    params = {
        "email": email,
        "password": password,
        "tk": tk,
        "version": version,
        "language": (os.getenv("KEEPA_LOGIN_LANGUAGE") or "zh_CN").strip(),
        "extension": (os.getenv("KEEPA_LOGIN_EXTENSION_ID") or EXTENSION_ID).strip(),
        "source": (os.getenv("KEEPA_LOGIN_SOURCE") or "chrome").strip(),
    }
    base = (os.getenv("KEEPA_LOGIN_URL") or DEFAULT_LOGIN_URL).strip()
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params,
                       urlencode(query), parsed.fragment))


def login(_urlopen=urlopen) -> dict:
    url = build_signin_url()
    req = Request(url, headers={"accept": "application/json", "user-agent": DEFAULT_UA}, method="GET")
    timeout = float(os.getenv("KEEPA_LOGIN_TIMEOUT_SECONDS", "20"))
    try:
        with _urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        text = ""
        try:
            text = exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"HTTP {exc.code}: {text or exc.reason}") from exc


def extract_headers(response: dict) -> dict:
    """auth-token 来自登录响应；客户端稳定值优先取 .env，缺省则本地生成并缓存。"""
    headers = {}
    token_path = (os.getenv("KEEPA_RESPONSE_AUTH_TOKEN_PATH") or "data.token").strip()
    token = _get_by_path(response, token_path)
    if token is not None and str(token).strip():
        headers["auth-token"] = str(token).strip()
    client_tokens = _load_or_create_client_tokens()
    headers["auth-fp"] = (os.getenv("KEEPA_AUTH_FP") or client_tokens["auth-fp"]).strip()
    headers["random-token"] = (os.getenv("KEEPA_RANDOM_TOKEN") or client_tokens["random-token"]).strip()
    cookie = (os.getenv("KEEPA_COOKIE") or "").strip()
    if cookie:
        headers["cookie"] = cookie
    if not headers.get("auth-token"):
        raise RuntimeError("登录响应未取到 auth-token，请检查 KEEPA_RESPONSE_AUTH_TOKEN_PATH")
    missing = [k for k in ("auth-fp", "random-token") if not headers.get(k)]
    if missing:
        raise RuntimeError("缺少客户端值: " + ", ".join(missing))
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
