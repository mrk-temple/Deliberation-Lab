"""Badcase 分析脚本：生成评测报告 + 回流方案。

用法：
  python scripts/analyze_badcases.py                # 生成报告
  python scripts/analyze_badcases.py --feedback     # 生成报告 + 执行回流
  python scripts/analyze_badcases.py --dry-run      # 生成报告 + 预览回流（不修改文件）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from reporter import load_all_results, generate_report, extract_badcases  # noqa: E402
from feedback import (  # noqa: E402
    load_results,
    feedback_to_personas,
    feedback_to_orchestrator,
    generate_validation_plan,
    save_feedback_report,
)


def main():
    parser = argparse.ArgumentParser(description="Badcase 分析与回流")
    parser.add_argument(
        "--feedback", action="store_true",
        help="执行回流（修改角色档案和编排提示）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只预览回流操作，不实际修改文件",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Badcase 分析与回流")
    print("=" * 60)

    # 1. 加载结果
    print("\n1. 加载评测结果...")
    results = load_all_results()
    if not results:
        print("   [!] 没有找到评测结果，请先运行 run_eval.py")
        return
    print(f"   共 {len(results)} 条结果")

    # 2. 筛选 badcase
    print("\n2. 筛选 Badcase...")
    badcases = extract_badcases(results)
    print(f"   发现 {len(badcases)} 个 Badcase")

    # 3. 生成报告
    print("\n3. 生成分析报告...")
    report_path = generate_report(results)
    print(f"   报告已保存: {report_path}")

    # 4. 回流（可选）
    if args.feedback or args.dry_run:
        action = "预览回流" if args.dry_run else "执行回流"
        print(f"\n4. {action}...")
        feedback_results = load_results()

        persona_log = feedback_to_personas(feedback_results, dry_run=args.dry_run)
        print(f"   角色档案回流: {len(persona_log)} 条操作")

        orch_log = feedback_to_orchestrator(feedback_results, dry_run=args.dry_run)
        print(f"   编排提示回流: {len(orch_log)} 条操作")

        validation_plan = generate_validation_plan(feedback_results)
        print(f"   验证计划: {len(validation_plan)} 个场景需重跑")

        fb_path = save_feedback_report(persona_log, orch_log, validation_plan)
        print(f"   回流报告: {fb_path}")

        if args.dry_run:
            print("\n   (dry-run 模式，未实际修改文件)")
        else:
            print("\n   回流完成！请重跑验证场景对比效果。")

    print("\n完成！")


if __name__ == "__main__":
    main()
