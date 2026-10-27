"""Where each child is on the ladder. Code only, no AI.

Early reading and number sense are ladders (ASER / Teaching at the Right Level; EGRA learner
profiles): letters -> simple words -> words with vowel signs -> sentences -> story and meaning.
So one observation says something about several skills: a child who reads a sentence knows her
letters; a child who can't yet blend कमल can't yet read sentences. SUNO keeps, for each child and
area (Hindi reading, maths, English), a probability for every level, updated by each checked
observation (Bayes' rule). From it come:
- per skill: the probability the child has it, and a status (needs support / on track / not
  enough evidence), named only after >= 3 observations on that ladder over >= 2 days;
- per child: a level (the TaRL group) once SUNO is sure enough;
- the next skill to teach: the lowest skill the child needs support with.

The mistake a teacher describes is evidence too: "read कमल as क-म-ल" means the letters are
known; "read पानी as पनी" means the child blends. Evidence fades with age (a child learns; half-life six weeks), and
counts in proportion to its confidence.
"""

from __future__ import annotations

import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .config import SKILLS

MIN_MOMENTS = int(os.environ.get("NAMING_MIN_MOMENTS", "3"))
MIN_DAYS = int(os.environ.get("NAMING_MIN_DAYS", "2"))
NEEDS_SUPPORT_AT, ON_TRACK_AT = 0.2, 0.8     # probability the child has the skill
LEVEL_SURE_AT = 0.6                          # posterior mass needed to state a child's level
HALF_LIFE_DAYS = 42                          # an observation counts half after six weeks (levels move slowly)
IMPLIED_WEIGHT = 0.6

LEVELS = {a["area"]: len(a["levels"]) for a in SKILLS["areas"]}
NEED = {s["code"]: (s["area"], s["level"]) for s in SKILLS["skills"]}
ORDER = [s["code"] for s in SKILLS["skills"]]

# P(outcome | the child's level vs the level the skill needs). Deliberately not the same numbers
# as the simulation's world (eval/sim/world.py), so the tracker is not tested against itself.
LIKELIHOOD = {
    "has":       {"correct": 0.80, "partial": 0.12, "incorrect": 0.08},
    "one_below": {"correct": 0.25, "partial": 0.30, "incorrect": 0.45},
    "far_below": {"correct": 0.10, "partial": 0.25, "incorrect": 0.65},
}

# A described mistake that shows lower skills are in place.
IMPLIES = {
    "segments_without_blending": ["hi.letters"],
    "matra_omitted": ["hi.letters", "hi.blend_no_matra"],
    "matra_confused": ["hi.letters", "hi.blend_no_matra"],
    "letter_by_letter": ["hi.letters", "hi.blend_no_matra"],
    "conjunct_broken": ["hi.letters", "hi.blend_no_matra", "hi.words_with_matras"],
    "meaning_not_understood": ["hi.sentence"],
    "place_value_confusion": ["math.number_recognition"],
    "counting_error": ["math.number_recognition"],
    "operation_confused": ["math.number_recognition"],
}


@dataclass
class Obs:
    child_id: str
    skill: str
    outcome: str        # correct | incorrect | partial
    confidence: float   # from confidence.py, already >= gate
    day: date
    error_type: str = "none"


@dataclass
class LadderState:
    area: str
    post: list[float]
    moments: int = 0
    days: set = field(default_factory=set)
    seen: dict = field(default_factory=dict)   # skill -> direct observations

    @property
    def decided(self) -> bool:
        return self.moments >= MIN_MOMENTS and len(self.days) >= MIN_DAYS

    def p_has(self, need: int) -> float:
        return sum(self.post[need:])

    @property
    def level(self) -> int | None:
        """The child's level (TaRL group) once SUNO is sure enough, else None."""
        if not self.decided:
            return None
        best = max(range(len(self.post)), key=lambda i: self.post[i])
        return best if self.post[best] >= LEVEL_SURE_AT else None


@dataclass
class SkillView:
    """What the ladder says about one child and one skill (same fields the planner and API use)."""
    p: float
    moments: int
    days: set
    decided: bool
    direct: int = 0     # observations of this very skill (the rest is inferred from the ladder)

    @property
    def status(self) -> str:
        if not self.decided:
            return "not enough evidence"
        if self.p <= NEEDS_SUPPORT_AT:
            return "needs support"
        if self.p >= ON_TRACK_AT:
            return "on track"
        return "not enough evidence"


def _band(level: int, need: int) -> str:
    return "has" if level >= need else "one_below" if level == need - 1 else "far_below"


def _update(st: LadderState, need: int, outcome: str, weight: float) -> None:
    post = [p * LIKELIHOOD[_band(lvl, need)][outcome] ** weight for lvl, p in enumerate(st.post)]
    z = sum(post)
    st.post = [p / z for p in post]


def track(observations: list[Obs], today: date) -> dict[tuple[str, str], LadderState]:
    ladders: dict[tuple[str, str], LadderState] = {}
    for o in sorted(observations, key=lambda o: o.day):
        if o.skill not in NEED or o.outcome not in ("correct", "partial", "incorrect"):
            continue
        area, need = NEED[o.skill]
        st = ladders.get((o.child_id, area))
        if st is None:
            n = LEVELS[area]
            st = ladders[(o.child_id, area)] = LadderState(area, [1.0 / n] * n)
        w = o.confidence * 0.5 ** ((today - o.day).days / HALF_LIFE_DAYS)
        _update(st, need, o.outcome, w)
        for lower in IMPLIES.get(o.error_type, []):
            if NEED[lower][0] == area:
                _update(st, NEED[lower][1], "correct", w * IMPLIED_WEIGHT)
        st.moments += 1
        st.days.add(o.day)
        st.seen[o.skill] = st.seen.get(o.skill, 0) + 1
    return ladders


def skill_views(ladders: dict[tuple[str, str], LadderState]) -> dict[tuple[str, str], SkillView]:
    out = {}
    for (cid, area), st in ladders.items():
        for skill, (a, need) in NEED.items():
            if a == area:
                out[(cid, skill)] = SkillView(round(st.p_has(need), 3), st.moments, st.days, st.decided,
                                              st.seen.get(skill, 0))
    return out


def next_steps(views: dict[tuple[str, str], SkillView], child_id: str) -> dict[str, str]:
    """Per area, the lowest skill on the ladder the child needs support with (what to teach next)."""
    out: dict[str, str] = {}
    # Lowest level first; at the same level, a skill the teacher actually described wins.
    def key(s: str):
        v = views.get((child_id, s))
        return (NEED[s][1], -(v.direct if v else 0), ORDER.index(s))
    for skill in sorted(ORDER, key=key):
        v = views.get((child_id, skill))
        area = NEED[skill][0]
        if v and v.status == "needs support" and area not in out:
            out[area] = skill
    return out


def information(st: LadderState | None, need: int, area: str) -> float:
    """Expected information from one more observation of a skill (entropy of has / hasn't)."""
    p = st.p_has(need) if st else (LEVELS[area] - need) / LEVELS[area]
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
