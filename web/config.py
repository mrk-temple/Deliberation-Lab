"""解析仓库根、读 config.yaml、加载环境变量。"""
from __future__ import annotations
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

# web/ 的上一级就是仓库根
REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
PERSONAS_DIR = REPO_ROOT / "personas"

# 仅加载本项目凭据；进程环境优先于本地文件。
load_dotenv(WEB_DIR / ".env", override=False)


def load_config() -> dict:
    path = REPO_ROOT / "config.yaml"
    if not path.exists():
        path = REPO_ROOT / "config.example.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()


def llm_settings() -> dict:
    llm = CONFIG.get("llm", {})
    base_url = os.environ.get(llm.get("base_url_env", "MIMO_BASE_URL"), "") or llm.get(
        "base_url_default", "https://api.xiaomimimo.com/v1"
    )
    api_key = os.environ.get(llm.get("api_key_env", "MIMO_API_KEY"), "")
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": os.environ.get("JIEHUO_MODEL") or llm.get("model", "mimo-v2.6-flash"),
        "temperature": llm.get("temperature", 0.85),
        "max_tokens": llm.get("max_tokens", 1200),
    }


def output_dir() -> Path:
    """Obsidian 笔记输出目录：环境变量 JIEHUO_OUTPUT_DIR > config.yaml > 默认 ~/Obsidian Vault。"""
    p = os.environ.get("JIEHUO_OUTPUT_DIR") or CONFIG.get("output_dir") or "~/Obsidian Vault/解惑议事厅"
    return Path(p).expanduser()


def db_path() -> Path:
    p = Path(os.environ.get("JIEHUO_DB_PATH") or CONFIG.get("web", {}).get("db_path", "web/council.db"))
    return p if p.is_absolute() else REPO_ROOT / p
