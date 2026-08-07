"""失败样本回流：将典型 badcase 转化为角色档案的补充约束。

回流方式：
1. 追加负面示例：在 persona 的 ## cases 小节追加"不要这样回应"的示例
2. 强化 method 约束：在 method 小节追加更具体的步骤要求
3. 调整编排提示：在 orchestrator 的 _EXTRA_* 提示中强化指令

回流后可在原失败场景上重跑评测，对比改善效果。
"""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_ROOT.parent
RESULTS_DIR = EVAL_ROOT / "results"
REPORTS_DIR = EVAL_ROOT / "reports"
PERSONAS_DIR = REPO_ROOT / "personas"
ORCHESTRATOR_PATH = REPO_ROOT / "web" / "orchestrator.py"

BADCASE_THRESHOLD = 3


def load_results() -> list[dict]:
    summary = RESULTS_DIR / "summary.json"
    if summary.exists():
        with open(summary, encoding="utf-8") as f:
            return json.load(f)
    return []


def load_result_detail(result_file: str) -> dict:
    path = RESULTS_DIR / result_file
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 1. 追加负面示例到角色档案 ──────────────────────────────────

def _append_anti_patterns(persona_path: Path, badcase_info: dict) -> bool:
    """在角色档案中追加 ## anti_patterns 小节（负面示例）。

    如果已有 ## anti_patterns，追加；否则新建。
    返回是否修改了文件。
    """
    text = persona_path.read_text(encoding="utf-8")
    original = text

    persona_name = badcase_info.get("persona_name", "该智者")
    issue_desc = badcase_info.get("issue", "")
    bad_response = badcase_info.get("bad_response", "")

    anti_pattern_entry = (
        f"\n- **避免**：{issue_desc}\n"
        f"  反面示例（不要这样回应）：\"{bad_response[:150]}...\""
    )

    # 检查是否已有 ## anti_patterns 小节
    anti_pattern_re = re.compile(r"(## anti_patterns[^\n]*\n)", re.MULTILINE)
    if anti_pattern_re.search(text):
        # 已有小节，在内容末尾追加
        # 找到下一个 ## 或文件末尾
        match = anti_pattern_re.search(text)
        insert_pos = match.end()
        # 找到下一个 ## 标题
        next_section = re.search(r"\n## ", text[insert_pos:])
        if next_section:
            end_pos = insert_pos + next_section.start()
        else:
            end_pos = len(text)
        text = text[:end_pos].rstrip() + anti_pattern_entry + "\n" + text[end_pos:]
    else:
        # 没有小节，在文件末尾追加
        # 找到 ## blindspots 之后追加
        blindspot_re = re.compile(r"(## blindspots[^\n]*\n.*?)(?=\n## |\Z)", re.DOTALL)
        if blindspot_re.search(text):
            text = blindspot_re.sub(
                r"\1\n\n## anti_patterns（反面示例 —— 从评测 badcase 回流）\n"
                f"{anti_pattern_entry.strip()}",
                text, count=1,
            )
        else:
            text = text.rstrip() + "\n\n## anti_patterns（反面示例 —— 从评测 badcase 回流）\n" + anti_pattern_entry.strip() + "\n"

    if text != original:
        # 先备份
        backup = persona_path.with_suffix(".md.bak")
        if not backup.exists():
            shutil.copy2(persona_path, backup)
        persona_path.write_text(text, encoding="utf-8")
        return True
    return False


# ── 2. 回流到角色档案 ──────────────────────────────────────────

def feedback_to_personas(results: list[dict], dry_run: bool = False) -> list[dict]:
    """将 badcase 回流到角色档案。

    对每个 badcase：
    - 找到相关 persona
    - 在其档案中追加负面示例
    返回回流操作日志。
    """
    log: list[dict] = []

    for r in results:
        if "error" in r:
            continue
        scores = r.get("scores", {})
        failed_dims = [
            d for d, s in scores.items()
            if isinstance(s.get("score"), (int, float)) and s["score"] <= BADCASE_THRESHOLD
        ]
        if not failed_dims:
            continue

        # 加载完整 trace
        detail = load_result_detail(r.get("result_file", ""))
        if not detail:
            continue

        trace = detail.get("trace", {})
        turns = trace.get("turns", [])

        # 对每个失败维度，找到相关发言并回流
        for dim_id in failed_dims:
            dim_score = scores.get(dim_id, {})
            issue = dim_score.get("issue", dim_score.get("reason", ""))

            # 找到该维度最相关的发言者
            # 角色一致性/方法运用度 → 找第一个发言者
            # pushback → 找所有发言者
            # 结论可执行性 → 找书记官
            target_speaker_id = None
            if dim_id == "conclusion_actionability":
                # 找书记官
                for turn in turns:
                    mod = turn.get("moderator")
                    if mod:
                        target_speaker_id = mod.get("id")
                        bad_response = mod.get("text", "")[:200]
                        break
                else:
                    continue
            else:
                # 找第一个发言者
                for turn in turns:
                    speakers = turn.get("speakers", [])
                    if speakers:
                        target_speaker_id = speakers[0].get("id")
                        bad_response = speakers[0].get("text", "")[:200]
                        break
                else:
                    continue

            if not target_speaker_id:
                continue

            persona_path = PERSONAS_DIR / f"{target_speaker_id}.md"
            if not persona_path.exists():
                continue

            badcase_info = {
                "persona_name": target_speaker_id,
                "issue": f"[{r.get('scenario_title','')}] {dim_id}: {issue}",
                "bad_response": bad_response,
            }

            if dry_run:
                log.append({
                    "action": "dry_run",
                    "persona": target_speaker_id,
                    "scenario": r.get("scenario_id"),
                    "dimension": dim_id,
                    "issue": issue[:100],
                })
            else:
                modified = _append_anti_patterns(persona_path, badcase_info)
                log.append({
                    "action": "modified" if modified else "no_change",
                    "persona": target_speaker_id,
                    "persona_path": str(persona_path),
                    "scenario": r.get("scenario_id"),
                    "dimension": dim_id,
                    "issue": issue[:100],
                })

    return log


# ── 3. 回流到编排提示 ──────────────────────────────────────────

FEEDBACK_PROMPTS = {
    "pushback_intensity": (
        "\n（评测反馈：pushback 力度不足。必须更犀利地质疑用户的自欺和回避，"
        "不要附和，不要安慰，直接点破核心矛盾。）"
    ),
    "conclusion_actionability": (
        "\n（评测反馈：结论过于空泛。下一步必须具体到今天或本周可做的一件事，"
        "不要给'加油''想开点'式空话。）"
    ),
    "method_application": (
        "\n（评测反馈：method 运用不深入。必须严格按以下步骤逐步拆解，"
        "每步都落到用户的具体处境，不要甩金句。）"
    ),
    "role_consistency": (
        "\n（评测反馈：角色一致性不足。绝不说'作为AI'，严格保持第一人称，"
        "用你的语气和思维方式说话。）"
    ),
}


def feedback_to_orchestrator(results: list[dict], dry_run: bool = False) -> list[dict]:
    """根据 badcase 统计，在 orchestrator.py 的提示中追加反馈约束。

    只在某个维度的 badcase 数 ≥ 2 时才修改（避免单次偶发）。
    """
    log: list[dict] = []

    # 统计每个维度的 badcase 数
    dim_badcase_count: dict[str, int] = defaultdict(int)
    for r in results:
        if "error" in r:
            continue
        scores = r.get("scores", {})
        for dim_id, s in scores.items():
            v = s.get("score")
            if isinstance(v, (int, float)) and v <= BADCASE_THRESHOLD:
                dim_badcase_count[dim_id] += 1

    for dim_id, count in dim_badcase_count.items():
        if count < 2:
            continue
        feedback = FEEDBACK_PROMPTS.get(dim_id)
        if not feedback:
            continue

        if dry_run:
            log.append({
                "action": "dry_run",
                "dimension": dim_id,
                "badcase_count": count,
                "feedback": feedback.strip(),
            })
        else:
            # 在 orchestrator.py 中追加反馈
            # 简单方案：在文件末尾追加一个 _FEEDBACK_OVERRIDES 字典
            text = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
            marker = "# ── 评测回流约束 ──"
            if marker not in text:
                addition = (
                    f"\n\n{marker}\n"
                    f"_FEEDBACK_{dim_id.upper()} = {repr(feedback.strip())}\n"
                    f"# 在 _EXTRA_* 提示中引用此变量以应用反馈\n"
                )
                ORCHESTRATOR_PATH.write_text(text + addition, encoding="utf-8")
                log.append({
                    "action": "modified",
                    "dimension": dim_id,
                    "badcase_count": count,
                    "file": str(ORCHESTRATOR_PATH),
                })
            else:
                log.append({
                    "action": "already_modified",
                    "dimension": dim_id,
                    "badcase_count": count,
                })

    return log


# ── 4. 回流验证 ────────────────────────────────────────────────

def generate_validation_plan(results: list[dict]) -> list[dict]:
    """生成回流验证计划：列出需要在回流后重跑的场景和后端。"""
    plan: list[dict] = []
    for r in results:
        if "error" in r:
            continue
        scores = r.get("scores", {})
        failed = any(
            isinstance(s.get("score"), (int, float)) and s["score"] <= BADCASE_THRESHOLD
            for s in scores.values()
        )
        if failed:
            plan.append({
                "scenario_id": r["scenario_id"],
                "scenario_title": r.get("scenario_title", ""),
                "backend": r.get("backend", ""),
                "result_file": r.get("result_file", ""),
                "before_weighted_score": r.get("weighted_score", 0),
            })
    return plan


def save_feedback_report(
    persona_log: list[dict],
    orchestrator_log: list[dict],
    validation_plan: list[dict],
) -> Path:
    """保存回流报告到 reports/。"""
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / "feedback_validation.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 失败样本回流报告",
        "",
        f"> 生成时间：{ts}",
        "",
        "## 一、角色档案回流",
        "",
    ]

    if not persona_log:
        lines.append("无角色档案需要回流（没有发现 badcase 或为 dry-run）。")
    else:
        lines.append(f"共 {len(persona_log)} 条回流操作：")
        lines.append("")
        for entry in persona_log:
            status = "✓" if entry["action"] == "modified" else ("○" if entry["action"] == "dry_run" else "→")
            lines.append(
                f"- {status} **{entry['persona']}** | 场景: {entry.get('scenario','')} | "
                f"维度: {entry.get('dimension','')} | {entry['action']}"
            )
            if entry.get("issue"):
                lines.append(f"  - 问题: {entry['issue']}")

    lines += [
        "",
        "## 二、编排提示回流",
        "",
    ]
    if not orchestrator_log:
        lines.append("无编排提示需要回流。")
    else:
        lines.append(f"共 {len(orchestrator_log)} 条回流操作：")
        lines.append("")
        for entry in orchestrator_log:
            lines.append(
                f"- **{entry['dimension']}** ({entry['badcase_count']} 个 badcase) → {entry['action']}"
            )

    lines += [
        "",
        "## 三、回流验证计划",
        "",
    ]
    if not validation_plan:
        lines.append("无需验证的场景。")
    else:
        lines.append(f"以下 {len(validation_plan)} 个场景需在回流后重跑验证：")
        lines.append("")
        lines.append("| 场景 | 后端 | 回流前综合分 |")
        lines.append("|------|------|------------|")
        for v in validation_plan:
            lines.append(
                f"| {v['scenario_title']} | {v['backend']} | {v['before_weighted_score']:.1f} |"
            )
        lines.append("")
        lines.append("### 验证方法")
        lines.append("")
        lines.append("```bash")
        for v in validation_plan:
            lines.append(
                f"# 重跑 {v['scenario_title']} ({v['backend']})"
            )
            lines.append(
                f"python scripts/run_eval.py --scenario {v['scenario_id']} --backend {v['backend']}"
            )
        lines.append("```")
        lines.append("")
        lines.append("重跑后对比 `before_weighted_score` 与新的 `weighted_score`，验证回流效果。")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
