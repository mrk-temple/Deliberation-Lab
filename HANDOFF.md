# 解惑议事厅 · 交接文档（给新的 Claude Code 会话）

> 新会话第一步：读 `DESIGN.md`、本文件。
> 一句话：这是一个"迷茫时请古今中外智者解惑"的平台，两种交付共用同一套人物库；
> UI 已按「水墨 × 古典 × ASCII」（朱印唯一的彩）重做。
> 注：原 `BUILD-PROMPT.md`/`design-system.md`/`apps/`/`packages/`/`index.html` 是"松烟 Songyan"茶站样板，
> 与本项目无关，已删除；视觉 token（朱印/ASCII/box-drawing/四角色字体）现活在 `web/static/style.css`。

## 是什么 / 两种交付（共用 `personas/`）
- **① Skill**：`skill/SKILL.md`（已装到 `~/.claude/skills/council/`）。三模式：独对/圆桌/抉择。
- **② Web**：`web/`，FastAPI + 原生前端 + SSE 流式 + 导出 Obsidian。**主力**。

## 怎么跑
```bash
# Web（开发）：必须从 web/ 起，相对路径才对
cd 解惑议事厅/web && ./run.sh            # 建 venv 装依赖后 uvicorn :8787
# 打开 http://127.0.0.1:8787
```
- **本机 curl 测 localhost 要加 `--noproxy '*'`**（有代理拦截）。
- 改了 `web/*.py`/`config.yaml` 要**重启 uvicorn**；改 `web/static/*` 前端**硬刷新**即可。
- 当前可能仍有一个后台 uvicorn 跑在 :8787（上个会话留下的）；冲突就 `pkill -f "uvicorn app:app"` 再起。
- 自查 UI：用 Windows Chrome 无头截图 →
  `"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --window-size=1440,950 --virtual-time-budget=5000 --screenshot="E:\\...\\shot.png" "http://127.0.0.1:8787/"`
  （锚点 `#hm-gallery` 截图不可靠；要确认卡片渲染用 `--dump-dom | grep -c ex-card`，应为 15）。

## LLM 后端
- 只走 **DeepSeek**（OpenAI 兼容）：模型/温度在 `config.yaml` 的 `llm` 段；
  key 优先 `web/.env`，缺省由 `web/config.py` 自动复用 personal-infoflow 的 `.env`。
- 前端输入框下方有模型下拉（自动/DeepSeek V4 Pro），每条消息带 `model` 覆盖。
- 后端配置在 import 时锁定（`llm._S`），改 `config.yaml` 需重启 uvicorn。

## UI 现状（web/static）
- 双层：**左名录=暗场画廊层、右对话=宣纸读字层**；朱红 `--zhu #B4432E` 唯一的彩，金做发丝线；
  字体 Playfair / EB Garamond / 宋体 / IBM Plex Mono。
- **首页 = 横向"展厅"**（`#home`）：暗场英雄左文字/右 **ASCII 水墨远山**（成形 + 持续雾气微动，
  `mountLandingAscii`/`startMist`）；横向展厅每位智者一件展品（**ASCII 像**，非照片显示），
  ← → 箭头/拖动/进度轨；点「请教」`askSage(id)` → 进对话。`enterHall/exitHall` 切首页↔对话
  （`body.in-hall`）；侧栏品牌「← 返回展厅」。
- 人物 ASCII 像：由 `web/static/img/av/<id>.jpg` 经脚本转 `web/static/sages-ascii.json`
  （正片 72 列；易经=太极；老子/庄子已收紧裁切）。重生成脚本思路见下。
- 三模式/SSE/停止/历史恢复/起卦抽牌/导出体悟/详情面板/移动端菜单 都在 `web/static/app.js`。
- ⚠️ `app.js` 末尾才调用 `init()`（避免顶部 const 的 TDZ）；别把 `init()` 移回顶部。

## 改人物像 / ASCII（小抄）
- 换某人照片：把新图（Wikimedia Commons 免费图）下到 `web/static/img/av/<id>.jpg`，
  再跑转换：`Image→ImageOps.grayscale/autocontrast→正片密度坡道(" .:-=+*#%@▒▓█")→写 sages-ascii.json`。
  深底/场景画要**先按 fraction 收紧裁到主体**再转（见上个会话 laozi/zhuangzi 的做法）。
- 完整素材管线参考 `web/fetch_assets.py`（头像/文物/雕塑下载+处理）。

## 人物库（15 位，`personas/*.md`）
老子·庄子·孔子·王阳明·苏轼（东）｜苏格拉底·马可奥勒留·尼采·加缪（西）｜荣格·纳瓦尔·费曼（现代）｜
毛泽东（领导者）｜易经·塔罗（术数）。加人复制 `personas/_TEMPLATE.md`（含可选 `## cases`），无需改代码。

## 注意 / 历史包袱
- 松烟 Songyan 茶站样板（`apps/`、`packages/`、`index.html`、`BUILD-PROMPT.md`、`design-system.md`）已删除——
  它是另一个产品，与解惑议事厅无关；视觉规范现以 `web/static/style.css` 为准。
- `.gitignore` 已忽略 `.env/.venv/council.db`；自用、不开源 key。
- `web/run.sh` 会在 `web/.env` 缺失时复用 infoflow 仓库的 DeepSeek key。

## 可能的下一步
扩充人物 / 命令面板分组 / 状态行显示当前模型 / 其它人物像再优化 / 远山动态幅度微调。
