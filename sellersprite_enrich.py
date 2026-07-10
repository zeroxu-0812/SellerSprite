"""Leg B：quick-view 批量增强。"""
import json
import random
import time
import urllib.request
import urllib.error
from sellersprite_signing import sellersprite_token, extension_version_token

AUTH_EXPIRED_CODES = {401, "401", "UNAUTHORIZED", "TOKEN_EXPIRED", "AUTH_EXPIRED",
                      "ERR_NEED_RE_AUTHORIZED", "ERR_GLOBAL_SESSION_EXPIRED"}
AUTH_EXPIRED_MSG = ("令牌过期", "token expired", "token invalid", "auth expired",
                    "unauthorized", "登录失效", "重新登录")
RETRY_HTTP = {408, 429} | set(range(500, 600))


class AuthExpiredError(RuntimeError):
    pass


class BusinessError(RuntimeError):
    """业务错误（code 非 200/OK 且非鉴权失效）：跳过当前批，不重试。"""
    pass


def build_quickview_url(config: dict, asins: list) -> str:
    qv = config["quick_view"]
    asins_str = ",".join(asins)
    tk = sellersprite_token(asins_str, ext_version=extension_version_token(config["version"]))
    params = (
        f"asins={asins_str}",
        f"source={config['source']}",
        "miniMode=false",
        f"withRelation={'true' if qv.get('with_relation', True) else 'false'}",
        f"withSaleTrend={'true' if qv.get('with_sale_trend', True) else 'false'}",
        f"tk={tk}",
        f"version={config['version']}",
        f"language={config['language']}",
        f"extension={config['extension_id']}",
    )
    return f"{qv['base_url']}/{config['station']}?" + "&".join(params)


def is_auth_expired(payload: dict, http_code: int) -> bool:
    if http_code == 401:
        return True
    if payload.get("code") in AUTH_EXPIRED_CODES:
        return True
    msg = str(payload.get("message", "")).lower()
    return any(k.lower() in msg for k in AUTH_EXPIRED_MSG)


# sellersprite 对"无数据"用 -1 哨兵（如 units=-1）；这些字段真实值不可能为 -1，归一为 None。
_NO_DATA_FIELDS = ("units", "month_units", "amount", "amount_growth", "profit", "fba",
                   "sellers", "variations", "reviews", "lqs")


def parse_quickview(payload: dict) -> list:
    data = payload.get("data") or {}
    items = list(data.get("items") or [])
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in _NO_DATA_FIELDS:
            if item.get(key) == -1:
                item[key] = None
    return items


def _do_request(url: str, headers: dict, timeout: float):
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode(), json.loads(resp.read().decode("utf-8"))


def enrich_asins(asins: list, config: dict, token_manager, base_headers: dict,
                 _sleep=time.sleep, _request=_do_request) -> dict:
    """返回 {asin: item}。鉴权失效自愈一次后重试；仍失败抛 AuthExpiredError。"""
    qv = config["quick_view"]
    batch = qv.get("batch_size", 20)
    result = {}
    for i in range(0, len(asins), batch):
        chunk = asins[i:i + batch]
        url = build_quickview_url(config, chunk)
        try:
            payload = _fetch_with_retry(url, config, token_manager, base_headers, _sleep, _request)
        except BusinessError as e:
            # 业务错误：打印并跳过该批，继续后续批次（早期批次结果保留）。
            print(f"⚠️ 第 {i // batch + 1} 批业务错误，跳过: {e}")
            continue
        for item in parse_quickview(payload):
            result[item.get("asin")] = item
        if i + batch < len(asins):
            _sleep(random.uniform(qv.get("delay_seconds_min", 5), qv.get("delay_seconds_max", 8)))
    return result


def _fetch_with_retry(url, config, token_manager, base_headers, _sleep, _request, _healed=False):
    qv = config["quick_view"]
    attempts = int(qv.get("retry_attempts", 2)) + 1
    timeout = float(qv.get("request_timeout_seconds", 50))
    backoff = float(qv.get("retry_backoff_seconds", 2))
    last_exc = None
    for attempt in range(1, attempts + 1):
        headers = token_manager.get_valid_headers(dict(base_headers))
        try:
            code, payload = _request(url, headers, timeout)
            if is_auth_expired(payload, code):
                if not _healed:
                    token_manager.invalidate_cache()
                    token_manager.refresh_from_command()
                    return _fetch_with_retry(url, config, token_manager, base_headers,
                                             _sleep, _request, _healed=True)
                raise AuthExpiredError("鉴权失效，刷新后仍失败。")
            if code == 200 and payload.get("code") in (None, 200, "200", "OK"):
                return payload
            # 业务错误：不重试，立即抛出（由 enrich_asins 跳过该批）。
            raise BusinessError(f"code={payload.get('code')} http={code}")
        except urllib.error.HTTPError as e:
            if e.code in RETRY_HTTP and attempt < attempts:
                _sleep(backoff * attempt); continue
            if e.code == 401 and not _healed:
                token_manager.invalidate_cache(); token_manager.refresh_from_command()
                return _fetch_with_retry(url, config, token_manager, base_headers,
                                         _sleep, _request, _healed=True)
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_exc = e
            if attempt < attempts:
                _sleep(backoff * attempt); continue
            raise
    raise last_exc or RuntimeError("quick-view 请求失败")
