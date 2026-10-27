"""Write 10 teacher-note scripts with known ground truth, for real people to read aloud.

Uses the simulation's teacher (eval/sim/teacher.py) on a SYNTHETIC class, then freezes the
roster, the statements (ground truth) and the note text into eval/real_notes/scripts.json.
Run once:  uv run python eval/real_notes/make_scripts.py   (about $0.10 of Claude credit)
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.sim.teacher import day_statements, voice_note  # noqa: E402
from eval.sim.world import make_class  # noqa: E402

LESSON = json.loads((ROOT / "samples/synthetic/demo_class.json").read_text())["lesson"]
FOCUS = ["hi.matras", "hi.blend_no_matra", "hi.words_with_matras", "hi.sentence", "hi.comprehension",
         "math.number_recognition", "math.place_value", "math.addition"]
STYLES = ["precise", "brief", "impressionistic", "hinglish", "precise", "brief", "impressionistic", "hinglish", "brief", "precise"]


def main() -> None:
    rng = random.Random(2026)
    k = make_class("real-notes", 30, "brief", LESSON, rng)
    notes = []
    for i, style in enumerate(STYLES, 1):
        k.style = style
        statements, _ = day_statements(k, [], FOCUS, rng)
        sents = voice_note(statements, style)
        notes.append({"id": f"note{i:02d}", "style": style, "text": " ".join(s["text"] for s in sents),
                      "statements": statements})
        print(f"note{i:02d} [{style}] {notes[-1]['text'][:90]}…")
    out = {"label": "SYNTHETIC scripts (fictional class) for real people to read aloud. Ground truth per statement.",
           "roster": k.roster, "notes": notes}
    (ROOT / "eval/real_notes/scripts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
