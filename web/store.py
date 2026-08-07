"""会话持久化（SQLite）+ 导出为 Obsidian 笔记。"""
from __future__ import annotations
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from config import db_path, output_dir


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS sessions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created TEXT, mode TEXT, title TEXT,
                personas TEXT, messages TEXT)"""
        )


def upsert_session(
    session_id: int | None, mode: str, title: str,
    persona_ids: list[str], messages: list[dict],
) -> int:
    """有 session_id 且存在 → 原地更新（滚动保存，不堆历史）；否则新建。返回 id。"""
    pj = json.dumps(persona_ids, ensure_ascii=False)
    mj = json.dumps(messages, ensure_ascii=False)
    with _conn() as c:
        if session_id:
            cur = c.execute(
                "UPDATE sessions SET mode=?,title=?,personas=?,messages=? WHERE id=?",
                (mode, title, pj, mj, session_id),
            )
            if cur.rowcount:
                return session_id
        cur = c.execute(
            "INSERT INTO sessions(created,mode,title,personas,messages) VALUES(?,?,?,?,?)",
            (datetime.now().isoformat(timespec="minutes"), mode, title, pj, mj),
        )
        return cur.lastrowid


def list_sessions(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id,created,mode,title FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_session(sid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["personas"] = json.loads(d["personas"])
        d["messages"] = json.loads(d["messages"])
        return d


_MODE_CN = {"solo": "独对", "roundtable": "圆桌", "council": "抉择"}


def _unique_path(out: Path, stem: str) -> Path:
    """避免同名覆盖：撞名则追加 -2/-3…"""
    path = out / f"{stem}.md"
    n = 2
    while path.exists():
        path = out / f"{stem}-{n}.md"
        n += 1
    return path


def export_to_obsidian(
    mode: str, title: str, messages: list[dict],
    persona_ids: list[str] | None = None, reflection: str = "",
    distilled: dict | None = None,
) -> str:
    """写一篇 Markdown 到 vault。
    有 `distilled`（书记官蒸馏结果）→ 按 note-template 写**提炼后的洞见**笔记；
    没有 → 退回原始行为：按人物归并发言原文。返回写入路径。"""
    import personas  # 延迟导入，拿人物的学派

    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    name_school = {p["name"]: p.get("school", "") for p in personas.load_all().values()}

    if distilled:
        return _write_distilled(out, now, mode, title, distilled,
                                persona_ids or [], reflection, name_school)

    safe = re.sub(r"[\\/:*?\"<>|\s]", "", title)[:12] or "解惑"
    path = _unique_path(out, f"{now:%Y-%m-%d}-{safe}")

    # 按发言者归并（保留首次出现顺序），书记官单独收集
    order: list[str] = []
    by_speaker: dict[str, list[str]] = {}
    moderator: list[str] = []
    for m in messages:
        if m["role"] == "user":
            continue
        sp = m.get("speaker") or "某位"
        text = (m.get("content") or "").strip()
        if not text:
            continue
        if sp == "书记官":
            moderator.append(text)
            continue
        if sp not in by_speaker:
            by_speaker[sp] = []
            order.append(sp)
        by_speaker[sp].append(text)

    # 确保所有入席者即便没记录到，也列出来（不漏人）
    for pid in persona_ids or []:
        p = personas.get(pid)
        if p and p["name"] not in by_speaker:
            by_speaker[p["name"]] = ["（本次未发言）"]
            order.append(p["name"])

    confusion = next((m["content"] for m in messages if m["role"] == "user"), title)

    lines = [
        "---",
        f"date: {now:%Y-%m-%d %H:%M}",
        f"mode: {_MODE_CN.get(mode, mode)}",
        f"council: [{', '.join(order)}]",
        "tags: [解惑议事厅]",
        "---",
        "",
        f"# {title}",
        "",
        "## 我的困惑",
        confusion,
        "",
        "## 各方观点",
    ]
    for name in order:
        school = name_school.get(name, "")
        lines.append(f"### {name}" + (f"｜{school}" if school else ""))
        for utt in by_speaker[name]:
            lines.append(f"- {utt}")
        lines.append("")
    if moderator:
        lines.append("## 书记官 · 综合" + ("与抉择" if mode == "council" else ""))
        lines += ["\n".join(moderator), ""]
    lines += [
        "## 我的体悟",
        reflection.strip() if reflection.strip() else "（在此写下你看通看透之处）",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _write_distilled(
    out: Path, now: datetime, mode: str, fallback_title: str, d: dict,
    persona_ids: list[str], reflection: str, name_school: dict[str, str],
) -> str:
    """按 references/note-template 写一篇蒸馏后的洞见笔记。"""
    import personas

    title = (d.get("title") or fallback_title or "解惑").strip()

    views = d.get("views") or []
    names = [v.get("name", "").strip() for v in views if v.get("name")]
    if not names:  # 蒸馏没给名单 → 用入席者补名单（不漏人）
        names = [p["name"] for pid in persona_ids if (p := personas.get(pid))]

    safe = re.sub(r"[\\/:*?\"<>|\s]", "", title)[:12] or "解惑"
    path = _unique_path(out, f"{now:%Y-%m-%d}-{safe}")

    lines = [
        "---",
        f"date: {now:%Y-%m-%d %H:%M}",
        f"mode: {_MODE_CN.get(mode, mode)}",
        f"council: [{', '.join(names)}]",
        "tags: [解惑议事厅]",
        "---",
        "",
        f"# {title}",
        "",
        "## 我的困惑",
        (d.get("confusion") or "").strip() or "（未记录）",
        "",
        "## 各方观点",
    ]
    for v in views:
        nm = (v.get("name") or "").strip()
        pt = (v.get("point") or "").strip()
        if not nm and not pt:
            continue
        school = name_school.get(nm, "")
        head = f"{nm}｜{school}" if school else nm
        lines.append(f"> **{head}**：{pt}")
    lines.append("")

    clash = (d.get("clash") or "").strip()
    if clash:
        lines += ["## 被重构的问题" if mode == "solo" else "## 交锋的根", clash, ""]

    advice = (d.get("advice") or "").strip()
    if advice:
        lines += ["## 给我的话", advice, ""]

    nxt = (d.get("next_step") or "").strip()
    lines += ["## 下一步", f"- [ ] {nxt}" if nxt else "- [ ] （在此写下你要做的一件事）", ""]

    sitq = (d.get("sit_question") or "").strip()
    if sitq:
        lines += ["## 留给我静坐想的问题", sitq, ""]

    lines += [
        "## 我的体悟",
        reflection.strip() if reflection.strip() else "（在此写下你看通看透之处）",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
