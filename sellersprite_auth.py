# sellersprite_auth.py
"""卖家精灵扩展鉴权头管理，复制自 keepa-monitor keepa_auth.py，自包含。"""
import json
import os
import subprocess
import time
from pathlib import Path

REQUIRED_HEADERS = ("auth-token", "auth-fp", "random-token")
OPTIONAL_HEADERS = ("cookie",)

ENV_HEADER_KEYS = {
    "auth-token": "KEEPA_AUTH_TOKEN",
    "auth-fp": "KEEPA_AUTH_FP",
    "random-token": "KEEPA_RANDOM_TOKEN",
    "cookie": "KEEPA_COOKIE",
}

PROJECT_ROOT = Path(__file__).resolve().parent


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y"}


class KeepaTokenManager:
    def __init__(self, cache_file: Path, ttl_seconds: int = 5400, refresh_margin_seconds: int = 60):
        self.cache_file = cache_file
        self.ttl_seconds = max(60, ttl_seconds)
        self.refresh_margin_seconds = max(10, refresh_margin_seconds)

    def _load_cache(self) -> dict | None:
        if not self.cache_file.exists():
            return None
        try:
            raw = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        expires_at = float(raw.get("expires_at", 0))
        if expires_at <= time.time() + self.refresh_margin_seconds:
            return None
        headers = raw.get("headers", {})
        if not self._has_required_headers(headers):
            return None
        return headers

    def _save_cache(self, headers: dict, ttl_seconds: int | None = None) -> None:
        safe = {}
        for key in (*REQUIRED_HEADERS, *OPTIONAL_HEADERS):
            value = str(headers.get(key, "")).strip()
            if value:
                safe[key] = value
        if not self._has_required_headers(safe):
            return
        payload = {"headers": safe, "expires_at": time.time() + float(ttl_seconds or self.ttl_seconds)}
        self.cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_from_env(self) -> dict:
        headers = {}
        for header_name, env_key in ENV_HEADER_KEYS.items():
            value = (os.getenv(env_key) or "").strip()
            if value:
                headers[header_name] = value
        return headers

    @staticmethod
    def _has_required_headers(headers: dict) -> bool:
        return all(str(headers.get(key, "")).strip() for key in REQUIRED_HEADERS)

    def get_valid_headers(self, base_headers: dict) -> dict:
        if env_bool("KEEPA_TOKEN_REFRESH_EACH_RUN", default=True):
            refreshed = self.refresh_from_command()
            if refreshed:
                merged = dict(base_headers); merged.update(refreshed); return merged

        cache_headers = self._load_cache()
        if cache_headers:
            merged = dict(base_headers); merged.update(cache_headers); return merged

        env_headers = self._load_from_env()
        if self._has_required_headers(env_headers):
            merged = dict(base_headers); merged.update(env_headers)
            self._save_cache(merged); return merged

        refreshed = self.refresh_from_command()
        if refreshed:
            merged = dict(base_headers); merged.update(refreshed); return merged

        missing = ", ".join(ENV_HEADER_KEYS[k] for k in REQUIRED_HEADERS)
        raise RuntimeError(
            "缺少卖家精灵鉴权信息。请在 .env 配置 " + missing +
            "，或设置 KEEPA_TOKEN_REFRESH_COMMAND 自动刷新。")

    def refresh_from_command(self) -> dict | None:
        command = (os.getenv("KEEPA_TOKEN_REFRESH_COMMAND") or "").strip()
        if not command:
            return None
        try:
            result = subprocess.run(
                command, shell=True, cwd=str(PROJECT_ROOT), capture_output=True,
                text=True, timeout=float(os.getenv("KEEPA_TOKEN_REFRESH_TIMEOUT_SECONDS", "45")), check=False)
        except Exception as exc:
            raise RuntimeError(f"执行 KEEPA_TOKEN_REFRESH_COMMAND 失败: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError("KEEPA_TOKEN_REFRESH_COMMAND 执行失败，exit=" +
                               f"{result.returncode}, stderr={(result.stderr or '').strip() or '(empty)'}")
        stdout = (result.stdout or "").strip()
        if not stdout:
            raise RuntimeError("KEEPA_TOKEN_REFRESH_COMMAND 未输出 JSON。")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("KEEPA_TOKEN_REFRESH_COMMAND 输出不是合法 JSON。") from exc
        headers = {}
        for key in (*REQUIRED_HEADERS, *OPTIONAL_HEADERS):
            value = str(payload.get(key, "")).strip()
            if value:
                headers[key] = value
        if not self._has_required_headers(headers):
            raise RuntimeError("KEEPA_TOKEN_REFRESH_COMMAND 输出缺少必需字段 "
                               "(auth-token/auth-fp/random-token)。")
        ttl_seconds = int(payload.get("ttl_seconds", self.ttl_seconds))
        self._save_cache(headers, ttl_seconds=ttl_seconds)
        return headers

    def invalidate_cache(self) -> None:
        if self.cache_file.exists():
            self.cache_file.unlink()
