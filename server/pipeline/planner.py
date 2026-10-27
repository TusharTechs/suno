"""The class picture, the Silence Ledger and today's listening list. Code only, no AI.

Everything the morning brief says is decided here; Claude only puts it into words.
- grid: per child and skill, the tracker status (needs support / on track / not enough evidence).
- silent: children the teacher has not described individually in the last 5 school days.
- listen_today: up to 5 children for the teacher to listen to today, each with one item
  from this week's lesson. Children with a claim to confirm come first, then the least known.
- language_flags: children who understood once it was explained in their home language.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import ladder, tracker
from .config import SKILL_CODES

LISTEN_PER_DAY = 5
WINDOW_DAYS = 5


def is_school_day(d: date) -> bool:
    return d.weekday() != 6  # government primary schools run Monday to Saturday


def next_school_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_school_day(d):
        d += timedelta(days=1)
    return d


def school_days_before(d: date, n: int) -> list[date]:
    out, cur = [], d
    while len(out) < n:
        cur -= timedelta(days=1)
        if is_school_day(cur):
            out.append(cur)
    return sorted(out)


def _day(r: dict) -> date:
    return date.fromisoformat(r["day"]) if isinstance(r["day"], str) else r["day"]


def _usable(r: dict) -> bool:
    return r.get("feedback") != "down"


def ladders(records: list[dict], today: date):
    obs = [ladder.Obs(r["child_id"], r["skill_code"], r["outcome"], r["confidence"], _day(r), r.get("error_type") or "none")
           for r in records if r["status"] == "evidence" and _usable(r) and _day(r) <= today]
    return ladder.track(obs, today)


def tracker_state(records: list[dict], today: date):
    """Per child and skill: probability of having it, observations, days, status (from the ladder)."""
    return ladder.skill_views(ladders(records, today))


def grid(roster: list[dict], state) -> dict:
    out = {}
    for c in roster:
        row = {}
        for s in SKILL_CODES:
            st = state.get((c["child_id"], s))
            row[s] = ({"status": st.status, "p": round(st.p, 2), "moments": st.moments, "days": len(st.days)}
                      if st else {"status": "not enough evidence", "p": None, "moments": 0, "days": 0})
        out[c["child_id"]] = row
    return out


def silent_children(roster: list[dict], records: list[dict], today: date) -> list[str]:
    window = school_days_before(today, WINDOW_DAYS - 1) + [today]
    heard = [(r["child_id"], _day(r)) for r in records
             if r["child_id"] and r["kind"] == "observation" and r["when"] == "today" and _usable(r)]
    absent: dict[date, set[str]] = {}
    for r in records:
        if r["status"] == "absent":
            absent.setdefault(_day(r), set()).add(r["child_id"])
    # Presence can only be judged on days the teacher sent a note: a child absent on every one of
    # them is not "silent". With no notes at all this week, nobody has been described.
    noted = [d for d in window if d in {_day(r) for r in records}]
    if not noted:
        return [c["child_id"] for c in roster]
    return tracker.silence_ledger([c["child_id"] for c in roster], heard, noted, absent)


def _least_known(cid: str, state, focus: list[str]) -> str:
    """The focus skill to listen for: one the child needs support with, else the least heard."""
    def rank(s: str):
        st = state.get((cid, s))
        return (st is None or st.status != "needs support", st.moments if st else 0, focus.index(s))
    return min(focus, key=rank)


def _item_for(lesson: dict, skill: str, salt: int) -> str:
    items = lesson["items"].get(skill) or []
    return items[salt % len(items)] if items else ""


def _confirm_list(records: list[dict], today: date) -> list[dict]:
    """Below-gate claims and opinions from the last school days that nothing later has settled:
    check them today. A claim with no skill gets one chosen by the caller."""
    since = school_days_before(today, WINDOW_DAYS)[0]
    settled = {(r["child_id"], r["skill_code"], _day(r)) for r in records if r["status"] == "evidence"}
    out, seen = [], set()
    for r in sorted(records, key=lambda r: (r["day"], r.get("rec_id", 0)), reverse=True):
        if r["status"] != "check_tomorrow" or not _usable(r):
            continue
        d = _day(r)
        if d < since or d >= today or r["child_id"] in seen:
            continue
        if any(c == r["child_id"] and (s == r["skill_code"] or not r["skill_code"]) and sd > d
               for c, s, sd in settled):
            continue
        seen.add(r["child_id"])
        out.append({"child_id": r["child_id"], "skill_code": r["skill_code"], "item": r["item"],
                    "reason": "confirm", "from_day": r["day"], "said": r["teacher_quote"]})
    return out


def listen_today(roster: list[dict], lesson: dict, records: list[dict], state, today: date,
                 yesterday_list: set[str], silent: list[str], lads=None) -> list[dict]:
    """Confirm-first, then the children and skills where one more observation tells SUNO the most
    (adaptive, like ASER's ladder): a struggle half-seen, a child never heard, a level unsure."""
    by_id = {c["child_id"]: c for c in roster}
    focus = [s for s in (lesson.get("focus_skills") or SKILL_CODES) if lesson["items"].get(s)]
    # Any skill with an item this week can be asked about (see askable below): a child stuck below
    # the week's focus (still on letters) is found by asking about letters, as ASER's ladder does.
    lads = lads if lads is not None else {}
    seen = {}  # items rotate with how often a child has been described, not with the calendar
    for r in records:
        if r["child_id"]:
            seen[r["child_id"]] = seen.get(r["child_id"], 0) + 1
    askable = [s for s in SKILL_CODES if lesson["items"].get(s)]
    plan = []
    for x in _confirm_list(records, today)[:2]:
        if not x["skill_code"] or not lesson["items"].get(x["skill_code"]):
            # A remark that names no skill ("read some words wrong") is about reading: check reading.
            reading = [f for f in focus if f.startswith("hi.")] or focus
            x["skill_code"] = _least_known(x["child_id"], state, reading)
            x["item"] = ""
        x["item"] = x["item"] or _item_for(lesson, x["skill_code"], by_id[x["child_id"]]["roll_no"] + seen.get(x["child_id"], 0))
        plan.append(x)
    taken = {p["child_id"] for p in plan}
    absent_yesterday = {r["child_id"] for r in records
                        if r["status"] == "absent" and r["day"] == school_days_before(today, 1)[0].isoformat()}
    skip = taken | (yesterday_list - absent_yesterday)
    scored = []
    for c in roster:
        cid = c["child_id"]
        if cid in skip:
            continue
        best_skill, best_info = None, -1.0
        for s in askable:
            area, need = ladder.NEED[s]
            info = ladder.information(lads.get((cid, area)), need, area)
            if info > best_info:
                best_skill, best_info = s, info
        struggling = any(state.get((cid, s)) and 0 < state[(cid, s)].p < 0.5 and not state[(cid, s)].decided
                         for s in focus)
        bonus = 0.5 * (cid in silent) + 0.3 * struggling
        scored.append((best_info + bonus, -seen.get(cid, 0), cid, best_skill, struggling))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    for _, _, cid, skill, struggling in scored[:LISTEN_PER_DAY - len(plan)]:
        st = state.get((cid, skill))
        reason = ("not_heard" if cid in silent else
                  "needs_support" if struggling or (st and st.status == "needs support") else "least_known")
        plan.append({"child_id": cid, "skill_code": skill, "reason": reason,
                     "item": _item_for(lesson, skill, by_id[cid]["roll_no"] + seen.get(cid, 0))})
    for x in plan:
        x["also"] = _second_rung(x, lads, askable, lesson, by_id[x["child_id"]]["roll_no"] + seen.get(x["child_id"], 0))
    return plan


def _second_rung(x: dict, lads, askable: list[str], lesson: dict, salt: int) -> dict | None:
    """A second item one rung up the ladder if the child probably has the first, else one rung down:
    the two-item mini-ladder ASER uses, heard while the child reads a line of the page anyway."""
    area, need = ladder.NEED[x["skill_code"]]
    st = lads.get((x["child_id"], area))
    p = st.p_has(need) if st else 0.5
    target = need + 1 if p >= 0.5 else need - 1
    options = [s for s in askable if ladder.NEED[s] == (area, target)]
    if not options:
        options = [s for s in askable if ladder.NEED[s][0] == area and ladder.NEED[s][1] != need]
        options.sort(key=lambda s: abs(ladder.NEED[s][1] - target))
        options = options[:1]
    if not options:
        return None
    skill = options[salt % len(options)]
    return {"skill_code": skill, "item": _item_for(lesson, skill, salt)}


def language_flags(records: list[dict], today: date) -> list[dict]:
    since = today - timedelta(days=21)
    flags = {}
    for r in records:
        if r["child_id"] and r.get("home_language") in ("helped", "barrier") and _day(r) >= since and _usable(r):
            flags[r["child_id"]] = {"child_id": r["child_id"], "signal": r["home_language"],
                                    "skill_code": r["skill_code"], "day": r["day"]}
    return list(flags.values())


def picture(roster: list[dict], lesson: dict, records: list[dict], today: date,
            yesterday_list: set[str] | None = None) -> dict:
    """Everything code knows about the class on `today` (morning: today's notes not in yet)."""
    lads = ladders(records, today)
    state = ladder.skill_views(lads)
    silent = silent_children(roster, records, today)
    g = grid(roster, state)
    window = set(school_days_before(today, WINDOW_DAYS - 1) + [today])
    heard_week = sorted({r["child_id"] for r in records if r["child_id"] and r["kind"] == "observation"
                         and _day(r) in window and _usable(r)})
    # "Needs support" = each child's next step on each ladder: the lowest skill they need help with
    # (Teaching at the Right Level groups), not every skill above it.
    needs = [{"child_id": c["child_id"], "skill_code": s, **g[c["child_id"]][s]}
             for c in roster for s in ladder.next_steps(state, c["child_id"]).values()]
    levels = {}
    for (cid, area), st in lads.items():
        levels.setdefault(cid, {})[area] = {"level": st.level, "moments": st.moments, "days": len(st.days),
                                            "post": [round(p, 3) for p in st.post]}
    on_track = [{"child_id": c, "skill_code": s} for c, row in g.items() for s, cell in row.items()
                if cell["status"] == "on track"]
    return {
        "today": today.isoformat(),
        "grid": g,
        "needs_support": needs,
        "on_track": on_track,
        "silent": silent,
        "heard_this_week": heard_week,
        "levels": levels,
        "listen_today": listen_today(roster, lesson, records, state, today, yesterday_list or set(), silent, lads),
        "language_flags": language_flags(records, today),
    }
