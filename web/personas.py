"""读 personas/*.md：解析 frontmatter + 各 ## 小节，返回结构化人物。"""
from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path
import yaml

from config import PERSONAS_DIR

# 小节标题形如：## method（他怎么想问题 —— 最重要）  → key = "method"
_SECTION_RE = re.compile(r"^##\s+([A-Za-z_]+)", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        key = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[key] = body[start:end].strip().lstrip("（）()").strip()
        # 去掉小节标题剩下的"（中文说明）"那一行残留
        sections[key] = re.sub(r"^[^\n]*）\s*\n", "", sections[key], count=1).strip()
    return sections


def _parse_file(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    meta = yaml.safe_load(m.group(1)) or {}
    sections = _parse_sections(m.group(2))
    return {
        "id": meta.get("id", path.stem),
        "name": meta.get("name", path.stem),
        "aka": meta.get("aka", ""),
        "school": meta.get("school", ""),
        "era": meta.get("era", ""),
        "category": meta.get("category", ""),
        "one_line": meta.get("one_line", ""),
        "sections": sections,
    }


@lru_cache(maxsize=1)
def load_all() -> dict[str, dict]:
    """返回 {id: persona}。跳过模板。带缓存——改了人物文件需重启服务。"""
    out: dict[str, dict] = {}
    for p in sorted(PERSONAS_DIR.glob("*.md")):
        if p.stem.startswith("_"):
            continue
        person = _parse_file(p)
        if person:
            out[person["id"]] = person
    return out


def get(pid: str) -> dict | None:
    return load_all().get(pid)


def meta_list() -> list[dict]:
    """给前端的精简列表（不含大段正文）。"""
    return [
        {k: p[k] for k in ("id", "name", "aka", "school", "era", "category", "one_line")}
        for p in load_all().values()
    ]
