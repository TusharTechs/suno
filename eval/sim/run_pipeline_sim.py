"""Stage A (SIMULATED): SUNO's real pipeline on simulated classrooms, scored against ground truth.

For each simulated class and school day:
  planner (real code) picks today's listening list
  -> the simulated teacher notices children (some from the list, the rest by visibility) and
     states what they actually did, in her style (eval/sim/teacher.py)
  -> Claude voices her statements as a spoken note; Sarvam text-to-speech speaks it; Sarvam
     speech-to-text transcribes it (real recognition errors)
  -> SUNO's real pipeline (Claude + code checks + confidence)
  -> the teacher answers SUNO's name questions the way she would (she knows whom she meant)
  -> scored against ground truth; records feed the planner for the next day.
The same note is also run on its clean text, to measure what speech recognition costs.

Run:  uv run python eval/sim/run_pipeline_sim.py --days 8
Writes eval/results/sim_pipeline.md and eval/results/sim_pipeline.json. Costs roughly $0.05 of
Claude credit per note plus a little Sarvam usage.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.sim.teacher import STYLES, day_statements, voice_note  # noqa: E402
from eval.sim.world import SKILL_REQ, make_class  # noqa: E402
from server.pipeline import asr, claude_observations, planner, tts  # noqa: E402
from server.pipeline.claude_client import Usage  # noqa: E402
from server.pipeline.guardrails import has_banned_words, settle_attribution  # noqa: E402

LESSON = json.loads((ROOT / "samples/synthetic/demo_class.json").read_text())["lesson"]
FOCUS = ["hi.matras", "hi.blend_no_matra", "hi.words_with_matras", "hi.sentence", "hi.comprehension",
         "math.number_recognition", "math.place_value", "math.addition"]
SPEAKER = {"precise": "ritu", "brief": "kavya", "impressionistic": "priya", "hinglish": "aditya"}
START = date(2026, 9, 7)
_lock = threading.Lock()


def not_correct(o: str) -> bool:
    return o in ("incorrect", "partial")


def match(rec: dict, statements: list[dict]) -> dict | None:
    """The ground-truth statement a record is about: same child, then same kind, skill, item."""
    gts = [s for s in statements if s["child_id"] == rec["child_id"]]
    if not gts:
        return None
    def score(s):
        return ((s["kind"] == rec["kind"]) * 4 + (s["skill"] == rec["skill_code"]) * 2
                + bool(rec["item"] and s.get("lesson_item") and rec["item"] in (s["lesson_item"], s["item"])))
    return max(gts, key=score)


def answer_questions(out: dict, statements: list[dict]) -> list[str]:
    """The teacher taps whom she meant. Returns what happened to each question."""
    by_mid = {r["mention_id"]: r for r in out["records"]}
    log = []
    for q in out["questions"]:
        rec = by_mid.get(q["mention_id"])
        if rec is None:
            continue
        # She sees the card (name heard, skill, word, outcome) and taps the child she meant.
        if q["type"] == "which_child":
            pool = [s for s in statements if s["child_id"] in q["candidates"] and s["kind"] == "observation"]
        else:
            taken = {r["child_id"] for r in out["records"] if r["child_id"]}
            pool = [s for s in statements if s["kind"] == "observation" and s["child_id"] not in taken]
        pool = sorted(pool, key=lambda s: -((s["skill"] == rec["skill_code"]) * 2
                                            + bool(rec["item"] and rec["item"] in (s["lesson_item"], s["item"]))))
        if pool and (len(pool) == 1 or pool[0]["skill"] == rec["skill_code"]):
            new = settle_attribution(rec, pool[0]["child_id"])
            rec.update(new)
            log.append("answered")
        else:
            rec["status"] = "dismissed"
            log.append("skipped")
    return log


def score_note(statements: list[dict], records: list[dict], follow_ups: list[dict]) -> dict:
    c = Counter()
    for r in records:
        if r["child_id"] is None:
            continue
        c["attributed"] += 1
        gt = match(r, statements)
        if gt is None:
            c["wrong_child"] += 1
            if r["status"] == "evidence":
                c["wrong_child_evidence"] += 1
            continue
        if r["status"] == "evidence":
            c["evidence"] += 1
            if gt["kind"] != "observation":
                c["evidence_from_non_observation"] += 1
            elif r["outcome"] == gt["outcome"] or (not_correct(r["outcome"]) and not_correct(gt["outcome"])):
                c["evidence_direction_ok"] += 1
                c["evidence_exact_outcome"] += r["outcome"] == gt["outcome"]
            c["evidence_skill_ok"] += r["skill_code"] == gt["skill"]
    for s in statements:
        recs = [r for r in records if r["child_id"] == s["child_id"] and match(r, statements) is s]
        ev = any(r["status"] == "evidence" for r in recs)
        e = s["expect"]
        c[f"expect_{e}"] += 1
        if e in ("evidence", "ask_then_evidence"):
            c[f"expect_{e}_became_evidence"] += ev
        if e == "not_evidence":
            c["not_evidence_became_evidence"] += ev
        if e == "absent":
            c["absent_found"] += any(r["status"] == "absent" for r in recs)
        if s.get("label"):
            c["statements_with_label"] += 1
    for r in records:
        c["banned_in_output"] += bool(has_banned_words(r["rationale"] + " " + r["teacher_quote"]))
    c["banned_in_output"] += sum(bool(has_banned_words(f["question_hi"])) for f in follow_ups)
    return c


def run_class(name: str, style: str, days: int, seed: int, voice: bool) -> dict:
    rng = random.Random(seed)
    k = make_class(name, 30, style, LESSON, rng)
    records: list[dict] = []
    yesterday: set[str] = set()
    notes = []
    totals = {"voice_before": Counter(), "voice_after": Counter(), "text_before": Counter()}
    usage = Usage()
    day = START
    for d in range(days):
        pic = planner.picture(k.roster, k.lesson, records, day, yesterday)
        listening = pic["listen_today"]
        statements, absent = day_statements(k, listening, FOCUS, rng)
        sents = voice_note(statements, style, usage=usage)
        text = " ".join(s["text"] for s in sents)
        transcript, asr_s = text, 0.0
        if voice:
            with tempfile.TemporaryDirectory() as tmp:
                wav = tts.speak_hi(text, Path(tmp) / "n.wav", speaker=SPEAKER[style], pace=1.05)
                t = time.time()
                transcript = asr.transcribe(wav.read_bytes(), k.roster, k.lesson)["transcript"]
                asr_s = time.time() - t
        out = claude_observations.extract(asr.sentences(transcript), k.roster, k.lesson, listening, usage=usage)
        before = score_note(statements, [dict(r) for r in out["records"]], out["follow_ups"])
        taps = answer_questions(out, statements)
        after = score_note(statements, out["records"], out["follow_ups"])
        clean = claude_observations.extract(asr.sentences(text), k.roster, k.lesson, listening, usage=usage)
        text_before = score_note(statements, clean["records"], clean["follow_ups"])
        totals["voice_before"].update(before)
        totals["voice_after"].update(after)
        totals["text_before"].update(text_before)
        totals["voice_after"]["questions_answered"] += taps.count("answered")
        totals["voice_after"]["questions_skipped"] += taps.count("skipped")
        totals["voice_after"]["questions"] += len(out["questions"])
        for r in out["records"]:
            r.update(day=day.isoformat(), rec_id=len(records) + 1, feedback=None)
            records.append(r)
        yesterday = {p["child_id"] for p in listening}
        notes.append({"day": day.isoformat(), "listening": listening, "statements": statements,
                      "note_text": text, "transcript": transcript, "asr_seconds": round(asr_s, 1),
                      "records": [{k2: r[k2] for k2 in ("name_said", "child_id", "kind", "skill_code", "item", "outcome",
                                                         "confidence", "status")} for r in out["records"]],
                      "questions": out["questions"], "problems": out["problems"]})
        with _lock:
            print(f"[{style:15}] {day} statements={len(statements)} records={len(out['records'])} "
                  f"wrong_child={after['wrong_child']} evidence={after['evidence']} ${usage.usd:.2f}", flush=True)
        day = planner.next_school_day(day)

    # Child-level: tracker statuses after the run vs the hidden truth.
    state = planner.tracker_state(records, day)
    flags = Counter()
    for (cid, skill), s in state.items():
        child = next(c for c in k.children if c.child_id == cid)
        if skill not in SKILL_REQ:
            continue
        truth = child.truly_needs_support(skill)
        if s.status == "needs support":
            flags["needs_support_flags"] += 1
            flags["needs_support_correct"] += truth
        elif s.status == "on track":
            flags["on_track_flags"] += 1
            flags["on_track_correct"] += not truth
    covered = {cid for (cid, _), s in state.items() if s.moments > 0}
    vis = sorted(k.children, key=lambda c: c.visibility)
    quiet = {c.child_id for c in vis[:10]}
    return {"class": name, "style": style, "totals": {k2: dict(v) for k2, v in totals.items()},
            "flags": dict(flags), "children_with_evidence": len(covered), "quiet_with_evidence": len(covered & quiet),
            "usd": round(usage.usd, 3), "notes": notes}


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "–"


def report(results: list[dict], days: int, voice: bool) -> str:
    T = {k: Counter() for k in ("voice_before", "voice_after", "text_before")}
    F = Counter()
    for r in results:
        for k, v in r["totals"].items():
            T[k].update(v)
        F.update(r["flags"])
    A, B, X = T["voice_after"], T["voice_before"], T["text_before"]
    n_notes = len(results) * days
    lines = [
        "# SUNO on simulated classrooms (SIMULATED, not real children or teachers)",
        "",
        f"Generated by `eval/sim/run_pipeline_sim.py`: {len(results)} simulated classes of 30 (one per teacher style: "
        f"{', '.join(r['style'] for r in results)}), {days} school days each, {n_notes} voice notes. "
        "Each note: the simulated teacher's statements → Claude voices them as speech → Sarvam text-to-speech → "
        "Sarvam speech-to-text → SUNO's real pipeline. Ground truth is known for every statement. "
        "Assumptions are listed in `eval/sim/world.py` and `eval/sim/teacher.py`.",
        "",
        "## Does SUNO credit the right child?",
        "",
        "| | After speech-to-text | Clean text (no speech errors) |",
        "|---|---|---|",
        f"| Records naming a child who was **not** talked about (wrong child) | {pct(B['wrong_child'], B['attributed'])} | {pct(X['wrong_child'], X['attributed'])} |",
        f"| Evidence records about the wrong child | {pct(B['wrong_child_evidence'], B['evidence'])} | {pct(X['wrong_child_evidence'], X['evidence'])} |",
        f"| Evidence records whose right/wrong direction matches what the child did | {pct(B['evidence_direction_ok'], B['evidence'])} | {pct(X['evidence_direction_ok'], X['evidence'])} |",
        f"| …and the exact outcome (correct / incorrect / partial) | {pct(B['evidence_exact_outcome'], B['evidence'])} | {pct(X['evidence_exact_outcome'], X['evidence'])} |",
        f"| …and the same skill | {pct(B['evidence_skill_ok'], B['evidence'])} | {pct(X['evidence_skill_ok'], X['evidence'])} |",
        "",
        "## Does it hold back what isn't evidence?",
        "",
        "| | After speech-to-text |",
        "|---|---|",
        f"| Opinions, labels and vague remarks that became evidence | {pct(B['not_evidence_became_evidence'], B['expect_not_evidence'])} |",
        f"| Evidence from a statement that was not an observation | {pct(B['evidence_from_non_observation'], B['evidence'])} |",
        f"| Labels (कमज़ोर, weak…) repeated in anything SUNO shows | {B['banned_in_output']} times, in {B['statements_with_label']} statements that used one |",
        "",
        "## How much of what she said becomes evidence?",
        "",
        "| | After speech-to-text | After the teacher's one-tap answers | Clean text |",
        "|---|---|---|---|",
        f"| Specific observations about a clearly named child | {pct(B['expect_evidence_became_evidence'], B['expect_evidence'])} | {pct(A['expect_evidence_became_evidence'], A['expect_evidence'])} | {pct(X['expect_evidence_became_evidence'], X['expect_evidence'])} |",
        f"| Specific observations where the name was unclear (shared name, unknown nickname, \"one child\") | {pct(B['expect_ask_then_evidence_became_evidence'], B['expect_ask_then_evidence'])} | {pct(A['expect_ask_then_evidence_became_evidence'], A['expect_ask_then_evidence'])} | {pct(X['expect_ask_then_evidence_became_evidence'], X['expect_ask_then_evidence'])} |",
        f"| Absences recorded | {pct(B['absent_found'], B['expect_absent'])} | | {pct(X['absent_found'], X['expect_absent'])} |",
        f"| Name questions asked / answered with one tap / skipped | {A['questions']} / {A['questions_answered']} / {A['questions_skipped']} | | |",
        "",
        "## Child-level: tracker after the run vs the hidden truth",
        "",
        f"- \"Needs support\" flags that are right: {pct(F['needs_support_correct'], F['needs_support_flags'])}",
        f"- \"On track\" flags that are right: {pct(F['on_track_correct'], F['on_track_flags'])}",
        f"- Children with at least one piece of evidence: "
        + ", ".join(f"{r['style']} {r['children_with_evidence']}/30 (quietest 10: {r['quiet_with_evidence']}/10)" for r in results),
        "",
        "## Per teacher style (after speech-to-text, before taps)",
        "",
        "| Style | Notes | Wrong-child evidence | Direction right | Opinions → evidence | Clear observations → evidence |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        b = Counter(r["totals"]["voice_before"])
        lines.append(f"| {r['style']} | {days} | {pct(b['wrong_child_evidence'], b['evidence'])} | "
                     f"{pct(b['evidence_direction_ok'], b['evidence'])} | {pct(b['not_evidence_became_evidence'], b['expect_not_evidence'])} | "
                     f"{pct(b['expect_evidence_became_evidence'], b['expect_evidence'])} |")
    lines += ["", f"Claude spend for this run: ${sum(r['usd'] for r in results):.2f}. Small samples: read percentages with their counts."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=8)
    ap.add_argument("--styles", default=",".join(STYLES))
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    styles = a.styles.split(",")
    with ThreadPoolExecutor(len(styles)) as ex:
        futs = [ex.submit(run_class, f"sim-{s}", s, a.days, a.seed + i, not a.no_voice) for i, s in enumerate(styles)]
        results = [f.result() for f in futs]
    out = ROOT / "eval" / "results"
    (out / "sim_pipeline.json").write_text(json.dumps({"label": "SIMULATED", "results": results}, ensure_ascii=False, indent=1))
    md = report(results, a.days, not a.no_voice)
    (out / "sim_pipeline.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
