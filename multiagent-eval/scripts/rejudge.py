"""补评分脚本：从已有结果文件中加载 trace，只重跑 Judge 评分。

用于 Judge 后端故障或更换 Judge 后端后，不需要重跑场景采集。

用法：
  python scripts/rejudge.py                    # 对所有缺评分的结果补评分
  python scripts/rejudge.py --all              # 对所有结果重新评分
  python scripts/rejudge.py --file career_pivot_deepseek_xxx.json  # 指定文件
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from pipeline import (  # noqa: E402
    _load_env, load_scenarios, load_dimensions, load_weights, load_models,
    resolve_backend, switch_backend, judge_trace, save_result,
)
from trace import Trace, TraceTurn, SpeakerTurn  # noqa: E402
import personas  # noqa: E402
import llm  # noqa: E402
import judge as judge_mod  # noqa: E402


EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = EVAL_ROOT / "results"


def _reconstruct_trace(data: dict) -> Trace:
    """从 JSON 结果文件中重建 Trace 对象。"""
    raw_trace = data["trace"]
    trace = Trace(
        scenario_id=raw_trace["scenario_id"],
        backend=raw_trace["backend"],
        model=raw_trace["model"],
        mode=raw_trace["mode"],
        persona_ids=raw_trace["persona_ids"],
        timestamp=raw_trace.get("timestamp", ""),
    )
    for raw_turn in raw_trace.get("turns", []):
        turn = TraceTurn(
            turn_index=raw_turn["turn_index"],
            user_message=raw_turn["user_message"],
            error=raw_turn.get("error", ""),
        )
        for raw_s in raw_turn.get("speakers", []):
            turn.speakers.append(SpeakerTurn(
                id=raw_s["id"], name=raw_s["name"],
                school=raw_s["school"], text=raw_s["text"],
            ))
        mod = raw_turn.get("moderator")
        if mod:
            turn.moderator = SpeakerTurn(
                id=mod["id"], name=mod["name"],
                school=mod["school"], text=mod["text"],
            )
        trace.turns.append(turn)
    return trace


async def rejudge_file(
    path: Path,
    scenarios: list[dict],
    dimensions: list[dict],
    weights: dict,
    judge_backend: dict,
    personas_cache: dict,
) -> bool:
    """对一个结果文件重新评分。返回是否成功。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # 找到对应场景定义
    scenario = next((s for s in scenarios if s["id"] == data["scenario_id"]), None)
    if not scenario:
        print(f"  [!] 找不到场景定义: {data['scenario_id']}")
        return False

    # 重建 trace
    trace = _reconstruct_trace(data)
    if not trace.turns:
        print(f"  [!] 无 trace 数据: {path.name}")
        return False

    # 检查是否有发言者文本
    has_content = any(
        s.text.strip() for turn in trace.turns for s in turn.speakers
    ) or any(
        turn.moderator and turn.moderator.text.strip() for turn in trace.turns
    )
    if not has_content:
        print(f"  [!] trace 中无实际内容: {path.name}")
        return False

    # 重跑 Judge
    print(f"  Judge 评分中... (judge={judge_backend['name']})")
    try:
        judge_result = await judge_trace(
            trace, scenario, dimensions, judge_backend, personas_cache,
        )
    except Exception as e:
        print(f"  [ERROR] Judge 失败: {e}")
        return False

    # 保存
    backend = {"name": data["backend"], "model": data["model"]}
    new_path = save_result(trace, judge_result, scenario, backend, weights)
    weighted = judge_mod.compute_weighted_score(
        judge_result.get("scores", {}), weights,
    )

    print(f"  综合分: {weighted}")
    for dim_id, s in judge_result.get("scores", {}).items():
        score = s.get("score", "?")
        print(f"    {dim_id}: {score}")

    return True


async def main():
    parser = argparse.ArgumentParser(description="补评分 / 重评分")
    parser.add_argument("--all", action="store_true", help="对所有结果重新评分")
    parser.add_argument("--file", default=None, help="指定结果文件名")
    args = parser.parse_args()

    _load_env()

    scenarios = load_scenarios()
    dimensions = load_dimensions()
    weights = load_weights()
    models_cfg = load_models()
    judge_name = models_cfg.get("judge_backend", "judge")
    judge_backend = resolve_backend(judge_name, models_cfg)
    personas_cache = personas.load_all()

    print("=" * 60)
    print(f"补评分（Judge: {judge_backend['name']} / {judge_backend['model']}）")
    print("=" * 60)

    # 收集需要处理的结果文件
    result_files = sorted(RESULTS_DIR.glob("*.json"))
    result_files = [f for f in result_files if f.name != "summary.json" and not f.name.endswith(".log")]

    to_process = []
    for f in result_files:
        if args.file and f.name != args.file:
            continue
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        scores = data.get("scores", {})
        has_scores = bool(scores) and any(
            isinstance(s.get("score"), (int, float)) for s in scores.values()
        )
        if args.all or not has_scores:
            to_process.append(f)

    if not to_process:
        print("没有需要补评分的结果文件。")
        return

    print(f"共 {len(to_process)} 个文件需要评分\n")

    success = 0
    for i, path in enumerate(to_process, 1):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"[{i}/{len(to_process)}] {data.get('scenario_title','')} ({data.get('backend','')})")
        ok = await rejudge_file(path, scenarios, dimensions, weights, judge_backend, personas_cache)
        if ok:
            success += 1
        print()

    print(f"完成：{success}/{len(to_process)} 成功")


if __name__ == "__main__":
    asyncio.run(main())
