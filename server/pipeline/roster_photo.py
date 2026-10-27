"""Claude reads a photo of the attendance register into a roster draft. The teacher reviews it.

Code keeps first names only (one word, letters only), whatever Claude returns, and caps the
list. The photo is not stored. Nothing is saved until the teacher confirms the list.
"""

from __future__ import annotations

import base64
import unicodedata

from .claude_client import Usage, call_structured, load_prompt, load_schema

PROMPT = "roster_photo.v1.md"
SCHEMA = "roster_photo.v1.json"
MAX_CHILDREN = 80
TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def first_name_only(name: str) -> str:
    """One word, letters and vowel signs only: never a surname, number or note."""
    for word in (name or "").split():
        w = "".join(ch for ch in word if unicodedata.category(ch)[0] in "LM")  # letters and vowel signs
        if w and unicodedata.category(w[0])[0] == "L":
            return w
    return ""


def read_register(data: bytes, media_type: str, usage: Usage | None = None) -> dict:
    if media_type not in TYPES:
        raise ValueError("send a JPEG, PNG or WebP photo")
    out = call_structured(prompt=load_prompt(PROMPT), schema=load_schema(SCHEMA),
                          stable_context="(roster photo)", request="Read the children's names from this register page.",
                          effort="medium", max_tokens=8000, usage=usage,
                          image=(media_type, base64.standard_b64encode(data).decode()))
    names, seen_rolls = [], set()
    for ch in out["children"][:MAX_CHILDREN]:
        n = first_name_only(ch["first_name"])
        if not n:
            continue
        roll = ch["roll_no"] if isinstance(ch["roll_no"], int) and ch["roll_no"] not in seen_rolls else None
        if roll:
            seen_rolls.add(roll)
        names.append({"roll_no": roll, "first_name": n})
    return {"children": names, "unreadable": out["unreadable"], "note": out["note"]}
