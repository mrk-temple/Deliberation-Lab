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

# 加载密钥：优先 web/.env，其次 infoflow 的 .env（复用已有 DeepSeek key），最后进程环境
_INFOFLOW_ENV = Path(
    "/mnt/e/Projects/idea/信息流+个人画像+日报反馈_agent-skill/personal-infoflow/.env"
)
for _env in (WEB_DIR / ".env", _INFOFLOW_ENV):
    if _env.exists():
        load_dotenv(_env, override=False)


def load_config() -> dict:
    with open(REPO_ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()


def llm_settings() -> dict:
    llm = CONFIG.get("llm", {})
    base_url = os.environ.get(llm.get("base_url_env", ""), "") or llm.get(
        "base_url_default", "https://api.deepseek.com"
    )
    api_key = os.environ.get(llm.get("api_key_env", "DEEPSEEK_API_KEY"), "")
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": llm.get("model", "deepseek-v4-pro"),
        "temperature": llm.get("temperature", 0.85),
        "max_tokens": llm.get("max_tokens", 1200),
    }


def output_dir() -> Path:
    """Obsidian 笔记输出目录：环境变量 JIEHUO_OUTPUT_DIR > config.yaml > 默认 ~/Obsidian Vault。"""
    p = os.environ.get("JIEHUO_OUTPUT_DIR") or CONFIG.get("output_dir") or "~/Obsidian Vault/解惑议事厅"
    return Path(p).expanduser()


def db_path() -> Path:
    p = Path(CONFIG.get("web", {}).get("db_path", "web/council.db"))
    return p if p.is_absolute() else REPO_ROOT / p
