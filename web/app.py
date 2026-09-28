"""Deliberation-Lab · FastAPI 后端。"""
from __future__ import annotations
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import llm
import personas
import orchestrator
import store
from config import CONFIG

app = FastAPI(title="Deliberation-Lab")
store.init_db()

STATIC = Path(__file__).parent / "static"


class ChatReq(BaseModel):
    mode: str  # solo | roundtable | council
    persona_ids: list[str]
    messages: list[dict]  # [{role, content, speaker?}]
    divination: str = ""  # 起卦/抽牌结果，注入术数人物上下文
    model: str = ""       # 前端模型覆盖：""=自动(用 config.yaml 的 llm.model) | deepseek-v4-pro
    target_id: str = ""   # 圆桌追问轮：只让这一位回应（空=全员）


class SuggestReq(BaseModel):
    question: str


class SaveReq(BaseModel):  # 每轮自动落库（不依赖导出），rolling 更新同一行
    session_id: int | None = None
    mode: str
    title: str = ""
    persona_ids: list[str] = []
    messages: list[dict]


class ExportReq(BaseModel):
    mode: str
    title: str
    persona_ids: list[str] = []
    messages: list[dict]
    reflection: str = ""  # 用户的"我的体悟"
    session_id: int | None = None  # 关联自动落库的那一行，导出时更新而非另起


@app.get("/api/health")
def health():
    return {"ok": True, "llm_configured": llm.configured(), "model": llm.model_label()}


@app.get("/api/personas")
def list_personas():
    return personas.meta_list()


@app.get("/api/persona/{pid}")
def persona_detail(pid: str):
    p = personas.get(pid)
    if not p:
        return JSONResponse({"error": "not found"}, status_code=404)
    return p


@app.post("/api/suggest")
async def suggest(req: SuggestReq):
    raw = await orchestrator.suggest(req.question, CONFIG.get("llm", {}).get("model", "deepseek-v4-pro"))
    # 容错解析 JSON
    try:
        s = raw[raw.index("{"): raw.rindex("}") + 1]
        return json.loads(s)
    except Exception:
        return {"picks": [], "raw": raw}


def _pick_model(mode: str, override: str) -> str:
    """前端指定优先；否则用配置的默认模型。"""
    if override:
        return override
    return CONFIG.get("llm", {}).get("model", "deepseek-v4-pro")


async def _sse(req: ChatReq):
    try:
        model = _pick_model(req.mode, req.model.strip())
        if req.mode == "solo":
            gen = orchestrator.solo(req.persona_ids[0], req.messages, req.divination, model)
        elif req.mode == "council":
            gen = orchestrator.roundtable(req.persona_ids, req.messages, True, req.divination, model, req.target_id)
        else:
            gen = orchestrator.roundtable(req.persona_ids, req.messages, False, req.divination, model, req.target_id)
        async for ev in gen:
            ev.pop("_full", None)  # 内部字段不外发
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    except Exception as e:  # 把错误也通过 SSE 告诉前端
        yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(req: ChatReq):
    return StreamingResponse(
        _sse(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _auto_title(messages: list[dict]) -> str:
    first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    return first.strip()[:18] or "未命名"


@app.post("/api/session/save")
def session_save(req: SaveReq):
    """每轮对话后自动落库——没导出也不会丢。"""
    title = req.title.strip() or _auto_title(req.messages)
    sid = store.upsert_session(req.session_id, req.mode, title, req.persona_ids, req.messages)
    return {"id": sid}


@app.post("/api/export")
async def export(req: ExportReq):
    model = CONFIG.get("llm", {}).get("model", "deepseek-v4-pro")
    distilled = await orchestrator.distill(req.mode, req.messages, req.persona_ids, model)
    path = store.export_to_obsidian(
        req.mode, req.title, req.messages, req.persona_ids, req.reflection, distilled
    )
    sid = store.upsert_session(req.session_id, req.mode, req.title, req.persona_ids, req.messages)
    return {"ok": True, "path": path, "distilled": bool(distilled), "id": sid}


@app.get("/api/sessions")
def sessions():
    return store.list_sessions()


@app.get("/api/sessions/{sid}")
def session(sid: int):
    s = store.get_session(sid)
    return s or JSONResponse({"error": "not found"}, status_code=404)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    # SW 必须 application/javascript，且不让浏览器缓存住旧版（否则更新策略改不动）
    return FileResponse(
        STATIC / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


app.mount("/", StaticFiles(directory=STATIC), name="static")
