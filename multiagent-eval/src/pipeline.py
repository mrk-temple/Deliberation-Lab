"""主评测流水线：加载场景 → 切换后端 → 调用 orchestrator → 采集 Trace → Judge 打分 → 存储。

后端切换通过上下文管理器 patch llm 模块的全局变量（_client/_S/_PROVIDER），
不改动 Deliberation-Lab 现有代码。GLM 和 DeepSeek 都走 OpenAI 兼容接口。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import AsyncOpenAI

# ── 路径设置 ────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent          # multiagent-eval/src/
EVAL_ROOT = SRC_DIR.parent                          # multiagent-eval/
REPO_ROOT = EVAL_ROOT.parent                        # Deliberation-Lab/
WEB_DIR = REPO_ROOT / "web"

# src/ 自身（for trace, judge）+ web/（for orchestrator, personas, llm, config）
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(WEB_DIR))

# 现在可以 import Deliberation-Lab 的模块了
import orchestrator        # noqa: E402
import personas            # noqa: E402
import llm                 # noqa: E402

from trace import Trace, TraceTurn, collect_from_orchestrator    # noqa: E402
import judge                                                    # noqa: E402

# ── 加载环境变量 ────────────────────────────────────────────────
def _load_env():
    """加载 API key：~/.hermes/.env（GLM）+ infoflow .env（DeepSeek）。"""
    for env_path in [
        Path.home() / ".hermes" / ".env",
        Path("/mnt/e/Projects/idea/信息流+个人画像+日报反馈_agent-skill/personal-infoflow/.env"),
        WEB_DIR / ".env",
    ]:
        if env_path.exists():
            load_dotenv(env_path, override=False)


# ── 配置加载 ────────────────────────────────────────────────────

def load_scenarios() -> list[dict]:
    with open(EVAL_ROOT / "config" / "scenarios.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["scenarios"]


def load_dimensions() -> list[dict]:
    with open(EVAL_ROOT / "config" / "dimensions.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data["dimensions"]


def load_weights() -> dict:
    with open(EVAL_ROOT / "config" / "dimensions.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f).get("weights", {})


def load_models() -> dict:
    with open(EVAL_ROOT / "config" / "models.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_backend(backend_name: str, models_cfg: dict) -> dict:
    """解析后端配置，从环境变量读取 api_key 和 base_url。"""
    cfg = models_cfg["backends"][backend_name]
    base_url = os.environ.get(cfg["base_url_env"], cfg["base_url_default"])
    api_key = os.environ.get(cfg["api_key_env"], "")
    return {
        "name": backend_name,
        "label": cfg["name"],
        "base_url": base_url,
        "api_key": api_key,
        "model": cfg["model"],
        "temperature": cfg.get("temperature", 0.85),
        "max_tokens": cfg.get("max_tokens", 1200),
    }


# ── 后端切换 ────────────────────────────────────────────────────

@contextmanager
def switch_backend(backend: dict):
    """上下文管理器：临时 patch llm 模块的后端配置，退出时 restore。

    GLM 和 DeepSeek 都走 OpenAI 兼容接口（llm.py 的非 claude_cli 路径），
    所以只需切 _client / _S["model"] / _PROVIDER。
    """
    if not backend["api_key"]:
        raise RuntimeError(
            f"后端 {backend['name']} 的 API key 未配置"
            f"（环境变量 {backend.get('api_key_env', '?')} 为空）"
        )

    old_provider = llm._PROVIDER
    old_client = llm._client
    old_model = llm._S.get("model")
    old_temp = llm._S.get("temperature")
    old_max = llm._S.get("max_tokens")
    old_base = llm._S.get("base_url")
    old_key = llm._S.get("api_key")

    llm._PROVIDER = "deepseek"  # OpenAI 兼容模式（非 claude_cli）
    llm._client = AsyncOpenAI(api_key=backend["api_key"], base_url=backend["base_url"])
    llm._S["model"] = backend["model"]
    llm._S["temperature"] = backend["temperature"]
    llm._S["max_tokens"] = backend["max_tokens"]
    llm._S["base_url"] = backend["base_url"]
    llm._S["api_key"] = backend["api_key"]

    try:
        yield
    finally:
        llm._PROVIDER = old_provider
        llm._client = old_client
        llm._S["model"] = old_model
        llm._S["temperature"] = old_temp
        llm._S["max_tokens"] = old_max
        llm._S["base_url"] = old_base
        llm._S["api_key"] = old_key


# ── 运行单个场景 ────────────────────────────────────────────────

async def run_scenario(
    scenario: dict,
    backend: dict,
) -> Trace:
    """用一个后端跑一个场景的所有 turn，返回完整 Trace。"""
    trace = Trace(
        scenario_id=scenario["id"],
        backend=backend["name"],
        model=backend["model"],
        mode=scenario["mode"],
        persona_ids=scenario["persona_ids"],
    )

    messages: list[dict] = []  # 累积多轮对话

    for i, turn_def in enumerate(scenario["turns"]):
        user_msg = turn_def["user"]
        messages.append({"role": "user", "content": user_msg})

        if scenario["mode"] == "solo":
            gen = orchestrator.solo(
                scenario["persona_ids"][0],
                messages,
            )
        else:
            council = scenario["mode"] == "council"
            gen = orchestrator.roundtable(
                scenario["persona_ids"],
                messages,
                council=council,
            )

        turn_trace = await collect_from_orchestrator(gen, i, user_msg)

        if turn_trace.error:
            print(f"    [!] turn {i} 错误: {turn_trace.error}")
            # 仍然记录，但不继续后续 turn
            trace.turns.append(turn_trace)
            break

        # 检查是否有发言者缺失（roundtable/council 模式）
        if scenario["mode"] != "solo":
            expected = set(scenario["persona_ids"])
            actual = {s.id for s in turn_trace.speakers}
            missing = expected - actual
            if missing:
                print(f"    [!] 警告: 以下角色未发言: {missing}")

        trace.turns.append(turn_trace)

        # solo 模式：把 assistant 回复加入 messages 供下一轮使用
        if scenario["mode"] == "solo" and turn_trace.speakers:
            sp = turn_trace.speakers[0]
            messages.append({
                "role": "assistant",
                "content": sp.text,
                "speaker": sp.name,
            })

        print(f"    turn {i} 完成: {len(turn_trace.speakers)} 位发言者"
              + (f" + 书记官" if turn_trace.moderator else ""))

    return trace


# ── 评测一条 trace ──────────────────────────────────────────────

async def judge_trace(
    trace: Trace,
    scenario: dict,
    dimensions: list[dict],
    judge_backend: dict,
    personas_cache: dict,
) -> dict:
    """切换到 Judge 后端，对 trace 评分。"""
    # 获取参与智者的完整档案
    personas_info = []
    for pid in scenario["persona_ids"]:
        p = personas_cache.get(pid)
        if p:
            personas_info.append(p)

    with switch_backend(judge_backend):
        result = await judge.judge_trace(
            trace, scenario, personas_info, dimensions, llm.complete,
        )
    return result


# ── 存储结果 ────────────────────────────────────────────────────

def save_result(
    trace: Trace,
    judge_result: dict,
    scenario: dict,
    backend: dict,
    weights: dict,
) -> Path:
    """保存单条评测结果到 results/。"""
    results_dir = EVAL_ROOT / "results"
    results_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{scenario['id']}_{backend['name']}_{ts}.json"
    path = results_dir / filename

    scores = judge_result.get("scores", {})
    weighted = judge.compute_weighted_score(scores, weights)

    data = {
        "scenario_id": scenario["id"],
        "scenario_title": scenario["title"],
        "backend": backend["name"],
        "model": backend["model"],
        "mode": scenario["mode"],
        "timestamp": trace.timestamp,
        "primary_dimensions": scenario.get("primary_dimensions", []),
        "trace": trace.to_dict(),
        "scores": scores,
        "weighted_score": weighted,
        "overall_assessment": judge_result.get("overall_assessment", ""),
        "rule_flags": judge_result.get("rule_flags", []),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return path


def save_summary(all_results: list[dict]) -> Path:
    """保存汇总摘要到 results/summary.json。"""
    results_dir = EVAL_ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    path = results_dir / "summary.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    return path


# ── 主入口 ──────────────────────────────────────────────────────

async def run_eval(
    scenario_filter: str | None = None,
    backend_filter: str | None = None,
) -> list[dict]:
    """主评测入口：跑指定场景 × 指定后端，返回汇总结果。

    scenario_filter: 只跑指定 ID 的场景（None=全部）
    backend_filter:  只跑指定后端（None=全部对比）
    """
    _load_env()

    scenarios = load_scenarios()
    dimensions = load_dimensions()
    weights = load_weights()
    models_cfg = load_models()

    if scenario_filter:
        scenarios = [s for s in scenarios if s["id"] == scenario_filter]
    if not scenarios:
        print("没有匹配的场景")
        return []

    backend_names = models_cfg["default_compare"]
    if backend_filter:
        backend_names = [backend_filter]

    judge_name = models_cfg.get("judge_backend", "glm")
    judge_backend = resolve_backend(judge_name, models_cfg)

    # 预加载人物档案（带缓存）
    personas_cache = personas.load_all()

    all_results: list[dict] = []

    total = len(scenarios) * len(backend_names)
    done = 0

    for scenario in scenarios:
        print(f"\n{'='*60}")
        print(f"场景: {scenario['title']} ({scenario['id']})")
        print(f"模式: {scenario['mode']}  角色: {scenario['persona_ids']}")

        for bname in backend_names:
            done += 1
            print(f"\n[{done}/{total}] 后端: {bname}")

            try:
                backend = resolve_backend(bname, models_cfg)

                # 1. 运行场景，采集 trace
                with switch_backend(backend):
                    trace = await run_scenario(scenario, backend)

                # 2. Judge 打分（失败时仍保存 trace）
                print(f"    Judge 评分中... (judge={judge_name})")
                try:
                    judge_result = await judge_trace(
                        trace, scenario, dimensions, judge_backend, personas_cache,
                    )
                except Exception as je:
                    print(f"    [!] Judge 失败，trace 仍保存: {je}")
                    judge_result = {
                        "scores": {},
                        "overall_assessment": f"Judge 失败: {je}",
                        "rule_flags": [],
                    }

                # 3. 存储
                path = save_result(trace, judge_result, scenario, backend, weights)
                weighted = judge.compute_weighted_score(
                    judge_result.get("scores", {}), weights,
                )

                print(f"    综合分: {weighted}")
                for dim_id, s in judge_result.get("scores", {}).items():
                    score = s.get("score", "?")
                    print(f"      {dim_id}: {score}")

                all_results.append({
                    "scenario_id": scenario["id"],
                    "scenario_title": scenario["title"],
                    "backend": bname,
                    "model": backend["model"],
                    "mode": scenario["mode"],
                    "weighted_score": weighted,
                    "scores": judge_result.get("scores", {}),
                    "rule_flags": judge_result.get("rule_flags", []),
                    "result_file": path.name,
                })

            except Exception as e:
                print(f"    [ERROR] {e}")
                traceback.print_exc()
                all_results.append({
                    "scenario_id": scenario["id"],
                    "scenario_title": scenario["title"],
                    "backend": bname,
                    "error": str(e),
                })

    # 保存汇总
    if all_results:
        summary_path = save_summary(all_results)
        print(f"\n{'='*60}")
        print(f"评测完成！汇总结果: {summary_path}")
        print(f"共 {len(all_results)} 条结果")

    return all_results
