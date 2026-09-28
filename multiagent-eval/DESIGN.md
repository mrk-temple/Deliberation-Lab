# 多智能体决策评测框架 · 设计决策文档

> 本文档记录所有重要设计决策及其理由，供后续迭代参考。

## 一、项目目标

基于 Deliberation-Lab 多智能体决策系统，构建一套轻量但完整的评测与能力分析框架，
形成「任务设计 → 数据构造 → 自动化评测 → Badcase 挖掘 → 回流优化」的闭环。
最终目的是服务 Deliberation-Lab 系统的优化，而非独立存在。

## 二、系统理解

### Deliberation-Lab 四层架构

```
L3 沉淀层  困惑/对话/洞见 → Obsidian 笔记 / DB
L2 交付层  Skill (Claude Code) | Web (FastAPI+SSE)
L1 编排层  三种对话模式 + 主持人逻辑（核心引擎）
L0 人物库  每人一份灵魂档案 personas/*.md（世界观/方法/语气/源典/局限）
```

### 三种对话模式

| 模式 | 场景 | 机制 |
|------|------|------|
| 独对 solo | 深挖一个人的视角 | 单人物，多轮追问 |
| 圆桌 roundtable | 看不同视角碰撞 | 多人立论 → 辩论导演编排交锋 → 书记官小结 |
| 抉择 council | 想要可落地的决断 | 各方表态 → 书记官综合（共识/取舍/下一步/静坐问题） |

### 可复用接口（评测框架直接 import，不走 HTTP）

- `personas.load_all()` / `personas.get(pid)` — 加载人物档案
- `orchestrator.solo(persona_id, messages, divination, model)` — 独对模式
- `orchestrator.roundtable(persona_ids, messages, council, divination, model, target_id)` — 圆桌/抉择
- `orchestrator._persona_system(p, extra)` — 系统提示构建
- `orchestrator._context_block(question, prior, transcript, instruction)` — 上下文构建
- `llm.stream(messages, temperature, model)` / `llm.complete(messages, temperature, model)` — LLM 调用

### 事件协议

```
{"type":"speaker", "id","name","school"}  → 发言者开始
{"type":"delta",   "text"}                → 正文增量
{"type":"end",     "_full": "完整文本"}    → 发言者结束（_full 不外发，评测框架用于采集）
{"type":"done"}                            → 整轮结束
```

## 三、关键设计决策

### 决策1：对比 GLM vs DeepSeek（而非 Claude）

**选择**：GLM-5.2 vs DeepSeek-V4-Pro

**理由**：
- 两者都是 OpenAI 兼容 API，切换干净，只需换 base_url / api_key / model
- 符合规范成功标准（七）的明确要求："至少完成 GLM vs DeepSeek 的对比"
- Claude 走 claude_cli（本机 Claude Code 订阅），冷启动慢（每次加载 7-8k cache token），
  圆桌多发言较慢、吃 5 小时额度，不适合批量自动化评测
- GLM 和 DeepSeek 都可按 token 付费，无额度时间限制，适合批量跑

### 决策2：5 个评测维度（在规范要求的 4 个基础上增加"方法运用度"）

**选择**：角色一致性 + Pushback 力度 + 结论可执行性 + 长程一致性 + 方法运用度

**理由**：
- 规范要求至少 4 个（前四个），我们增加第 5 个"方法运用度"
- Deliberation-Lab 的核心设计哲学是"人物 = 数据，不是代码"，其中 `method`（怎么想问题）
  是灵魂档案中最重要的字段——它逼人物用自己的思维方式真正拆解用户困惑，而非甩金句
- 如果一个"费曼"只会说"第一原则是你绝不能欺骗自己"而不真正用第一性原理拆解问题，
  那角色一致性可能不低，但实际上没有发挥系统设计的核心价值
- 因此 method 运用值得独立评测，与角色一致性区分开

### 决策3：10 个场景的设计原则——刻意制造天然角色张力

**选择**：场景设计遵循"天然张力优先"原则，刻意安排立场对立的角色组合。

**6 组核心张力组合**（来自用户反馈，已用于场景设计）：

| 组合 | 张力 | 用于场景 |
|------|------|----------|
| 毛泽东 × 老子 | 行动斗争 vs 无为不争 | — |
| 尼采 × 马可奥勒留 | 酒神超人 vs 斯多葛克制 | 场景10 |
| 费曼 × 易经/庄子 | 实证可验证 vs 玄学象数 | 场景5, 8 |
| 苏格拉底 × 毛泽东 | 质疑一切 vs 实践导向 | 场景4, 8 |
| 纳瓦尔 × 孔子 | 个人杠杆 vs 群体伦理 | 场景10 |
| 荣格 × 王阳明 | 无意识个体化 vs 致良知 | 场景9 |

**场景分布**：
- 个人抉择（solo）：3 个 — 测方法运用与长程一致性
- 多方辩论（roundtable）：3 个 — 测 pushback 与角色一致性
- 复杂 trade-off（council）：4 个 — 测结论可执行性

**被否决的场景方向**（及理由）：
- 存在意义危机（太虚，结论难落地，可执行性差）
- 亲情与自我（容易变成情感安慰，冲突不够锋利）
- 创造与生存（与职业转型、价值观碰撞重叠）
- 归乡与漂泊（情绪向，区分度一般）

### 决策4：评测框架直接 import 现有 orchestrator 和 personas 模块

**选择**：不走 HTTP API，直接 import orchestrator / personas / llm 模块。

**理由**：
- 更可靠——不需要启动 web 服务器，不受网络/端口/代理影响
- 直接拿到 trace 数据——orchestrator 的 `{"type":"end","_full":...}` 事件包含完整发言文本，
  HTTP SSE 时会被 strip 掉（`ev.pop("_full")`），但直接调用可以拿到
- 避免重复造轮子——复用编排逻辑、系统提示构建、人物加载
- 评测框架的 src/ 代码将 web/ 加入 sys.path，import 现有模块

### 决策5：后端切换方案——上下文管理器运行时切换

**选择**：用上下文管理器在运行时切换 `llm` 模块的 `_client`、`_S`、`_PROVIDER`，
不改动现有代码。

**理由**：
- `llm.py` 在 import 时就锁定了 provider（`_PROVIDER = _S["provider"]`），无法运行时切换
- 改动现有代码会影响 web 端运行，违反"服务主系统"原则
- 上下文管理器方案：评测前 patch `llm._client` / `llm._S["model"]` / `llm._PROVIDER`，
  评测后 restore，对现有代码零侵入
- GLM 和 DeepSeek 都走 OpenAI 兼容接口，只需切 `_client`（AsyncOpenAI 实例）和 model 名

## 四、评测流水线设计

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│ 加载场景     │ ──→ │ 调用          │ ──→ │ 采集 Trace  │ ──→ │ Judge    │
│ scenarios.  │     │ orchestrator  │     │ 每位发言者  │     │ 打分     │
│ yaml        │     │ (切换后端)    │     │ 完整文本+元 │     │ LLM+规则 │
└─────────────┘     └──────────────┘     │ 信息        │     └──────────┘
                                         └─────────────┘          │
                                                                   ▼
                    ┌──────────────┐     ┌─────────────┐     ┌──────────┐
                    │ Badcase 分析  │ ←── │ 结果存储     │ ←── │ 结构化   │
                    │ 筛选+分类     │     │ results/    │     │ 评分结果 │
                    └──────────────┘     └─────────────┘     └──────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ 回流优化      │
                    │ 更新角色档案  │
                    └──────────────┘
```

### 多轮场景处理

- solo 场景的 turns 按顺序逐轮调用 `orchestrator.solo()`
- 每轮把上一轮的 assistant 回复加入 messages，形成多轮对话
- 长程一致性维度跨轮评估
- roundtable / council 场景通常只有 1 个 turn（orchestrator 内部处理多发言者）

## 五、Trace 采集设计

每条 Trace 记录：

```json
{
  "scenario_id": "career_pivot",
  "backend": "glm",
  "model": "glm-5.2",
  "mode": "solo",
  "turn_index": 0,
  "timestamp": "2026-07-25T14:30:00",
  "speakers": [
    {
      "id": "feynman",
      "name": "费曼",
      "school": "物理学 / 科学思维",
      "text": "完整发言文本",
      "token_count": 350
    }
  ],
  "moderator": {  // 圆桌/抉择模式的书记官小结
    "text": "..."
  },
  "user_message": "用户本轮输入",
  "full_transcript": "整轮完整对话文本"
}
```

## 六、Judge 设计

### LLM-as-Judge + 规则检查

**规则检查（硬性，直接定分）**：
- 检测到"作为AI""作为语言模型""As an AI" → 角色一致性 = 1
- 检测到第三人称自称该人物名（"费曼认为..."）而非第一人称 → 角色一致性 ≤ 2
- 结论中无任何具体行动建议（仅安慰/复述） → 结论可执行性 ≤ 2

**LLM-as-Judge（柔性，按 rubric 打分）**：
- 把场景描述 + 完整 trace + persona 档案 + 维度 rubric 喂给 Judge 模型
- Judge 输出每个维度的 1-5 分 + 打分理由 + 具体问题点
- 为减少偏差，Judge 用固定 temperature（0.3）和结构化 JSON 输出

### Judge prompt 结构

```
系统：你是多智能体决策系统的评测裁判。根据 rubric 给出 1-5 分评分。
用户：
  【场景】{scenario_description}
  【该智者的方法】{persona_method}（用于评方法运用度）
  【完整对话】{trace}
  【评分标准】{dimension_rubric}
  请对每个维度给出 JSON：{"dimension": "...", "score": N, "reason": "...", "issue": "..."}
```

## 七、Badcase 分类体系

根据评分自动筛选低分样本（任一维度 ≤ 2 分），按以下类型分类：

| 类型 | 判定 | 对应维度 |
|------|------|----------|
| 角色崩坏 | 角色一致性 ≤ 2 | role_consistency |
| Pushback 不足 | Pushback 力度 ≤ 2 | pushback_intensity |
| 结论空泛 | 结论可执行性 ≤ 2 | conclusion_actionability |
| 前后矛盾 | 长程一致性 ≤ 2 | long_range_consistency |
| 方法未运用 | 方法运用度 ≤ 2 | method_application |

## 八、回流机制设计

### 回流方式

将典型失败案例转化为角色档案的补充约束：

1. **追加负面示例**：在 persona 的 `## cases` 或新增 `## anti_patterns` 小节中，
   追加"不要这样回应"的负面示例
2. **强化 method 约束**：如果方法运用度低分，在 method 小节追加更具体的步骤要求
3. **调整编排提示**：如果 pushback 不足，在 orchestrator 的 `_EXTRA_*` 提示中
   强化"必须质疑"的指令

### 回流验证

- 回流后在原失败场景上重跑评测
- 对比回流前后得分
- 记录在 reports/feedback_validation.md 中

## 九、可复现性保障

- 固定 temperature（评测用 0.85，Judge 用 0.3）
- 记录模型版本、时间戳、场景 ID
- 结果按 `{scenario_id}_{backend}_{timestamp}.json` 命名
- 随机种子固定（涉及随机选择时）
