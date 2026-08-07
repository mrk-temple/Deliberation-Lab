# 多智能体决策评测与能力分析框架

> 基于「解惑议事厅」多智能体决策系统，设计并实现一套轻量但完整的评测与能力分析框架。
> 形成「任务设计 → 数据构造 → 自动化评测 → Badcase 挖掘 → 回流优化」的闭环。

## 项目简介

解惑议事厅是一个"迷茫时请古今中外智者解惑"的多智能体系统，15 位智者（老子、庄子、
孔子、苏格拉底、费曼、毛泽东等）各有结构化"灵魂档案"，支持独对 / 圆桌 / 抉择三种
对话模式。

本框架对解惑议事厅进行系统性评测：
- 设计 10 个高质量决策评测场景（个人抉择、多方辩论、复杂 trade-off）
- 定义 5 个核心评测维度（角色一致性、Pushback 力度、结论可执行性、长程一致性、方法运用度）
- 实现自动化 Judge 与 Trace 采集 Pipeline
- 对比 GLM-5.2 与 DeepSeek-V4-Pro 在多 Agent 协作任务上的表现
- 进行 Badcase 挖掘与能力瓶颈定位
- 将失败样本回流到角色档案与编排逻辑

## 目录结构

```
multiagent-eval/
├── README.md                 # 本文件
├── DESIGN.md                 # 设计决策文档
├── requirements.txt          # Python 依赖
├── config/
│   ├── scenarios.yaml        # 10 个评测场景定义
│   ├── dimensions.yaml       # 5 个评测维度与 rubric
│   └── models.yaml           # GLM / DeepSeek 后端配置
├── src/
│   ├── __init__.py
│   ├── pipeline.py           # 主评测流水线（阶段2）
│   ├── judge.py              # 自动化 Judge（阶段2）
│   ├── trace.py              # Trace 采集与解析（阶段2）
│   ├── reporter.py           # 报告生成（阶段3）
│   └── feedback.py           # 失败样本回流（阶段4）
├── scripts/
│   ├── __init__.py
│   ├── run_eval.py           # 一键跑评测（阶段2）
│   └── analyze_badcases.py   # Badcase 分析（阶段3）
├── results/                  # 评测结果输出（自动生成）
└── reports/                  # 分析报告（自动生成）
```

## 快速开始

### 1. 安装依赖

```bash
cd multiagent-eval
pip install -r requirements.txt
```

### 2. 配置 API Key

需要以下环境变量（建议放在项目根 `multiagent-eval/.env`，脚本会自动加载；也可导出到 shell）：

```bash
export GLM_API_KEY="your-glm-key"
export GLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export DEEPSEEK_API_KEY="your-deepseek-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

### 3. 运行评测（阶段2 完成后）

```bash
python scripts/run_eval.py                    # 跑全部场景 × 全部后端
python scripts/run_eval.py --scenario career_pivot   # 只跑指定场景
python scripts/run_eval.py --backend glm      # 只跑指定后端
```

### 4. 生成报告（阶段3 完成后）

```bash
python scripts/analyze_badcases.py            # 分析 Badcase 并生成报告
```

## 评测流程

```
场景加载 → 切换后端 → 调用 orchestrator → 采集 Trace → Judge 打分 → 存储结果
                                                                    ↓
                                                            Badcase 筛选与分类
                                                                    ↓
                                                            回流到角色档案
                                                                    ↓
                                                            重跑验证改善
```

### 评测维度（1-5 分）

| 维度 | 说明 |
|------|------|
| 角色一致性 | 语气/人称/思维方式是否符合人设 |
| Pushback 力度 | 是否有效质疑用户自欺，圆桌是否有真实分歧 |
| 结论可执行性 | 最终建议是否具体可落地 |
| 长程一致性 | 多轮后是否前后自洽 |
| 方法运用度 | 是否真正用 persona 的 method 拆解问题 |

## 后端对比

| 后端 | 模型 | 接口 |
|------|------|------|
| GLM | glm-5.2 | 智谱开放平台 OpenAI 兼容 |
| DeepSeek | deepseek-v4-pro | DeepSeek API OpenAI 兼容 |

两者都走 OpenAI 兼容接口，通过上下文管理器在运行时切换，不改动解惑议事厅现有代码。

## 结果说明

- `results/` — 每次评测的结构化 JSON 结果（含 trace + 评分）
- `reports/` — Markdown 分析报告（含整体对比、各维度表现、典型 Badcase、改进建议）
- 回流后的角色档案更新记录在 `reports/feedback_validation.md`

## 设计文档

详细设计决策见 [DESIGN.md](./DESIGN.md)。

## 与解惑议事厅的关系

本框架直接 import 解惑议事厅的 `orchestrator`、`personas`、`llm` 模块，
复用其编排逻辑和人物库，不重复造轮子。评测的最终目的是服务解惑议事厅的优化。
