"""Trace 采集与解析：消费 orchestrator 的事件流，构建结构化 Trace。

事件协议（来自 orchestrator）：
  {"type":"speaker", "id","name","school"}  发言者开始
  {"type":"delta",   "text"}                正文增量
  {"type":"end",     "_full": "完整文本"}    发言者结束
  {"type":"done"}                            整轮结束
  {"type":"error",   "message"}             错误
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import AsyncIterator


@dataclass
class SpeakerTurn:
    """一位发言者在某一轮的完整发言。"""
    id: str
    name: str
    school: str
    text: str = ""

    def is_moderator(self) -> bool:
        return self.id == "moderator"


@dataclass
class TraceTurn:
    """一个 user turn 的完整采集结果（可能包含多位发言者）。"""
    turn_index: int
    user_message: str
    speakers: list[SpeakerTurn] = field(default_factory=list)
    moderator: SpeakerTurn | None = None
    error: str = ""

    @property
    def full_text(self) -> str:
        """这一轮的完整可读文本。"""
        lines = [f"【用户】{self.user_message}"]
        for s in self.speakers:
            lines.append(f"【{s.name}（{s.school}）】\n{s.text}")
        if self.moderator:
            lines.append(f"【书记官】\n{self.moderator.text}")
        return "\n\n".join(lines)


@dataclass
class Trace:
    """一次完整场景评测的 Trace（可能包含多个 turn）。"""
    scenario_id: str
    backend: str
    model: str
    mode: str
    persona_ids: list[str]
    timestamp: str = ""
    turns: list[TraceTurn] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="seconds")

    @property
    def full_transcript(self) -> str:
        """所有 turn 拼接的完整对话文本，供 Judge 阅读。"""
        return "\n\n" + "=" * 60 + "\n\n".join(
            t.full_text for t in self.turns
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


async def collect_from_orchestrator(
    gen: AsyncIterator[dict],
    turn_index: int,
    user_message: str,
) -> TraceTurn:
    """消费 orchestrator 的 async generator，构建一个 TraceTurn。

    gen 是 orchestrator.solo() 或 orchestrator.roundtable() 的返回值。
    """
    turn = TraceTurn(turn_index=turn_index, user_message=user_message)
    current: SpeakerTurn | None = None
    text_buf: list[str] = []

    async for ev in gen:
        etype = ev.get("type")

        if etype == "speaker":
            # 保存上一个发言者
            if current is not None:
                current.text = "".join(text_buf)
                _store_speaker(turn, current)
            current = SpeakerTurn(
                id=ev.get("id", ""),
                name=ev.get("name", ""),
                school=ev.get("school", ""),
            )
            text_buf = []

        elif etype == "delta":
            text_buf.append(ev.get("text", ""))

        elif etype == "end":
            # _full 字段有完整文本（比 delta 拼接更可靠）
            full = ev.get("_full", "")
            if current is not None:
                current.text = full if full else "".join(text_buf)
                _store_speaker(turn, current)
                current = None
                text_buf = []

        elif etype == "error":
            turn.error = ev.get("message", "未知错误")

        elif etype == "done":
            # 确保最后一个发言者已保存
            if current is not None:
                current.text = "".join(text_buf)
                _store_speaker(turn, current)
                current = None

    return turn


def _store_speaker(turn: TraceTurn, speaker: SpeakerTurn) -> None:
    """把发言者存入 turn（区分 moderator 和普通智者）。"""
    if speaker.is_moderator():
        turn.moderator = speaker
    else:
        turn.speakers.append(speaker)
