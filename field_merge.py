"""字段归一、扁平化。"""
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
        # bsrList: 取 main=true 的 rank -> __main_rank，其余第一个 -> __sub_rank
        if obj and all(isinstance(x, dict) for x in obj):
            main_rank, sub_rank = None, None
            for item in obj:
                if item.get("main"):
                    main_rank = item.get("rank")
                elif sub_rank is None:
                    sub_rank = item.get("rank")
            if main_rank is not None:
                out[f"{prefix}__main_rank"] = main_rank
            if sub_rank is not None:
                out[f"{prefix}__sub_rank"] = sub_rank
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
