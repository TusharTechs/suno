"""Stage B (SIMULATED): a 12-week term, many times over, using SUNO's real tracker and planner.

Question: over a term, does SUNO find the children who need support, including the quiet ones,
and how much does its listening list matter? Compared arms, same simulated classes:
  no_list:  a perfect written diary of what she naturally notices (visibility-weighted), scored
            by the same tracker. This is a generous baseline: real memory forgets.
  list_50:  SUNO's listening list, which she follows half the time; the rest as she naturally does.
  list_80:  SUNO's listening list, followed 80% of the time.
A listed child reads the two-item mini-ladder (one item at her likely level, one a rung away);
a child she notices on her own reads one item.
Per-statement errors (does a statement become evidence, does it land on the wrong child or the
wrong right/wrong direction) come from Stage A's measurements in eval/results/sim_pipeline.json.

Run:  uv run python eval/sim/run_term_sim.py --runs 200
Writes eval/results/sim_term.md and .json. No API calls.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.sim.teacher import STYLES  # noqa: E402
from eval.sim.world import make_class, response  # noqa: E402
from server.pipeline import planner  # noqa: E402

LESSON = json.loads((ROOT / "samples/synthetic/demo_class.json").read_text())["lesson"]
FOCUS = LESSON["focus_skills"]
WEEKS, PER_DAY, P_ABSENT, SIZE = 12, 5, 0.12, 35
CHECKPOINTS = [2, 4, 8, 12]
ARMS = {"no_list": 0.0, "list_50": 0.5, "list_80": 0.8}
TWO_ITEMS = True   # listed children read the two-item mini-ladder (planner's "also"); --one-item to compare


def measured_rates() -> dict:
    """From Stage A (SIMULATED): what fraction of each kind of statement becomes evidence, etc."""
    f = ROOT / "eval/results/sim_pipeline.json"
    rates = {"p_evidence": 0.9, "p_wrong_child": 0.01, "p_direction_wrong": 0.03, "source": "defaults"}
    if not f.exists():
        return rates
    c = Counter()
    for r in json.loads(f.read_text())["results"]:
        c.update(r["totals"]["voice_after"])
    if c["expect_evidence"] and c["evidence"]:
        n = c["evidence"]
        # Zero errors in n trials is not a zero error rate: use at least the "rule of three" upper
        # bound (3/n, ~95% confidence) so the term simulation is not flattered by a small sample.
        rates = {
            "p_evidence": c["expect_evidence_became_evidence"] / c["expect_evidence"],
            "p_wrong_child": max(c["wrong_child_evidence"] / n, 3 / n),
            "p_direction_wrong": max(1 - c["evidence_direction_ok"] / max(1, n - c["wrong_child_evidence"]), 3 / n),
            "source": f"eval/results/sim_pipeline.json (Stage A, after one-tap answers; error rates floored at 3/{n})",
        }
    return rates


def run_once(arm: str, seed: int, rates: dict) -> dict:
    rng = random.Random(seed)            # same class and same children for every arm
    k = make_class("term", SIZE, "brief", LESSON, rng)
    rng = random.Random(seed * 7919 + list(ARMS).index(arm))
    detail_mix = STYLES["brief"]["detail"]
    adherence = ARMS[arm]
    by_id = {c.child_id: c for c in k.children}
    truth = {(c.child_id, s): c.p_correct(s) < 0.5 for c in k.children for s in FOCUS}
    records: list[dict] = []
    seen: list[tuple[str, str, str, date]] = []   # memory arm: (child, skill, outcome, day)
    yesterday: set[str] = set()
    day, n_day = date(2026, 7, 6), 0
    out = {}
    first_flag: dict[tuple[str, str], int] = {}
    total_days = WEEKS * 6
    while n_day < total_days:
        present = [c for c in k.children if rng.random() > P_ABSENT]
        listening = []
        if adherence:
            pic = planner.picture(k.roster, k.lesson, records, day, yesterday)
            listening = [p for p in pic["listen_today"]]
        noticed, planned = [], {}
        for p in listening:
            c = by_id[p["child_id"]]
            if c in present and rng.random() < adherence:
                noticed.append(c)
                planned[c.child_id] = [p["skill_code"]] + ([p["also"]["skill_code"]] if p.get("also") and TWO_ITEMS else [])
        pool = [c for c in present if c not in noticed]
        while len(noticed) < PER_DAY and pool:
            c = rng.choices(pool, [x.visibility ** 1.5 for x in pool])[0]
            pool.remove(c)
            noticed.append(c)
        for c, skill in [(c, s) for c in noticed for s in (planned.get(c.child_id) or [rng.choice(FOCUS)])]:
            outcome, _ = response(c, skill, rng)
            seen.append((c.child_id, skill, outcome, day))
            if arm == "memory":
                continue
            detail = rng.choices(["item_error", "item", "skill", "vague"], detail_mix)[0]
            if detail == "vague" or rng.random() > rates["p_evidence"]:
                continue
            cid = c.child_id
            if rng.random() < rates["p_wrong_child"]:
                cid = rng.choice([x.child_id for x in k.children if x.child_id != c.child_id])
            o = outcome
            if rng.random() < rates["p_direction_wrong"]:
                o = "correct" if outcome != "correct" else "incorrect"
            records.append({"child_id": cid, "skill_code": skill, "outcome": o, "status": "evidence",
                            "kind": "observation", "confidence": 0.9, "day": day.isoformat(), "when": "today",
                            "item": "x", "home_language": "none", "teacher_quote": "", "feedback": None,
                            "rec_id": len(records) + 1})
        yesterday = {p["child_id"] for p in listening}
        n_day += 1
        # Who is flagged "needs support" today?
        if arm == "memory":
            flagged = memory_flags(seen, day, rng)
        else:
            state = planner.tracker_state(records, day)
            flagged = {key for key, s in state.items() if s.status == "needs support" and key[1] in FOCUS}
            known = {key for key, s in state.items() if s.status != "not enough evidence" and key[1] in FOCUS}
        for key in flagged:
            first_flag.setdefault(key, n_day)
        if n_day % 6 == 0 and n_day // 6 in CHECKPOINTS:
            wk = n_day // 6
            if arm == "memory":
                known = memory_known(seen, day)
            heard = {cid for cid, *_ in seen} if arm == "memory" else {r["child_id"] for r in records}
            quiet = {c.child_id for c in sorted(k.children, key=lambda c: c.visibility)[:SIZE // 3]}
            struggling = {key for key, t in truth.items() if t}
            # Child level: a child who truly needs support in Hindi reading (below the week's focus)
            # is "found" if SUNO flags any Hindi skill; the TaRL level is checked where SUNO states one.
            hindi_focus = [f for f in FOCUS if f.startswith("hi.")]
            kids_struggling = {c.child_id for c in k.children if any(truth[(c.child_id, f)] for f in hindi_focus)}
            kids_flagged = {cid for cid, sk in flagged if sk.startswith("hi.")}
            lv = {} if arm == "memory" else planner.ladders(records, day)
            stated = [(c, lv[(c.child_id, "hindi")].level) for c in k.children
                      if (c.child_id, "hindi") in lv and lv[(c.child_id, "hindi")].level is not None]
            out[wk] = {
                "children_found": len(kids_flagged & kids_struggling) / max(1, len(kids_struggling)),
                "children_flag_precision": len(kids_flagged & kids_struggling) / len(kids_flagged) if kids_flagged else float("nan"),
                "level_stated": len(stated) / SIZE,
                "level_exact": sum(c.reading == l for c, l in stated) / len(stated) if stated else float("nan"),
                "level_within_one": sum(abs(c.reading - l) <= 1 for c, l in stated) / len(stated) if stated else float("nan"),
                "children_with_evidence": len(heard) / SIZE,
                "quiet_with_evidence": len(heard & quiet) / len(quiet),
                "cells_known": len(known) / len(truth),
                "struggling_found": len(flagged & struggling) / max(1, len(struggling)),
                "flags": len(flagged), "flags_right": len(flagged & struggling),
                "quiet_struggling_found": len(flagged & {s for s in struggling if s[0] in quiet})
                / max(1, len({s for s in struggling if s[0] in quiet})),
            }
        day = planner.next_school_day(day)
    struggling = [key for key, t in truth.items() if t]
    days_to_flag = [first_flag[key] for key in struggling if key in first_flag]
    out["median_days_to_flag"] = sorted(days_to_flag)[len(days_to_flag) // 2] if days_to_flag else None
    return out


def _remembered(seen, day, rng):
    return [(c, s, o) for c, s, o, d in seen if rng.random() < math.exp(-(day - d).days / 7)]


def memory_flags(seen, day, rng) -> set:
    per = defaultdict(list)
    for c, s, o in _remembered(seen, day, rng):
        per[(c, s)].append(o)
    return {key for key, os in per.items() if len(os) >= 3 and key[1] in FOCUS
            and sum(o == "correct" for o in os) / len(os) < 0.5}


def memory_known(seen, day) -> set:
    rng = random.Random(day.toordinal())
    per = Counter((c, s) for c, s, _ in _remembered(seen, day, rng))
    return {key for key, n in per.items() if n >= 3 and key[1] in FOCUS}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--one-item", action="store_true", help="listed children read one item, not two")
    a = ap.parse_args()
    global TWO_ITEMS
    TWO_ITEMS = not a.one_item
    rates = measured_rates()
    agg = {arm: defaultdict(lambda: defaultdict(list)) for arm in ARMS}
    med = {arm: [] for arm in ARMS}
    for i in range(a.runs):
        for arm in ARMS:
            r = run_once(arm, 1000 + i, rates)
            for wk in CHECKPOINTS:
                for m, v in r[wk].items():
                    agg[arm][wk][m].append(v)
            if r["median_days_to_flag"] is not None:
                med[arm].append(r["median_days_to_flag"])
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{a.runs} runs", flush=True)

    def mean(xs):
        xs = [x for x in xs if x == x]  # drop NaN (no flags / no stated level in that run)
        return sum(xs) / len(xs) if xs else float("nan")

    names = {"no_list": "Perfect diary of what she notices (no listening list)",
             "list_50": "SUNO, list followed 50%", "list_80": "SUNO, list followed 80%"}
    lines = ["# A 12-week term with SUNO (SIMULATED, not real children or teachers)", "",
             f"Generated by `eval/sim/run_term_sim.py`: {a.runs} simulated classes of {SIZE}, {WEEKS} weeks each, "
             f"{PER_DAY} children noticed a day ({'two items' if TWO_ITEMS else 'one item'} for a listed child), {int(P_ABSENT * 100)}% absence, focus skills of the demo lesson. "
             "Uses SUNO's real tracker and planner. "
             f"Per-statement error rates from {rates['source']}: becomes evidence {rates['p_evidence']:.0%}, "
             f"wrong child {rates['p_wrong_child']:.1%}, wrong right/wrong direction {rates['p_direction_wrong']:.1%}. "
             "Assumptions in `eval/sim/world.py`, `teacher.py` and this script.", ""]
    for title, metric in [("Children who truly need support in Hindi reading whom SUNO flags", "children_found"),
                          ("…and of the children SUNO flags, how many truly need support", "children_flag_precision"),
                          ("Children whose Hindi reading level (TaRL group) SUNO states", "level_stated"),
                          ("…and the stated level is exactly right", "level_exact"),
                          ("…or within one level", "level_within_one"),
                          ("Children with any evidence", "children_with_evidence"),
                          ("Quietest third of the class with any evidence", "quiet_with_evidence"),
                          ("Child × focus-skill cells known (on track or needs support)", "cells_known"),
                          ("Struggling child × skill cells correctly flagged \"needs support\"", "struggling_found"),
                          ("…among the quietest third", "quiet_struggling_found")]:
        lines += [f"## {title}", "", "| | " + " | ".join(f"week {w}" for w in CHECKPOINTS) + " |",
                  "|---|" + "---|" * len(CHECKPOINTS)]
        for arm in ARMS:
            lines.append(f"| {names[arm]} | " + " | ".join(f"{mean(agg[arm][w][metric]):.0%}" for w in CHECKPOINTS) + " |")
        lines.append("")
    lines += ["## Precision of \"needs support\" flags at week 12", "", "| | Flags | Right |", "|---|---|---|"]
    for arm in ARMS:
        f, rgt = sum(agg[arm][12]["flags"]), sum(agg[arm][12]["flags_right"])
        lines.append(f"| {names[arm]} | {f / a.runs:.1f} per class | {rgt / f:.0%} |" if f else f"| {names[arm]} | 0 | – |")
    lines += ["", "## Median school days until a struggling child × skill is first flagged", "",
              "| | Days |", "|---|---|"]
    for arm in ARMS:
        lines.append(f"| {names[arm]} | {sorted(med[arm])[len(med[arm]) // 2] if med[arm] else '–'} |")
    md = "\n".join(lines) + "\n"
    (ROOT / "eval/results/sim_term.md").write_text(md)
    (ROOT / "eval/results/sim_term.json").write_text(json.dumps(
        {"label": "SIMULATED", "rates": rates, "runs": a.runs,
         "results": {arm: {w: {m: mean(v) for m, v in agg[arm][w].items()} for w in CHECKPOINTS} for arm in ARMS}},
        indent=1))
    print(md)


if __name__ == "__main__":
    main()
