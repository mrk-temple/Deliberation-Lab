"""报告生成：从评测结果生成 Markdown 分析报告。

包含：
- 整体得分对比（不同模型）
- 各维度表现
- 典型 Badcase 分析
- 能力瓶颈总结
- 改进建议
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = EVAL_ROOT / "results"
REPORTS_DIR = EVAL_ROOT / "reports"

# Badcase 分类阈值：任一维度 ≤ 此分数即为 badcase
BADCASE_THRESHOLD = 3

# Badcase 类型映射
DIMENSION_LABELS = {
    "role_consistency": "角色一致性",
    "pushback_intensity": "Pushback力度",
    "conclusion_actionability": "结论可执行性",
    "long_range_consistency": "长程一致性",
    "method_application": "方法运用度",
}


def load_all_results() -> list[dict]:
    """从 summary.json 加载所有结果。"""
    summary_path = RESULTS_DIR / "summary.json"
    if not summary_path.exists():
        # 尝试从单个结果文件加载
        results = []
        for f in sorted(RESULTS_DIR.glob("*.json")):
            if f.name == "summary.json":
                continue
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
                results.append({
                    "scenario_id": data["scenario_id"],
                    "scenario_title": data.get("scenario_title", ""),
                    "backend": data["backend"],
                    "model": data.get("model", ""),
                    "mode": data.get("mode", ""),
                    "weighted_score": data.get("weighted_score", 0),
                    "scores": data.get("scores", {}),
                    "rule_flags": data.get("rule_flags", []),
                    "result_file": f.name,
                })
        return results
    with open(summary_path, encoding="utf-8") as f:
        return json.load(f)


def load_result_detail(result_file: str) -> dict:
    """加载单个结果文件的完整内容（含 trace）。"""
    path = RESULTS_DIR / result_file
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_badcases(results: list[dict]) -> list[dict]:
    """筛选低分样本（badcase）。"""
    badcases = []
    for r in results:
        if "error" in r:
            badcases.append({**r, "badcase_type": "运行错误", "failed_dims": []})
            continue
        scores = r.get("scores", {})
        failed_dims = []
        for dim_id, s in scores.items():
            score = s.get("score", 0)
            if isinstance(score, (int, float)) and score <= BADCASE_THRESHOLD:
                failed_dims.append(dim_id)
        if failed_dims:
            badcases.append({
                **r,
                "badcase_type": _classify_badcase(failed_dims),
                "failed_dims": failed_dims,
            })
    return badcases


def _classify_badcase(failed_dims: list[str]) -> str:
    """根据失败维度分类 badcase。"""
    type_map = {
        "role_consistency": "角色崩坏",
        "pushback_intensity": "Pushback不足",
        "conclusion_actionability": "结论空泛",
        "long_range_consistency": "前后矛盾",
        "method_application": "方法未运用",
    }
    types = [type_map.get(d, d) for d in failed_dims]
    return " / ".join(types)


def generate_report(results: list[dict]) -> Path:
    """生成完整的 Markdown 分析报告。"""
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_path = REPORTS_DIR / f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    badcases = extract_badcases(results)

    lines: list[str] = []
    lines.append(f"# 多智能体决策评测报告")
    lines.append(f"")
    lines.append(f"> 生成时间：{ts}")
    lines.append(f"> 评测场景数：{len(set(r['scenario_id'] for r in results))}")
    lines.append(f"> 对比后端：{', '.join(sorted(set(r.get('backend','') for r in results)))}")
    lines.append(f"")

    # ── 一、整体得分对比 ──
    lines.append("## 一、整体得分对比")
    lines.append("")

    backend_stats = _compute_backend_stats(results)
    lines.append("| 后端 | 场景数 | 平均综合分 | 角色一致性 | Pushback | 结论可执行性 | 长程一致性 | 方法运用度 |")
    lines.append("|------|--------|-----------|-----------|----------|------------|-----------|-----------|")
    for bname, stats in sorted(backend_stats.items()):
        lines.append(
            f"| {bname} | {stats['count']} | {stats['avg_weighted']:.2f} | "
            f"{stats['avg_dim']['role_consistency']:.1f} | "
            f"{stats['avg_dim']['pushback_intensity']:.1f} | "
            f"{stats['avg_dim']['conclusion_actionability']:.1f} | "
            f"{stats['avg_dim']['long_range_consistency']:.1f} | "
            f"{stats['avg_dim']['method_application']:.1f} |"
        )
    lines.append("")

    # ── 二、各场景详细得分 ──
    lines.append("## 二、各场景详细得分")
    lines.append("")
    lines.append("| 场景 | 模式 | 后端 | 综合分 | 角色一致 | Pushback | 结论 | 长程 | 方法 |")
    lines.append("|------|------|------|--------|---------|----------|------|------|------|")
    for r in sorted(results, key=lambda x: (x["scenario_id"], x.get("backend", ""))):
        if "error" in r:
            lines.append(f"| {r['scenario_title']} | {r.get('mode','')} | {r.get('backend','')} | ERROR | - | - | - | - | - |")
            continue
        s = r.get("scores", {})
        def _sc(dim):
            v = s.get(dim, {}).get("score", "-")
            return f"{v}" if v != "-" else "-"
        lines.append(
            f"| {r['scenario_title']} | {r.get('mode','')} | {r.get('backend','')} | "
            f"{r.get('weighted_score', 0):.1f} | "
            f"{_sc('role_consistency')} | {_sc('pushback_intensity')} | "
            f"{_sc('conclusion_actionability')} | {_sc('long_range_consistency')} | "
            f"{_sc('method_application')} |"
        )
    lines.append("")

    # ── 三、各维度分析 ──
    lines.append("## 三、各维度分析")
    lines.append("")
    for dim_id, dim_label in DIMENSION_LABELS.items():
        lines.append(f"### {dim_label}（{dim_id}）")
        lines.append("")
        for bname in sorted(backend_stats.keys()):
            dim_scores = []
            for r in results:
                if r.get("backend") == bname and "error" not in r:
                    v = r.get("scores", {}).get(dim_id, {}).get("score")
                    if isinstance(v, (int, float)):
                        dim_scores.append(v)
            if dim_scores:
                avg = sum(dim_scores) / len(dim_scores)
                mn = min(dim_scores)
                mx = max(dim_scores)
                lines.append(f"- **{bname}**: 平均 {avg:.1f}，最低 {mn}，最高 {mx}")
        lines.append("")

    # ── 四、Badcase 分析 ──
    lines.append("## 四、Badcase 分析")
    lines.append("")
    if not badcases:
        lines.append("本次评测未发现 Badcase（所有维度评分均 > 3 分）。")
        lines.append("")
        lines.append("> 注：这可能意味着评测场景对当前模型难度偏低，")
        lines.append("> 或 Judge 评分标准偏宽松。后续可增加更难的场景或收紧 rubric。")
    else:
        lines.append(f"共发现 **{len(badcases)}** 个 Badcase（任一维度 ≤ {BADCASE_THRESHOLD} 分）：")
        lines.append("")

        # 按类型统计
        type_counts: dict[str, int] = defaultdict(int)
        for bc in badcases:
            type_counts[bc["badcase_type"]] += 1
        lines.append("### Badcase 类型分布")
        lines.append("")
        lines.append("| 类型 | 数量 |")
        lines.append("|------|------|")
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {t} | {c} |")
        lines.append("")

        # 典型 Badcase 详情
        lines.append("### 典型 Badcase 详情")
        lines.append("")
        for i, bc in enumerate(badcases[:10], 1):  # 最多展示10个
            lines.append(f"#### Badcase #{i}: {bc['scenario_title']} ({bc.get('backend','')})")
            lines.append(f"- **类型**: {bc['badcase_type']}")
            lines.append(f"- **失败维度**: {', '.join(bc.get('failed_dims', []))}")
            if "error" in bc:
                lines.append(f"- **错误**: {bc['error']}")
            else:
                lines.append(f"- **综合分**: {bc.get('weighted_score', 0):.1f}")
                for dim in bc.get("failed_dims", []):
                    s = bc.get("scores", {}).get(dim, {})
                    reason = s.get("reason", "")
                    issue = s.get("issue", "")
                    lines.append(f"- **{DIMENSION_LABELS.get(dim, dim)}** ({s.get('score','?')}分): {reason}")
                    if issue and issue != "无":
                        lines.append(f"  - 问题点: {issue}")
                if bc.get("rule_flags"):
                    lines.append(f"- **规则触发**: {', '.join(bc['rule_flags'])}")
            lines.append("")

    # ── 五、能力瓶颈总结 ──
    lines.append("## 五、能力瓶颈总结")
    lines.append("")
    bottleneck = _identify_bottlenecks(results)
    if bottleneck:
        for b in bottleneck:
            lines.append(f"- {b}")
    else:
        lines.append("当前模型在所有维度上表现均较好，未发现明显瓶颈。")
    lines.append("")

    # ── 六、改进建议 ──
    lines.append("## 六、改进建议")
    lines.append("")
    suggestions = _generate_suggestions(results, badcases)
    for s in suggestions:
        lines.append(f"- {s}")
    lines.append("")

    # ── 七、按场景类型分析 ──
    lines.append("## 七、按场景类型分析")
    lines.append("")
    for category, cat_label in [
        ("personal_choice", "个人抉择 (solo)"),
        ("multi_party_debate", "多方辩论 (roundtable)"),
        ("complex_tradeoff", "复杂 trade-off (council)"),
    ]:
        cat_results = [r for r in results if r.get("mode") == {"personal_choice": "solo", "multi_party_debate": "roundtable", "complex_tradeoff": "council"}.get(category)]
        if not cat_results:
            continue
        lines.append(f"### {cat_label}")
        lines.append("")
        for bname in sorted(backend_stats.keys()):
            cat_backend = [r for r in cat_results if r.get("backend") == bname and "error" not in r]
            if cat_backend:
                avg = sum(r.get("weighted_score", 0) for r in cat_backend) / len(cat_backend)
                lines.append(f"- **{bname}**: 平均综合分 {avg:.2f}（{len(cat_backend)} 个场景）")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _compute_backend_stats(results: list[dict]) -> dict:
    """计算每个后端的统计信息。"""
    stats: dict = {}
    dim_ids = list(DIMENSION_LABELS.keys())

    for r in results:
        if "error" in r:
            continue
        bname = r.get("backend", "unknown")
        if bname not in stats:
            stats[bname] = {
                "count": 0,
                "weighted_sum": 0,
                "dim_sum": {d: 0 for d in dim_ids},
                "dim_count": {d: 0 for d in dim_ids},
            }
        stats[bname]["count"] += 1
        stats[bname]["weighted_sum"] += r.get("weighted_score", 0)
        for d in dim_ids:
            v = r.get("scores", {}).get(d, {}).get("score")
            if isinstance(v, (int, float)):
                stats[bname]["dim_sum"][d] += v
                stats[bname]["dim_count"][d] += 1

    # 计算平均
    for bname, s in stats.items():
        s["avg_weighted"] = s["weighted_sum"] / s["count"] if s["count"] else 0
        s["avg_dim"] = {}
        for d in dim_ids:
            cnt = s["dim_count"][d]
            s["avg_dim"][d] = s["dim_sum"][d] / cnt if cnt else 0

    return stats


def _identify_bottlenecks(results: list[dict]) -> list[str]:
    """识别能力瓶颈（平均分最低的维度）。"""
    bottlenecks: list[str] = []
    dim_scores: dict[str, list[float]] = defaultdict(list)

    for r in results:
        if "error" in r:
            continue
        for dim_id, s in r.get("scores", {}).items():
            v = s.get("score")
            if isinstance(v, (int, float)):
                dim_scores[dim_id].append(v)

    # 找平均分 < 4 的维度
    for dim_id, scores in dim_scores.items():
        avg = sum(scores) / len(scores) if scores else 0
        if avg < 4.0:
            label = DIMENSION_LABELS.get(dim_id, dim_id)
            bottlenecks.append(
                f"**{label}** 平均 {avg:.1f} 分 — 低于 4 分，是主要瓶颈"
            )

    # 按平均分排序
    all_dims = []
    for dim_id, scores in dim_scores.items():
        avg = sum(scores) / len(scores) if scores else 0
        all_dims.append((dim_id, avg))
    all_dims.sort(key=lambda x: x[1])

    if all_dims:
        lowest = all_dims[0]
        label = DIMENSION_LABELS.get(lowest[0], lowest[0])
        bottlenecks.insert(0, f"最弱维度: **{label}**（平均 {lowest[1]:.1f} 分）")

    return bottlenecks


def _generate_suggestions(results: list[dict], badcases: list[dict]) -> list[str]:
    """根据评测结果生成改进建议。"""
    suggestions: list[str] = []

    # 统计各维度的 badcase 数
    dim_badcase_count: dict[str, int] = defaultdict(int)
    for bc in badcases:
        for d in bc.get("failed_dims", []):
            dim_badcase_count[d] += 1

    if dim_badcase_count:
        worst_dim = max(dim_badcase_count, key=dim_badcase_count.get)
        label = DIMENSION_LABELS.get(worst_dim, worst_dim)
        suggestions.append(
            f"优先改进 **{label}**（{dim_badcase_count[worst_dim]} 个 badcase）"
        )

    if dim_badcase_count.get("role_consistency"):
        suggestions.append(
            "角色崩坏问题：检查 persona 档案的 voice/method 是否足够具体，"
            "考虑在系统提示中增加更多负面示例（'不要这样说'）"
        )
    if dim_badcase_count.get("pushback_intensity"):
        suggestions.append(
            "Pushback 不足问题：在 orchestrator 的 _EXTRA_RT_STATE / _EXTRA_COUNCIL "
            "中强化'必须质疑'的指令，或调整辩论导演提示"
        )
    if dim_badcase_count.get("conclusion_actionability"):
        suggestions.append(
            "结论空泛问题：在 _MOD_COUNCIL 中强化'下一步必须具体到今天/本周可做的事'，"
            "增加负面示例"
        )
    if dim_badcase_count.get("method_application"):
        suggestions.append(
            "方法未运用问题：在 _persona_system 中增加'严格按以下步骤拆解'的约束，"
            "把 method 步骤更显式地嵌入提示"
        )

    if not suggestions:
        suggestions.append("当前系统表现良好，可考虑增加更难的评测场景以发现边界。")

    return suggestions
