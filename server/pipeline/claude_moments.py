"""Claude call 1: rebuild question-answer moments from one lesson's transcript.

Input: roster, lesson context, segments (speaker type + text), teacher taps.
Output: moments (schemas/moments.v1.json), then verified by guardrails.check_moments.
"""

from __future__ import annotations

import json

from .claude_client import Usage, call_structured, load_prompt, load_schema
from .guardrails import check_moments

PROMPT = "moments.v1.md"
SCHEMA = "moments.v1.json"


def _stable_context(roster: list[dict], lesson: dict) -> str:
    # Sorted keys keep the cached prefix byte-identical across calls.
    return ("ROSTER\n" + json.dumps(roster, ensure_ascii=False, sort_keys=True)
            + "\n\nLESSON\n" + json.dumps(lesson, ensure_ascii=False, sort_keys=True))


def _request(segments: list[dict], taps: list[dict]) -> str:
    lines = [f'{s["seg_id"]} [{s["t0"]:.1f}-{s["t1"]:.1f}s] {s["speaker"]}: {s["text"]}' for s in segments]
    tap_lines = [f'tap at {t["t"]:.1f}s: {t["child_id"]}' for t in taps] or ["(no taps)"]
    return "SEGMENTS\n" + "\n".join(lines) + "\n\nTAPS\n" + "\n".join(tap_lines)


def rebuild_moments(roster: list[dict], lesson: dict, segments: list[dict], taps: list[dict],
                    usage: Usage | None = None) -> tuple[list[dict], list[dict], list[tuple]]:
    """Returns (claude_moments, verified_moments, problems)."""
    out = call_structured(
        prompt=load_prompt(PROMPT),
        schema=load_schema(SCHEMA),
        stable_context=_stable_context(roster, lesson),
        request=_request(segments, taps),
        usage=usage,
    )
    raw = out["moments"]
    verified, problems = check_moments(raw, segments, taps, roster)
    return raw, verified, problems
