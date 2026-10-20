"""Per-child, per-skill belief, the Silence Ledger and tomorrow's call-ons. Code only, no AI.

Tracker: Beta(alpha, beta) per child and skill, starting at (1, 1). Each piece
of evidence that passed the gate with confidence c adds c to alpha (correct),
to beta (incorrect), or c/2 to each (partial). Evidence older than two weeks
counts half. A child is named only with >= 3 moments over >= 2 days.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

MIN_MOMENTS = int(os.environ.get("NAMING_MIN_MOMENTS", "3"))
MIN_DAYS = int(os.environ.get("NAMING_MIN_DAYS", "2"))
NEEDS_SUPPORT_BELOW, ON_TRACK_ABOVE = 0.5, 0.7
OLD_AFTER = timedelta(days=14)


@dataclass
class Evidence:
    child_id: str
    skill: str
    outcome: str          # correct | incorrect | partial
    confidence: float     # from confidence.py, already >= gate
    day: date


@dataclass
class SkillState:
    alpha: float = 1.0
    beta: float = 1.0
    moments: int = 0
    days: set = field(default_factory=set)

    @property
    def p(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def status(self) -> str:
        if self.moments < MIN_MOMENTS or len(self.days) < MIN_DAYS:
            return "not enough evidence"
        if self.p < NEEDS_SUPPORT_BELOW:
            return "needs support"
        if self.p > ON_TRACK_ABOVE:
            return "on track"
        return "not enough evidence"


def track(evidence: list[Evidence], today: date) -> dict[tuple[str, str], SkillState]:
    state: dict[tuple[str, str], SkillState] = defaultdict(SkillState)
    for e in evidence:
        w = e.confidence * (0.5 if today - e.day > OLD_AFTER else 1.0)
        s = state[(e.child_id, e.skill)]
        if e.outcome == "correct":
            s.alpha += w
        elif e.outcome == "incorrect":
            s.beta += w
        elif e.outcome == "partial":
            s.alpha += w / 2
            s.beta += w / 2
        else:
            continue
        s.moments += 1
        s.days.add(e.day)
    return dict(state)


def silence_ledger(roster_ids: list[str], heard: list[tuple[str, date]], school_days: list[date],
                   absent: dict[date, set[str]] | None = None) -> list[str]:
    """Children with no individual moment in the last 5 school days they attended."""
    last5 = sorted(school_days)[-5:]
    heard_ids = {c for c, d in heard if d in last5}
    absent = absent or {}
    present_some_day = {c for c in roster_ids if any(c not in absent.get(d, set()) for d in last5)}
    return [c for c in roster_ids if c in present_some_day and c not in heard_ids]


def plan_call_ons(roster_ids: list[str], state: dict[tuple[str, str], SkillState], skills: list[str],
                  called_yesterday: set[str], k: int = 5) -> list[str]:
    """Up to k children with the fewest confident moments on this week's skills;
    those needing support break ties first. Never the same child two days running."""
    def key(c: str):
        moments = sum(state[(c, s)].moments for s in skills if (c, s) in state)
        support = any(state[(c, s)].status == "needs support" for s in skills if (c, s) in state)
        return (moments, not support, c)
    return sorted((c for c in roster_ids if c not in called_yesterday), key=key)[:k]
