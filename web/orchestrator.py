"""把 personas + orchestration 规则变成实际的对话编排（流式事件）。

事件协议（app.py 会转成 SSE）：
  {"type":"speaker", "id","name","school"}  一位发言者开始
  {"type":"delta",   "text"}                正文增量
  {"type":"end"}                            当前发言者结束
  {"type":"done"}                           整轮结束
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import llm
import personas


# ── 系统提示构建 ────────────────────────────────────────────────

def _persona_system(p: dict, extra: str) -> str:
    s = p["sections"]
    cases = f"\n【你常引以为例的典型案例】{s['cases']}" if s.get("cases") else ""
    return f"""你现在就是{p['name']}（{p['school']}·{p['era']}）。是{p['name']}本人在说话，不是在分析或介绍{p['name']}。{cases}

【你的世界观】{s.get('worldview','')}
【你的核心思想】{s.get('core_ideas','')}
【你思考问题的方式——务必照此拆解用户的具体困惑】{s.get('method','')}
【你说话的方式——严格保持，让人一眼认出是你】{s.get('voice','')}
【你会反对/警惕什么】{s.get('pushback_on','')}
【你的局限——必要时坦诚，绝不神化自己】{s.get('blindspots','')}

铁律：
1. 用"你思考问题的方式"真正拆解用户当下这个具体困惑，落到他的处境，不要泛泛而谈、不要堆砌名言（引用原话最多一句，且要服务于推进）。
2. 严格保持你的语气，用第一人称。绝不说"作为AI/作为语言模型"之类抽离的话。
3. 该点破用户的回避、自欺、矛盾时，直接点破。
{extra}"""


_EXTRA_SOLO = "4. 这是一对一深谈：若这是开场第一轮，先用你的方式重述、重构他的困惑——常常困惑本身就被问错了，点出他真正卡在哪；之后每轮多用反问引导他自己想，每次只推进一步，简洁有力，别长篇大论。结尾给一句你的赠言和一个具体的下一步。"
_EXTRA_RT_STATE = "4. 这是圆桌，其他智者也在场。先简短给出你对这个困惑的判断，要有锋芒，3-5 句即可。"
_EXTRA_RT_CLASH = "4. 这是圆桌交锋环节。针对其他智者发言里你最不认同的地方，直接回应、反驳（尤其撞上你反对的观点时点名回应），简短犀利，2-4 句。"
_EXTRA_COUNCIL = "4. 这是议事会表态：极简说明你的立场，给他一句直击要害的忠告，2-3 句。"
_EXTRA_FOLLOW = "4. 用户追问了。结合此前讨论，用你的方式简短回应他的追问，2-4 句。"

_MOD_ROUNDTABLE = """你是议事厅的书记官（主持人），中立、克制、有洞察力。各位智者已发言完毕。请做小结：
- 点出分歧的根在哪——用户的困惑往往正卡在这个取舍上；
- 指出各视角是否有共识；
- 不投票、不强行统一，最后温和把话头交还用户。
简洁，不灌鸡汤，平实地说。"""

_MOD_COUNCIL = """你是议事厅的书记官。各位智者已表态。请给用户一个可落地的综合判断，严格按此结构（用 Markdown 粗体小标题）：
**共识**：（若有）一句话。
**真正的取舍**：他在用什么换什么——点破不可调和处。
**建议的下一步**：具体、今天或本周可做的一件事。
**留给你静坐想的问题**：一个开放问题。
强调：决定权在用户，你只帮他看清，不替他活。简洁。"""


def _context_block(question: str, prior: str, transcript: str, instruction: str) -> str:
    parts = [f"用户的困惑：{question}"]
    if prior:
        parts.append(f"\n此前的对话：\n{prior}")
    if transcript:
        parts.append(f"\n本轮已发言：\n{transcript}")
    parts.append(f"\n{instruction}")
    return "\n".join(parts)


def _prior_from_history(messages: list[dict]) -> tuple[str, str]:
    """返回 (最新用户困惑, 之前对话的纯文本摘要)。"""
    question = ""
    prior_lines: list[str] = []
    for m in messages:
        if m["role"] == "user":
            if question:  # 上一条 user 进入 prior
                prior_lines.append(f"用户：{question}")
            question = m["content"]
        else:
            prior_lines.append(f"{m.get('speaker','某位')}：{m['content']}")
    return question, "\n".join(prior_lines)


async def _maybe_summarize(text: str, max_chars: int = 2400, model: str | None = None) -> str:
    """长文压缩成'前情提要'，控制 token 与延迟。短文原样返回。"""
    if len(text) <= max_chars:
        return text
    sys = "把下面的对话压缩成简洁的'前情提要'：保留各方关键立场与尚未解决的分歧，150 字内，中文。"
    try:
        return await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": text}],
            temperature=0.3, model=model,
        )
    except Exception:
        return text[-max_chars:]


# ── 模式一：独对 ────────────────────────────────────────────────

async def solo(persona_id: str, messages: list[dict], divination: str = "", model: str | None = None) -> AsyncIterator[dict]:
    p = personas.get(persona_id)
    if not p:
        yield {"type": "error", "message": f"找不到人物 {persona_id}"}
        return
    system = _persona_system(p, _EXTRA_SOLO)
    convo = [{"role": "system", "content": system}]
    if divination:
        convo.append({"role": "system",
                      "content": f"【本局占卜】{divination} —— 若你擅长术数，请结合此象为他解读。"})
    # 独对走多轮：过长则压缩较早的历史，只保留最近 6 条原文
    hist = messages
    if len(messages) > 6 and sum(len(m.get("content", "")) for m in messages) > 4000:
        old, hist = messages[:-6], messages[-6:]
        digest = await _maybe_summarize(
            "\n".join(f"{m.get('speaker') or ('我' if m['role']=='user' else '对方')}：{m['content']}"
                      for m in old), 200, model)
        convo.append({"role": "system", "content": "前情提要：" + digest})
    for m in hist:
        role = "user" if m["role"] == "user" else "assistant"
        convo.append({"role": role, "content": m["content"]})
    yield {"type": "speaker", "id": p["id"], "name": p["name"], "school": p["school"]}
    buf = []
    async for piece in llm.stream(convo, model=model):
        buf.append(piece)
        yield {"type": "delta", "text": piece}
    yield {"type": "end", "_full": "".join(buf)}
    yield {"type": "done"}


# ── 模式二/三：圆桌 / 抉择 ──────────────────────────────────────

async def roundtable(
    persona_ids: list[str], messages: list[dict], council: bool = False, divination: str = "",
    model: str | None = None, target_id: str = "",
) -> AsyncIterator[dict]:
    people = [personas.get(i) for i in persona_ids]
    people = [p for p in people if p]
    if len(people) < 2:
        yield {"type": "error", "message": "圆桌至少需要 2 位智者"}
        return
    pmap = {p["id"]: p for p in people}

    question, prior = _prior_from_history(messages)
    follow_up = bool(prior)  # 有此前对话 = 追问轮
    prior = await _maybe_summarize(prior, model=model)  # 长对话压缩，控 token
    if divination:
        question = f"{question}\n\n【本局占卜】{divination}"
    transcript = ""

    async def run_speaker(p, extra, instruction):
        """流式一位发言；空输出自动重试，保证人人都说话（修复"未发言"）。"""
        nonlocal transcript
        system = _persona_system(p, extra)
        content = _context_block(question, prior, transcript, instruction)
        yield {"type": "speaker", "id": p["id"], "name": p["name"], "school": p["school"]}
        full = ""
        async for piece in llm.stream(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            model=model,
        ):
            full += piece
            yield {"type": "delta", "text": piece}
        if not full.strip():  # 空输出 → 加重指令重试一次
            retry = content + "\n\n（请务必用中文，至少两三句给出你的看法，不要沉默。）"
            async for piece in llm.stream(
                [{"role": "system", "content": system}, {"role": "user", "content": retry}],
                temperature=0.9, model=model,
            ):
                full += piece
                yield {"type": "delta", "text": piece}
        if not full.strip():
            full = "（此刻沉吟，未予置评。）"
            yield {"type": "delta", "text": full}
        yield {"type": "end", "_full": full}
        transcript += f"\n{p['name']}｜{p['school']}：{full}\n"

    if follow_up:
        # 追问轮：默认每人回应一次；指定 target_id 则只让那一位回应（省额度、可深挖某人）
        responders = people
        if target_id:
            responders = [p for p in people if p["id"] == target_id] or people
        for p in responders:
            async for ev in run_speaker(p, _EXTRA_FOLLOW, "请回应用户的这个追问。"):
                yield ev
    else:
        # 第一轮 · 立论：人人各发一言（先保证全员覆盖）
        state_extra = _EXTRA_COUNCIL if council else _EXTRA_RT_STATE
        for p in people:
            async for ev in run_speaker(p, state_extra, "立论：用你的方式给出你对这困惑的判断。"):
                yield ev
        # 第二轮 · 交锋：由"辩论导演"定向编排，让真正对立者点名互驳（替代轮流）
        if not council and len(people) >= 2:
            plan = await _plan_debate(question, transcript, people, model)
            for step in plan:
                p = pmap.get(step.get("speaker"))
                if not p:
                    continue
                async for ev in run_speaker(p, _EXTRA_RT_CLASH, step.get("instruction", "请回应。")):
                    yield ev

    # 书记官小结
    yield {"type": "speaker", "id": "moderator", "name": "书记官", "school": "主持"}
    mod_system = _MOD_COUNCIL if council else _MOD_ROUNDTABLE
    mod_user = f"用户的困惑：{question}\n\n全部发言：\n{transcript}"
    buf = []
    async for piece in llm.stream(
        [{"role": "system", "content": mod_system}, {"role": "user", "content": mod_user}],
        temperature=0.4, model=model,
    ):
        buf.append(piece)
        yield {"type": "delta", "text": piece}
    yield {"type": "end", "_full": "".join(buf)}
    yield {"type": "done"}


async def _plan_debate(question: str, transcript: str, people: list[dict], model: str | None = None) -> list[dict]:
    """辩论导演：看完立论，设计一场聚焦交锋（3-5 个发言），让对立者点名互驳，
    而不是让所有人机械轮流。返回 [{speaker, instruction}]。"""
    ids = {p["id"] for p in people}
    roster = "；".join(f"{p['id']}={p['name']}（{p['one_line']}）" for p in people)
    sys = (
        "你是议事厅的辩论导演。读完各位智者的立论后，设计一场**聚焦的交锋**：\n"
        "- 抓住分歧最尖锐的两三处，安排真正对立的人**点名互相反驳**；\n"
        "- 不要让所有人平均轮流空谈；同一个人可再次发言以回击；\n"
        "- 总共 3-5 个发言，按精彩程度排序。\n"
        '只返回 JSON：{"plan":[{"speaker":"<id>","instruction":"针对谁、就什么分歧、做什么，一句中文"}]}'
    )
    user = f"名册(id=名)：{roster}\n\n各位立论：\n{transcript}\n\n用户困惑：{question}"
    try:
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.5, model=model,
        )
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        plan = [s for s in data.get("plan", []) if s.get("speaker") in ids][:5]
        if plan:
            return plan
    except Exception:
        pass
    # 兜底：每人针对最不认同的一位反驳一次
    return [{"speaker": p["id"], "instruction": "针对你最不认同的一位，点名直接反驳。"}
            for p in people][:4]


# ── 沉淀：把整场对话蒸馏成结构化笔记（L3 crown jewel）─────────────

def _full_transcript(messages: list[dict]) -> str:
    lines: list[str] = []
    for m in messages:
        text = (m.get("content") or "").strip()
        if not text:
            continue
        if m["role"] == "user":
            lines.append(f"【他的困惑/追问】{text}")
        else:
            lines.append(f"{m.get('speaker') or '某位'}：{text}")
    return "\n".join(lines)


async def distill(mode: str, messages: list[dict], persona_ids: list[str], model: str | None = None) -> dict | None:
    """书记官把这场解惑蒸馏成一篇给'未来的他'回看的笔记——提炼洞见，而非复述对话。
    返回结构化 dict（store 负责按模板组装 markdown）；失败返回 None，由 store 走原始兜底。"""
    transcript = _full_transcript(messages)
    if not transcript.strip():
        return None
    mode_cn = {"solo": "独对", "roundtable": "圆桌", "council": "抉择"}.get(mode, mode)
    if mode == "solo":
        clash_key = "被这位智者重构后的问题——他这困惑是不是本身就被问错了，1-3 句"
    else:
        clash_key = "分歧的根：各方真正卡在哪个取舍上，他的困惑往往正卡在这个根上，1-3 句"
    sys = (
        "你是议事厅的书记官。把这次解惑蒸馏成一篇笔记，写给【未来回看的他】——"
        "提炼能复用的洞见，绝不复述整段对话，不灌鸡汤。\n"
        "只返回 JSON，不要任何别的字：\n"
        "{\n"
        '  "title": "一句话标题，≤16字，概括这个困惑",\n'
        '  "confusion": "把他的困惑整理成1-3句，保留他真正卡住的地方",\n'
        '  "views": [{"name":"发言者原名（与对话中一致）","point":"这一方的核心判断，1-2句提炼"}],\n'
        f'  "clash": "{clash_key}",\n'
        '  "advice": "综合给他的话/赠言，点透即可，不强行统一，1-3句",\n'
        '  "next_step": "一件具体、今天或本周就能做的事",\n'
        '  "sit_question": "一个值得他静坐去想的开放问题"\n'
        "}"
    )
    user = f"模式：{mode_cn}\n\n这次解惑的全过程：\n{transcript}"
    try:
        raw = await llm.complete(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.4, model=model,
        )
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        if isinstance(data, dict) and (data.get("confusion") or data.get("views")):
            return data
    except Exception:
        pass
    return None


# ── 选人建议 ────────────────────────────────────────────────────

async def suggest(question: str, model: str | None = None) -> str:
    roster = "\n".join(
        f"- {p['id']}｜{p['name']}（{p['school']}）：{p['one_line']}"
        for p in personas.load_all().values()
    )
    sys = """你是议事厅的选人助手。根据用户的困惑，从名册中挑 3-4 位最对症的智者上圆桌，
**必须故意掺入一位会唱反调的**，以保证有真实交锋。只返回 JSON，不要别的：
{"picks":[{"id":"...", "reason":"一句话为什么选他"}]}"""
    user = f"名册：\n{roster}\n\n用户的困惑：{question}"
    return await llm.complete(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}], model=model
    )
