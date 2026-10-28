"""SIMULATED classrooms for testing SUNO without real children. Every number this produces is
labelled SIMULATED; the assumptions are listed here so a reader can disagree with them.

A class has children with a hidden ("true") level in Hindi reading and in maths. Each school day
a simulated teacher notices some children read or answer, sees what they actually did (drawn
from their true level), and later says it in her own style, including the messy things real
teachers say: opinions, labels, a shared name without a roll number, a nickname the roster
doesn't know, "one child", habits instead of today.

ASSUMPTIONS (change them and re-run):
- Reading levels in a Grade 2 government class (loosely after ASER's Std II-III picture):
  beginner 10%, letters 30%, simple words 25%, words with vowel signs 15%, sentences 12%, story 8%.
- Maths levels: none 20%, reads 2-digit numbers 35%, tens-and-ones 30%, add/subtract 15%.
- English: 35% of children read simple English words.
- A child at or above a skill's level answers right 90% of the time; one level below, 35%;
  further below, 8%.
- Teacher attention: who she notices on her own is weighted by how visible a child is
  (front bench, talkative): weight = visibility ** 1.5, visibility ~ lognormal(0, 0.6).

ASER-CALIBRATED classes (make_class(..., reading_dist=aser_reading_dist(state), absence=...)):
- Reading levels come from ASER 2024's published Std II table for that state (eval/sim/aser2024.json).
  ASER has one "word" level; we split it half "simple words", half "words with vowel signs"
  (ASSUMPTION). ASER's paragraph level is our "sentences"; its story level is our "story".
  The table covers all children, government and private; government-school children read lower.
- Absence: each child has her own absence rate, Beta-distributed around the state's published
  absence (1 - attendance) with concentration 4 (ASSUMPTION), so some children are absent often.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

READING_LEVELS = ["beginner", "letters", "simple words", "matra words", "sentences", "story"]
READING_DIST = [0.10, 0.30, 0.25, 0.15, 0.12, 0.08]
MATHS_LEVELS = ["none", "numbers", "tens-ones", "operations"]
MATHS_DIST = [0.20, 0.35, 0.30, 0.15]

# skill -> (area, level needed)
SKILL_REQ = {
    "hi.letters": ("hindi", 1), "hi.matras": ("hindi", 2), "hi.blend_no_matra": ("hindi", 2),
    "hi.words_with_matras": ("hindi", 3), "hi.sentence": ("hindi", 4), "hi.comprehension": ("hindi", 5),
    "math.number_recognition": ("maths", 1), "math.place_value": ("maths", 2),
    "math.addition": ("maths", 2), "math.subtraction": ("maths", 3),
    "hi.conjuncts": ("hindi", 4), "en.words": ("english", 1),
}
P_ENGLISH_WORDS = 0.35   # share of children who can read simple English words (ASSUMPTION)
P_AT, P_ONE_BELOW, P_FAR_BELOW = 0.90, 0.35, 0.08
ASER = json.loads((Path(__file__).parent / "aser2024.json").read_text())
ABSENCE_CONCENTRATION = 4      # ASSUMPTION: how unevenly absence is spread across children


def aser_reading_dist(state: str) -> list[float]:
    """ASER 2024 Std II levels (beginner, letter, word, paragraph, story) -> our six reading levels."""
    b, l, w, para, story = ASER["reading_std2"][state]
    return [b, l, w / 2, w / 2, para, story]


def aser_absence(state: str) -> float:
    return 1 - ASER["attendance_primary"][state] / 100

NAME_POOL = [
    ("आरव", "Aarav"), ("सिमरन", "Simran"), ("रवि", "Ravi"), ("पिंकी", "Pinki"), ("अंजलि", "Anjali"),
    ("अमन", "Aman"), ("सुरेश", "Suresh"), ("सोनू", "Sonu"), ("अर्जुन", "Arjun"), ("रीना", "Reena"),
    ("फ़ातिमा", "Fatima"), ("प्रिया", "Priya"), ("करण", "Karan"), ("मोहन", "Mohan"), ("काजल", "Kajal"),
    ("नेहा", "Neha"), ("विकास", "Vikas"), ("पूजा", "Pooja"), ("दीपक", "Deepak"), ("गीता", "Geeta"),
    ("राहुल", "Rahul"), ("सलमा", "Salma"), ("आशा", "Asha"), ("मनीष", "Manish"), ("इमरान", "Imran"),
    ("रानी", "Rani"), ("गोलू", "Golu"), ("सीमा", "Seema"), ("अजय", "Ajay"), ("सना", "Sana"),
    ("कृष्णा", "Krishna"), ("लक्ष्मी", "Lakshmi"), ("रोहित", "Rohit"), ("सपना", "Sapna"), ("अनिल", "Anil"),
    ("ज्योति", "Jyoti"), ("साहिल", "Sahil"), ("मुस्कान", "Muskan"), ("विशाल", "Vishal"), ("खुशी", "Khushi"),
    ("राजेश", "Rajesh"), ("नीतू", "Neetu"), ("आकाश", "Akash"), ("रुबीना", "Rubina"), ("धर्मेंद्र", "Dharmendra"),
]
NICKNAMES = [("गुड्डू", "Guddu"), ("बबलू", "Bablu"), ("छोटू", "Chhotu"), ("मुन्नी", "Munni"), ("पप्पू", "Pappu")]


@dataclass
class Child:
    child_id: str
    first_name: str
    latin: str
    roll_no: int
    reading: int
    maths: int
    english: int
    visibility: float
    reversal: bool                 # tends to reverse two-digit numbers
    home_language_gap: bool        # understands better in the home language
    roster_nickname: str | None    # nickname written in the roster
    spoken_nickname: str | None    # nickname the teacher uses that the roster does NOT know
    p_absent: float | None = None  # her own absence rate (ASER-calibrated classes); None = class default

    def p_correct(self, skill: str) -> float:
        area, need = SKILL_REQ[skill]
        lvl = {"hindi": self.reading, "maths": self.maths, "english": self.english}[area]
        if lvl >= need:
            return P_AT
        return P_ONE_BELOW if lvl == need - 1 else P_FAR_BELOW

    def truly_needs_support(self, skill: str) -> bool:
        return self.p_correct(skill) < 0.5


@dataclass
class Klass:
    name: str
    children: list[Child]
    style: str
    lesson: dict = field(default_factory=dict)

    @property
    def roster(self) -> list[dict]:
        return [{"child_id": c.child_id, "first_name": c.first_name, "roll_no": c.roll_no,
                 "aliases": [c.latin] + ([c.roster_nickname] if c.roster_nickname else [])} for c in self.children]


def make_class(name: str, size: int, style: str, lesson: dict, rng: random.Random,
               reading_dist: list[float] | None = None, absence: float | None = None) -> Klass:
    pool = rng.sample(NAME_POOL, size - 2)
    # Two shared first names, as in most real classes of 30+.
    dup = rng.sample(pool, 2)
    names = pool + dup
    rng.shuffle(names)
    nick_pool = rng.sample(NICKNAMES, 3)
    children = []
    for i, (deva, latin) in enumerate(names, 1):
        children.append(Child(
            child_id=f"c{i:02d}", first_name=deva, latin=latin, roll_no=i,
            reading=rng.choices(range(6), reading_dist or READING_DIST)[0], maths=rng.choices(range(4), MATHS_DIST)[0],
            english=int(rng.random() < P_ENGLISH_WORDS),
            visibility=rng.lognormvariate(0, 0.6), reversal=rng.random() < 0.25,
            home_language_gap=rng.random() < 0.15, roster_nickname=None, spoken_nickname=None,
            p_absent=None if absence is None else rng.betavariate(absence * ABSENCE_CONCENTRATION, (1 - absence) * ABSENCE_CONCENTRATION)))
    # One child has a nickname in the roster; one is called by a nickname the roster lacks.
    a, b = rng.sample(children, 2)
    a.roster_nickname = nick_pool[0][0]
    b.spoken_nickname = nick_pool[1][0]
    return Klass(name=name, children=children, style=style, lesson=lesson)


def response(child: Child, skill: str, rng: random.Random) -> tuple[str, str]:
    """What the child actually did: (outcome, error_type)."""
    p = child.p_correct(skill)
    r = rng.random()
    if r < p:
        return "correct", "none"
    if r < p + (1 - p) * 0.25:
        outcome = "partial"
    else:
        outcome = "incorrect"
    if skill == "math.number_recognition":
        err = "number_reversal" if child.reversal or rng.random() < 0.3 else "other"
    elif skill == "math.place_value":
        err = "place_value_confusion"
    elif skill in ("math.addition", "math.subtraction"):
        err = "counting_error"
    elif skill == "hi.blend_no_matra":
        err = rng.choice(["segments_without_blending"] * 3 + ["letter_confusion"])
    elif skill == "hi.matras":
        err = rng.choice(["matra_confused", "matra_omitted"])
    elif skill == "hi.words_with_matras":
        err = rng.choice(["matra_omitted"] * 2 + ["matra_confused", "letter_by_letter"])
    elif skill == "hi.comprehension":
        err = "meaning_not_understood"
    elif skill == "hi.sentence":
        err = rng.choice(["letter_by_letter", "guesses_from_first_letter"])
    else:
        err = "letter_confusion"
    return outcome, err
