"""Versioned domain config: the skill ladder and the activity bank (config/*.json)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SKILLS = json.loads((ROOT / "config" / "skills.v1.json").read_text())
ACTIVITIES = json.loads((ROOT / "config" / "activities.v1.json").read_text())["activities"]
SKILL_CODES = [s["code"] for s in SKILLS["skills"]]
SKILL_BY_CODE = {s["code"]: s for s in SKILLS["skills"]}
