"""一键评测脚本。

用法：
  python scripts/run_eval.py                          # 跑全部场景 × 全部后端
  python scripts/run_eval.py --scenario career_pivot  # 只跑指定场景
  python scripts/run_eval.py --backend glm            # 只跑指定后端
  python scripts/run_eval.py --scenario career_pivot --backend glm  # 指定场景+后端
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 把 src/ 加入 path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from pipeline import run_eval  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Deliberation-Lab · 多智能体决策评测"
    )
    parser.add_argument(
        "--scenario", "-s", default=None,
        help="只跑指定场景 ID（如 career_pivot），不指定则跑全部",
    )
    parser.add_argument(
        "--backend", "-b", default=None,
        help="只跑指定后端（glm / deepseek），不指定则跑全部对比",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Deliberation-Lab · 多智能体决策评测")
    print("=" * 60)
    if args.scenario:
        print(f"场景过滤: {args.scenario}")
    if args.backend:
        print(f"后端过滤: {args.backend}")
    if not args.scenario and not args.backend:
        print("全量评测：所有场景 × 所有后端")

    asyncio.run(run_eval(
        scenario_filter=args.scenario,
        backend_filter=args.backend,
    ))


if __name__ == "__main__":
    main()
