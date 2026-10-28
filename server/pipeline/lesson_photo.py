"""Claude reads a photo of this week's textbook page into a draft lesson (items by skill).
The teacher reviews and saves it. Code keeps known skills only, short items only, at most 6 per
skill. The photo is not stored."""

from __future__ import annotations

import base64

from .claude_client import Usage, call_structured, load_prompt, load_schema
from .config import SKILL_CODES

PROMPT = "lesson_photo.v1.md"
SCHEMA = "lesson_photo.v1.json"
TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_PER_SKILL, MAX_LEN = 6, 60


def read_page(data: bytes, media_type: str, usage: Usage | None = None) -> dict:
    if media_type not in TYPES:
        raise ValueError("send a JPEG, PNG or WebP photo")
    out = call_structured(prompt=load_prompt(PROMPT), schema=load_schema(SCHEMA),
                          stable_context="(lesson photo)", request="Read this week's textbook page.",
                          effort="medium", max_tokens=8000, usage=usage,
                          image=(media_type, base64.standard_b64encode(data).decode()))
    items: dict[str, list[str]] = {}
    for it in out["items"]:
        text = " ".join(it["item"].split())
        if it["skill_code"] in SKILL_CODES and 0 < len(text) <= MAX_LEN:
            lst = items.setdefault(it["skill_code"], [])
            if text not in lst and len(lst) < MAX_PER_SKILL:
                lst.append(text)
    return {"title": out["title"][:80], "items": items, "note": out["note"]}
