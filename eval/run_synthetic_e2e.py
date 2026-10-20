"""End-to-end run of SUNO's reasoning core on the SYNTHETIC lessons.

transcript + taps -> Claude 1 (moments) -> code checks -> Claude 2 (evidence)
-> confidence + gate (code) -> tracker, Silence Ledger, planner (code)
-> Claude 3 (brief) -> brief checks (code) -> optional Sarvam voice.

    uv run python eval/run_synthetic_e2e.py [--speak]

Needs ANTHROPIC_API_KEY (and SARVAM_API_KEY for --speak). Writes eval/results/e2e_synthetic/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.pipeline.claude_brief import write_brief  # noqa: E402
from server.pipeline.claude_client import MODEL, Usage  # noqa: E402
from server.pipeline.claude_evidence import extract_evidence  # noqa: E402
from server.pipeline.claude_moments import rebuild_moments  # noqa: E402
from server.pipeline.tracker import Evidence, plan_call_ons, silence_ledger, track  # noqa: E402

OUT = ROOT / "eval/results/e2e_synthetic"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speak", action="store_true")
    args = ap.parse_args()
    data = json.loads((ROOT / "samples/synthetic/attribution_lessons.json").read_text())
    activities = json.loads((ROOT / "samples/activities.v0.json").read_text())["activities"]
    roster = data["roster"]
    ids = [c["child_id"] for c in roster]
    usage = Usage()
    days = [date(2026, 10, 19) + timedelta(days=i) for i in range(len(data["lessons"]))]
    claims, later, heard, log = [], [], [], []
    for day, L in zip(days, data["lessons"]):
        _, moments, problems = rebuild_moments(roster, L["lesson"], L["segments"], L["taps"], usage=usage)
        c, w, p2 = extract_evidence(moments, L["segments"], usage=usage)
        claims += [x | {"day": day.isoformat()} for x in c]
        later += [x | {"day": day.isoformat()} for x in w]
        heard += [(m["addressee_child_id"], day) for m in moments
                  if m["addressee_child_id"] and m["response_type"] == "individual" and m["response_seg_ids"]]
        log.append({"lesson": L["lesson"]["lesson_id"], "moments": len(moments), "claims": len(c),
                    "check_tomorrow": len(w), "problems": [list(p) for p in problems + p2]})
    today = days[-1] + timedelta(days=1)
    state = track([Evidence(x["child_id"], x["skill_code"], x["outcome"], x["confidence"],
                            date.fromisoformat(x["day"])) for x in claims], today)
    skills = sorted({x["skill_code"] for x in claims}) or ["hi.words_with_matras"]
    call_on = plan_call_ons(ids, state, skills, called_yesterday=set(), k=5)
    silent = silence_ledger(ids, heard, days)
    facts = {
        "tracker": [{"child_id": c, "skill": s, "status": st.status, "p": round(st.p, 2), "moments": st.moments,
                     "days": len(st.days)} for (c, s), st in sorted(state.items())],
        "evidence_summary": [{k: x[k] for k in ("child_id", "skill_code", "item", "heard", "outcome", "error_type", "day")}
                             for x in claims],
        "check_tomorrow": [{"child_id": x["child_id"], "item": x["item"], "why": x["rationale"]} for x in later],
        "call_on": call_on, "silent": silent,
    }
    brief = write_brief(roster, facts, activities, usage=usage)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_text(json.dumps({"claims": claims, "check_tomorrow": later, "log": log},
                                                  ensure_ascii=False, indent=1, default=str))
    (OUT / "brief.json").write_text(json.dumps({"label": "SYNTHETIC lessons", "model": MODEL, "facts": facts,
                                                "brief": brief}, ensure_ascii=False, indent=1))
    (OUT / "brief_hi.txt").write_text(brief["text_hi"])
    print(json.dumps(log, ensure_ascii=False, indent=1))
    print("\n" + brief["text_hi"])
    print(f"\nTokens: {usage.input_tokens} in, {usage.output_tokens} out, {usage.cache_read_tokens} cache reads; "
          f"cost ≈ ${usage.usd:.3f}")
    if args.speak:
        from server.pipeline.tts import speak_hi
        print("voice:", speak_hi(brief["text_hi"], ROOT / ".cache/brief_synthetic.wav"))


if __name__ == "__main__":
    main()
