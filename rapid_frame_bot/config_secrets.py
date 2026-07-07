from __future__ import annotations
import os


def _parse_key_file(path: str) -> tuple[str, str]:
    api_key = api_secret = ""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if ":" not in line:
                continue
            label, _, value = line.partition(":")
            label = label.strip().lower()
            value = value.strip()
            if label in ("api_key", "apikey", "key"):
                api_key = value
            elif label in ("secret key", "secret", "api_secret"):
                api_secret = value
    return api_key, api_secret


def load_keys(exchange_name: str,
              secrets_dir: str = "secrets") -> tuple[str, str]:
    """env 優先（{NAME}_API_KEY / {NAME}_API_SECRET），缺則回退讀 secrets/{name}.txt。"""
    upper = exchange_name.upper()
    env_key = os.environ.get(f"{upper}_API_KEY", "")
    env_secret = os.environ.get(f"{upper}_API_SECRET", "")
    if env_key and env_secret:
        return env_key, env_secret
    path = os.path.join(secrets_dir, f"{exchange_name.lower()}.txt")
    if os.path.exists(path):
        fk, fs = _parse_key_file(path)
        return env_key or fk, env_secret or fs
    return env_key, env_secret
