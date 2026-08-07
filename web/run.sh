#!/usr/bin/env bash
# 启动解惑议事厅 web。首次运行会建 venv 装依赖。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV="$HERE/.venv"
if [[ ! -d "$VENV" ]]; then
  echo "首次运行：创建虚拟环境并安装依赖…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r requirements.txt
fi

# 没有 web/.env 时，复用 infoflow 的 DeepSeek key（不复制密钥，只在运行时读取）
INFOFLOW_ENV="/mnt/e/Projects/idea/信息流+个人画像+日报反馈_agent-skill/personal-infoflow/.env"
if [[ ! -f "$HERE/.env" && -f "$INFOFLOW_ENV" ]]; then
  echo "用 infoflow 的 DeepSeek key 运行（如需独立配置，复制 .env.example 为 .env）"
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8787}"
echo "解惑议事厅 → http://$HOST:$PORT"
exec "$VENV/bin/uvicorn" app:app --host "$HOST" --port "$PORT"
