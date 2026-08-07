"""自动化 Judge：规则检查 + LLM-as-Judge。

规则检查（硬性，直接定分或设上限）：
  - 检测到"作为AI/语言模型" → 角色一致性 = 1
  - 检测到第三人称自称 → 角色一致性 ≤ 2
  - 抉择模式无具体行动 → 结论可执行性 ≤ 2

LLM-as-Judge（柔性，按 rubric 打分）：
  - 把场景 + trace + persona method + rubric 喂给 Judge 模型
  - 输出每个维度的 1-5 分 + 理由 + 问题点
"""
from __future__ import annotations

import json
import re

from trace import Trace

# ── 规则检查 ────────────────────────────────────────────────────

# AI 自曝模式
_AI_PATTERNS = [
    r"作为\s*AI",
    r"作为\s*语言模型",
    r"作为\s*人工智能",
    r"As an AI",
    r"I'?m an AI",
    r"I am an AI",
    r"作为\s*大语言模型",
]
_AI_RE = re.compile("|".join(_AI_PATTERNS), re.IGNORECASE)

# 第三人称自称（如费曼说"费曼认为"）
# 匹配模式：<人物名> + (认为|觉得|建议|相信|主张)
_THIRD_PERSON_RE = re.compile(
    r"(?:我|本人).{0,4}(?:认为|觉得|建议|相信|主张)"
)
# 更直接：发言者用自己的名字指代自己
# 这个在中文里较难精确匹配，先用宽松规则


def check_ai_self_disclosure(trace: "Trace") -> bool:
    """检查是否有任何发言者说出'作为AI'类话术。"""
    for turn in trace.turns:
        for s in turn.speakers:
            if _AI_RE.search(s.text):
                return True
        if turn.moderator and _AI_RE.search(turn.moderator.text):
            return True
    return False


def check_no_concrete_action(trace: "Trace") -> bool:
    """抉择模式：书记官结论中是否完全没有具体行动建议。

    启发式：检测是否包含时间词（今天/本周/现在/立刻）或动词指令
    （去做/写下/列出/找/问/尝试/开始）。
    """
    if trace.mode != "council":
        return False
    mod_text = ""
    for turn in trace.turns:
        if turn.moderator:
            mod_text += turn.moderator.text
    if not mod_text:
        return True  # 连书记官结论都没有

    action_hints = [
        "今天", "本周", "现在", "立刻", "马上", "今晚", "明早",
        "去做", "写下", "列出", "找", "问", "尝试", "开始",
        "第一步", "接下来", "具体",
    ]
    return not any(h in mod_text for h in action_hints)


# ── LLM-as-Judge ────────────────────────────────────────────────

def _build_judge_prompt(
    trace: "Trace",
    scenario: dict,
    personas_info: list[dict],
    dimensions: list[dict],
) -> list[dict]:
    """构建 Judge 的 system + user 消息。"""

    # 场景信息
    scenario_block = (
        f"【场景】{scenario['title']}\n"
        f"【场景描述】{scenario['description']}\n"
        f"【任务目标】{scenario['task_goal']}\n"
        f"【成功标准】{scenario['success_criteria']}\n"
        f"【模式】{trace.mode}\n"
        f"【后端模型】{trace.backend} ({trace.model})\n"
    )

    # 各位智者的 method（用于评方法运用度）
    persona_block_parts = []
    for p in personas_info:
        sections = p.get("sections", {})
        persona_block_parts.append(
            f"── {p['name']}（{p['school']}）──\n"
            f"  method: {sections.get('method', '（未定义）')}\n"
            f"  pushback_on: {sections.get('pushback_on', '（未定义）')}\n"
            f"  voice: {sections.get('voice', '（未定义）')}"
        )
    persona_block = "\n".join(persona_block_parts)

    # 维度 rubric
    rubric_parts = []
    for d in dimensions:
        rubric_parts.append(
            f"── {d['name']}（{d['id']}，{d['scale']}分）──\n"
            f"  {d['description']}\n"
            + "\n".join(f"  {k}分: {v}" for k, v in d["rubric"].items())
        )
    rubric_block = "\n".join(rubric_parts)

    system = (
        "你是多智能体决策系统的评测裁判。你的任务是根据评分标准（rubric），"
        "对一次多智能体对话进行客观评分。\n\n"
        "要求：\n"
        "1. 严格按照 rubric 打分，1分最差，5分最好\n"
        "2. 每个维度给出分数 + 理由 + 具体问题点\n"
        "3. 特别关注：角色是否崩坏、pushback是否到位、结论是否可落地、多轮是否一致、"
        "method是否真正运用\n"
        "4. 只返回 JSON，不要任何别的字\n\n"
        "JSON 格式：\n"
        "{\n"
        '  "scores": {\n'
        '    "role_consistency": {"score": N, "reason": "...", "issue": "..."},\n'
        '    "pushback_intensity": {"score": N, "reason": "...", "issue": "..."},\n'
        '    "conclusion_actionability": {"score": N, "reason": "...", "issue": "..."},\n'
        '    "long_range_consistency": {"score": N, "reason": "...", "issue": "..."},\n'
        '    "method_application": {"score": N, "reason": "...", "issue": "..."}\n'
        "  },\n"
        '  "overall_assessment": "一句话总评"\n'
        "}"
    )

    user = (
        f"{scenario_block}\n\n"
        f"【参与智者的人设信息】\n{persona_block}\n\n"
        f"【评分标准】\n{rubric_block}\n\n"
        f"【完整对话 Trace】\n{trace.full_transcript}\n\n"
        f"请按照上述标准，对这次对话进行评分。只返回 JSON。"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_judge_response(raw: str) -> dict:
    """解析 Judge 的 JSON 响应，容错处理。"""
    # 去掉 markdown 代码块标记（```json ... ``` 或 ``` ... ```）
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # 去掉首行 ```json 或 ```
        lines = cleaned.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        # 去掉末尾 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    # 尝试直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试提取 {...} 部分
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        return json.loads(cleaned[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    # 尝试修复截断的 JSON（推理模型可能超 max_tokens 导致 JSON 不完整）
    # 找到最后一个完整的 dimension 条目
    try:
        start = cleaned.index("{")
        # 逐个找最后一个完整的 "score": N 后的 }
        fragment = cleaned[start:]
        # 尝试在截断处补全
        last_score = fragment.rfind('"score"')
        if last_score > 0:
            # 找到这个 score 后的数字和 }
            after = fragment[last_score:]
            # 尝试加 } 补全
            for attempt in [fragment + "}}}", fragment + "}}", fragment + "}"]:
                try:
                    return json.loads(attempt)
                except json.JSONDecodeError:
                    continue
    except (ValueError, json.JSONDecodeError):
        pass

    return {
        "scores": {},
        "overall_assessment": f"Judge 响应解析失败，原始响应: {raw[:300]}",
        "_parse_error": True,
    }


# ── 组合打分 ────────────────────────────────────────────────────

async def judge_trace(
    trace: "Trace",
    scenario: dict,
    personas_info: list[dict],
    dimensions: list[dict],
    llm_complete,
) -> dict:
    """对一条 trace 进行完整评分（规则 + LLM）。

    llm_complete: async callable，签名 (messages, temperature) -> str
    返回：{
        "scores": {dim_id: {"score": N, "reason": ..., "rule_override": bool}},
        "overall_assessment": str,
        "rule_flags": [...],
    }
    """
    rule_flags: list[str] = []

    # 1. LLM-as-Judge
    messages = _build_judge_prompt(trace, scenario, personas_info, dimensions)
    raw = await llm_complete(messages, temperature=0.3)
    result = _parse_judge_response(raw)
    llm_scores = result.get("scores", {})
    overall = result.get("overall_assessment", "")

    # 2. 规则覆盖
    # 规则1：AI 自曝 → 角色一致性 = 1
    if check_ai_self_disclosure(trace):
        rule_flags.append("ai_self_disclosure")
        if "role_consistency" in llm_scores:
            llm_scores["role_consistency"]["score"] = 1
            llm_scores["role_consistency"]["reason"] = (
                "[规则覆盖] 检测到'作为AI'类话术，角色一致性直接1分。"
            )
            llm_scores["role_consistency"]["rule_override"] = True

    # 规则2：抉择模式无具体行动 → 结论可执行性 ≤ 2
    if check_no_concrete_action(trace):
        rule_flags.append("no_concrete_action")
        rc = llm_scores.get("conclusion_actionability", {})
        if rc.get("score", 5) > 2:
            rc["score"] = 2
            rc["reason"] = "[规则覆盖] 抉择模式书记官结论中未检测到具体行动建议。"
            rc["rule_override"] = True
            llm_scores["conclusion_actionability"] = rc

    return {
        "scores": llm_scores,
        "overall_assessment": overall,
        "rule_flags": rule_flags,
    }


def compute_weighted_score(scores: dict, weights: dict) -> float:
    """计算加权综合分。"""
    total = 0.0
    for dim_id, w in weights.items():
        s = scores.get(dim_id, {})
        score = s.get("score", 0)
        if isinstance(score, (int, float)):
            total += score * w
    return round(total, 2)
