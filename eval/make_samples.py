"""Sample inputs for reviewers: SYNTHETIC teacher voice notes about the demo class, voiced by
Sarvam text-to-speech (bulbul:v3), so the real speech-to-text path can be tested without a
Hindi speaker. Writes samples/synthetic/sample_notes.json and samples/synthetic/audio/sample_*.mp3.
Run:  uv run python eval/make_samples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.pipeline.tts import speak_hi  # noqa: E402

LABEL = ("SYNTHETIC sample notes written by Team Sunvai about the fictional demo class, voiced by Sarvam "
         "text-to-speech (bulbul:v3). Not a real teacher, not real children.")
SAMPLES = [
    {"id": "everyday", "speaker": "ritu", "title": "रोज़ का नोट", "title_en": "An ordinary day: the listening list, a mistake, an absence",
     "text": "आज मोहन ने घर सही पढ़ा, जल्दी से। काजल ने कि को की पढ़ा, छोटी और बड़ी इ में गड़बड़ हुई। "
             "पिंकी ने कमल को क म ल पढ़ा, अभी भी जोड़ नहीं पा रही। दीपक आज नहीं आया।"},
    {"id": "hard-cases", "speaker": "kavya", "title": "मुश्किल नाम और लेबल", "title_en": "Hard cases: two Priyas, a label, a name not on the roster",
     "text": "प्रिया ने किताब को कताब पढ़ा। प्रिया, सत्ताईस नंबर वाली, ने पूरा वाक्य सही पढ़ा। "
             "सोनू तो कमज़ोर है, उसने पानी को पनी पढ़ा। राजू ने नाव सही पढ़ा। रवि अच्छा बच्चा है।"},
    {"id": "maths-language", "speaker": "aditya", "title": "गणित और घर की भाषा", "title_en": "Maths, and a child who understood in her home language",
     "text": "गोलू ने सैंतालीस सही पढ़ा, पहली बार उल्टा नहीं किया। इमरान ने तेईस और पाँच जोड़कर अट्ठाईस बताया। "
             "फ़ातिमा को कमल कहाँ खिलता है समझ नहीं आया, भोजपुरी में पूछा तो बता दिया। सलमा ने बत्तीस में तीन दहाई बताई।"},
    {"id": "hinglish", "speaker": "shubh", "title": "हिंदी-अंग्रेज़ी मिला नोट", "title_en": "Code-mixed Hindi and English, the way many teachers talk",
     "text": "Aaj Neha ने tree को सही पढ़ा, English में भी अच्छा कर रही है। Geeta ने sun को son पढ़ा। "
             "Vikas ने मटर को म ट र पढ़ा, blending अभी नहीं हो रही। Arjun absent था।"},
]


def main() -> None:
    out = []
    for s in SAMPLES:
        f = ROOT / "samples" / "synthetic" / "audio" / f"sample_{s['id']}.mp3"
        speak_hi(s["text"], f, speaker=s["speaker"], pace=1.0)
        out.append({k: s[k] for k in ("id", "title", "title_en", "text")} | {"audio": f"/samples/audio/{f.name}"})
        print("wrote", f.name, f.stat().st_size // 1024, "KB")
    (ROOT / "samples" / "synthetic" / "sample_notes.json").write_text(
        json.dumps({"label": LABEL, "notes": out}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
