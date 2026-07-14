"""Leg B：competitor-lookup 批量增强（可并发）。"""
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
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


def build_competitor_url(config: dict, asins: list) -> str:
    """competitor-lookup 端点（单接口全量：亚马逊字段 + 卖家精灵增强 57 字段）。
    URL 形如 .../competitor-lookup/US?asins=A,B&...（从 quick_view.base_url 去掉 /quick-view 派生）。"""
    asins_str = ",".join(asins)
    tk = sellersprite_token(asins_str, ext_version=extension_version_token(config["version"]))
    base = config["quick_view"]["base_url"].rsplit("/quick-view", 1)[0]  # → .../competitor-lookup
    params = (
        f"asins={asins_str}",
        f"source={config['source']}",
        f"tk={tk}",
        f"version={config['version']}",
        f"language={config['language']}",
        f"extension={config['extension_id']}",
    )
    return f"{base}/{config['station']}?" + "&".join(params)


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


def lookup_asins(asins: list, config: dict, token_manager, base_headers: dict,
                 _sleep=time.sleep, _request=_do_request) -> dict:
    """competitor-lookup：给定 ASIN，返回 {asin: item}（每条 57 字段，亚马逊+增强全量）。
    按 batch_size 分批，多批通过 ThreadPoolExecutor 并发（worker 数 = concurrency.workers，
    默认 3）；单批或 workers<=1 时走顺序路径并保留批间延时。复用 enrich 的重试 / 鉴权自愈 /
    业务跳过逻辑。"""
    qv = config["quick_view"]
    batch = qv.get("batch_size", 20)
    workers = max(1, int((config.get("concurrency") or {}).get("workers", 3)))
    chunks = [asins[i:i + batch] for i in range(0, len(asins), batch)]

    def fetch_chunk(chunk):
        url = build_competitor_url(config, chunk)
        try:
            payload = _fetch_with_retry(url, config, token_manager, base_headers, _sleep, _request)
        except BusinessError as e:
            print(f"⚠️ competitor-lookup 业务错误，跳过该批: {e}")
            return []
        return parse_quickview(payload)

    result = {}
    if workers == 1 or len(chunks) <= 1:
        # 顺序路径：保留批间随机延时（礼貌限速）
        for idx, chunk in enumerate(chunks):
            for item in fetch_chunk(chunk):
                result[item.get("asin")] = item
            if idx < len(chunks) - 1:
                _sleep(random.uniform(qv.get("delay_seconds_min", 5), qv.get("delay_seconds_max", 8)))
    else:
        # 并发路径：worker 数本身即限速，不再加批间延时
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for items in ex.map(fetch_chunk, chunks):
                for item in items:
                    result[item.get("asin")] = item
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
            # 业务错误：不重试，立即抛出（由调用方 lookup_asins 跳过该批）。
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
