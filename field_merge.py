"""字段归一、扁平化、派生字段。"""
import datetime
import json
import re

CANONICAL_FIELD_MAP = {
    "buyPrice": "buy_price",
}


def camel_to_snake(s: str) -> str:
    s = CANONICAL_FIELD_MAP.get(s, s)
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _flatten(obj, prefix, out):
    if isinstance(obj, dict):
        # dict[str, scalar] -> 子键；dict[str, list/dict] -> 递归
        list_vals = {k: v for k, v in obj.items() if isinstance(v, (list, dict))}
        scalars = {k: v for k, v in obj.items() if not isinstance(v, (list, dict))}
        for k, v in scalars.items():
            out[f"{prefix}__{camel_to_snake(k)}" if prefix else camel_to_snake(k)] = v
        for k, v in list_vals.items():
            _flatten(v, f"{prefix}__{camel_to_snake(k)}" if prefix else camel_to_snake(k), out)
    elif isinstance(obj, list):
        # bsrList: 取 main=true 的 rank/label -> __main_rank/__main_label，其余第一个 -> __sub_*
        if obj and all(isinstance(x, dict) for x in obj):
            main_rank, sub_rank = None, None
            main_label, sub_label = None, None
            for item in obj:
                if item.get("main"):
                    main_rank = item.get("rank")
                    main_label = item.get("label")
                elif sub_rank is None:
                    sub_rank = item.get("rank")
                    sub_label = item.get("label")
            if main_rank is not None:
                out[f"{prefix}__main_rank"] = main_rank
            if main_label:
                out[f"{prefix}__main_label"] = main_label
            if sub_rank is not None:
                out[f"{prefix}__sub_rank"] = sub_rank
            if sub_label:
                out[f"{prefix}__sub_label"] = sub_label
            # 也保留原始 JSON 以不丢信息
            out[prefix] = json.dumps(obj, ensure_ascii=False)
        else:
            out[prefix] = json.dumps(obj, ensure_ascii=False)


def flatten_record(rec: dict) -> dict:
    out = {}
    _flatten(rec, "", out)
    return out


def to_number(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"-?\d+(?:\.\d+)?", str(val).replace(",", ""))
    return float(m.group()) if m else None


def large_image_url(url):
    """从亚马逊封面图 URL 派生 1500px 高清版（同图床同 ID，换尺寸标识，无需额外请求）。
    图片 ID 可能含 + / % 等字符（如 71+oszjnRVL），用非贪婪匹配到尺寸码前的 '.'。
    非亚马逊图床或无 URL 时：原样返回 / None。"""
    if not url:
        return None
    m = re.search(r"/images/I/([^/.]+?)\._", url)
    if not m:
        return url
    return f"https://images-na.ssl-images-amazon.com/images/I/{m.group(1)}._AC_SL1500_.jpg"


def product_url(asin):
    """由 ASIN 派生亚马逊商品详情页链接（competitor-lookup 不返回 url）。"""
    return f"https://www.amazon.com/dp/{asin}" if asin else None


def available_date(available_ms):
    """上架时间毫秒时间戳 → yyyy-mm-dd（UTC，匹配卖家精灵上架日）。无值返回 None。"""
    if not available_ms:
        return None
    return datetime.datetime.fromtimestamp(available_ms / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
