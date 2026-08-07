# 解惑议事厅 · Council Chamber

> 迷茫、纠结、想不通时，请历史上的智者帮你看通看透。

「解惑议事厅」是一个**多智能体角色扮演**系统：15 位古今智者（老子、庄子、孔子、王阳明、苏轼、苏格拉底、马可·奥勒留、尼采、加缪、荣格、纳瓦尔、费曼、毛泽东、易经、塔罗）各有**一份结构化"灵魂档案"**，而非写死的 prompt。围绕同一套人物库，提供三种对话模式，每次解惑沉淀成一篇笔记写进 Obsidian。

- 🗣️ **独对**：深挖一位智者的视角，多轮追问，用他的思维方式拆你的问题
- 🛋️ **圆桌**：多位智者围坐共议、彼此交锋——"价值在分歧，不在和谐"
- ⚖️ **抉择**：各方给立场，书记官综合成可落地的决断（共识 / 取舍 / 下一步 / 留给你静坐想的问题）

## 界面预览

![首页展厅](docs/screenshot.png)

> 首页是横向"展厅"：每位智者一件展品（ASCII 水墨像），点「请教」进入对话。可安装为 PWA 独立窗口。
> （截图请自行截取首页后放到 `docs/screenshot.png`，分辨率建议 1440×950。）

## 快速开始（Web）

要求：**Python 3.10+** 和 **DeepSeek API Key**（OpenAI 兼容）。

```bash
cd web
./run.sh          # 首次自动建虚拟环境并装依赖，之后每次直接启动
# 浏览器打开 http://127.0.0.1:8787
```

**配置 API Key**：复制 `web/.env.example` 为 `web/.env` 并填入：

```bash
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

不填也能启动——服务会尝试从环境变量读取；`/api/health` 返回 `llm_configured: false` 时表示 key 缺失。

**停止**：终端里 `Ctrl+C`；或 `pkill -f uvicorn`。

> Windows + WSL 用户：仓库里附有 `启动解惑议事厅.bat` / `停止解惑议事厅.bat`，双击即用（记得改脚本里的项目路径）。

## 三种对话模式

| 模式 | 场景 | 机制 |
|---|---|---|
| **独对 solo** | 深挖一个人的视角 | 单人物多轮追问；先用他的 `method` 重构你的困惑（常常困惑本身就被问错了） |
| **圆桌 roundtable** | 看不同视角碰撞 | 全员立论 → **辩论导演**编排交锋（让真正对立者点名互驳）→ 书记官小结，点出分歧的根 |
| **抉择 council** | 想要可落地的决断 | 各方极简表态 → 书记官按固定结构收敛 |

圆桌/抉择都支持追问轮；选人时系统会**故意掺入一位唱反调的**，保证有真实交锋。

## 阵容（15 位）

| 类别 | 智者 |
|---|---|
| 东方大儒/哲思 | 老子、庄子、孔子、王阳明、苏轼 |
| 西方哲学家 | 苏格拉底、马可·奥勒留、尼采、加缪 |
| 现代思想者 | 荣格、纳瓦尔、费曼 |
| 领导者 | 毛泽东 |
| 术数玄学 | 易经、塔罗 |

**核心设计原则：人物 = 数据，不是代码。** 每位智者是一份 `personas/<id>.md` 灵魂档案（世界观 / 核心思想 / **method 怎么想问题** / voice 怎么说话 / pushback_on 反对什么 / blindspots 局限），加新人物只需复制 `personas/_TEMPLATE.md` 填好，**无需改任何代码**。

## 每次解惑，沉淀进 Obsidian

任意模式结束后可一键导出：系统让"书记官"把整场对话**蒸馏成一篇洞见笔记**（提炼可复用的判断，而非复述对话），写入 `<vault>/解惑议事厅/YYYY-MM-DD-<摘要>.md`，格式见 `references/note-template.md`。

导出目录可在 `config.yaml` 配置（或设 `JIEHUO_OUTPUT_DIR` 环境变量）。

## 多智能体评测框架（multiagent-eval）

仓库内还包含一套**评测与能力分析框架**（`multiagent-eval/`），形成「任务设计 → 数据构造 → 自动化评测 → Badcase 挖掘 → 回流优化」闭环：

- 10 个决策评测场景（个人抉择 / 多方辩论 / 复杂 trade-off）
- 5 维评分标准：角色一致性、Pushback 力度、结论可执行性、长程一致性、方法运用度
- LLM-as-Judge + 规则检查的自动打分，Trace 全量采集
- 对比 **GLM-5.2 vs DeepSeek-V4-Pro** 两种后端（运行时切换，零侵入）
- Badcase 分类挖掘 + 失败样本**回流到角色档案**并验证改善

详见 [multiagent-eval/README.md](multiagent-eval/README.md)。评测曾发现并修复一个有趣 bug：角色 ID 命名不一致导致马可·奥勒留被静默过滤。

## 目录结构

```
解惑议事厅/
├── personas/            # L0 人物库 · 15 位灵魂档案 + _TEMPLATE.md
├── references/          # L1 编排规则 + Obsidian 笔记格式
├── skill/               # Claude Code Skill（可安装到 ~/.claude/skills/council/）
├── web/                 # L2 Web 主力交付（FastAPI + 原生前端）
│   ├── app.py           #   FastAPI：/api/chat(SSE) /api/suggest /api/export /api/sessions
│   ├── orchestrator.py  #   编排引擎：三种模式 + 辩论导演 + 蒸馏
│   ├── llm.py           #   OpenAI 兼容后端（DeepSeek）
│   ├── personas.py      #   解析 personas/*.md → 结构化人物
│   ├── store.py         #   SQLite 会话 + 导出 Obsidian
│   └── static/          #   水墨×ASCII 前端（SSE 流式渲染）
├── multiagent-eval/     # 评测框架（独立子模块，直接 import web 代码）
└── config.yaml          # vault 路径、模型、端口等
```

## 架构（四层）

```
L3 沉淀层   困惑/对话/洞见 → SQLite 会话 + Obsidian 笔记
L2 交付层   Claude Code Skill ｜ Web（FastAPI + SSE）
L1 编排层   三种对话模式 + 辩论导演 + 书记官（核心引擎）
L0 人物库   每人一份灵魂档案（世界观/方法/语气/源典/局限）
```

详细设计见 [DESIGN.md](DESIGN.md)。

## 技术栈

**后端**：Python · FastAPI · SSE 流式 · SQLite · OpenAI 兼容 API（默认 DeepSeek，可换任意 OpenAI 兼容服务）
**前端**：原生 HTML/CSS/JS（零构建），水墨 × 古典 × ASCII 视觉
**编排**：单 LLM 多次调用 + 脚本化状态编排（每位智者一次独立调用，transcript 作为上下文传递）

## 许可证

MIT License（见 [LICENSE](LICENSE)）。

**图片来源**：智者头像（`web/static/img/av/*.jpg`）来自 [Wikimedia Commons](https://commons.wikimedia.org)，多为公有领域（public domain）或 CC 许可，仅作个人项目展示；如需商用请自行核对各图许可。`web/fetch_assets.py` 记录了下载与处理管线。

## 隐私说明

- API Key 一律走 `.env`（已被 `.gitignore` 忽略），**不会进入版本库**；
- 本地会话数据存 `web/council.db`（不入库）；导出笔记写入你的 Obsidian vault，仅存本地。
