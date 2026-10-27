# Design-change log

This file is the evidence for the Build deck's **"User inputs and testing"** slide. The organisers score real user contact, and the changes it caused. Add a row whenever a teacher, child session, parent, mentor or organiser changes what we build. Newest first.

## Input from users, mentors and organisers
| Date | Source | What they said or did | What we changed | Where it shows |
| --- | --- | --- | --- | --- |
| 20 Oct 2026 | Technical mentor (call) | SUNO rests on one untested belief: that each answer can be mapped to the right child. Test that alone before building any app ("if that hypothesis doesn't hold, the entire thing collapses"). Suggested a home test: 2–3 people, a phone some distance away, check the mapping. | Stopped app work. Built feasibility test F1 (voice matching on real child voices from ASER, in a simulated classroom) and a scorer for the home test. F1 result: voice matching cannot name the child (Decision 17); attribution moves to the teacher's tap on planned call-ons. | `docs/feasibility.md`, `eval/feasibility/` |
| 20 Oct 2026 | Technical mentor (call) | Teachers often point ("haan beta, tum batao") instead of naming, and a class can have several children with the same name; name calls alone can't say who answered. | Name calls become one signal, never the only one. Roster entries carry a roll number so same-name children stay distinct. | Decision 18 |
| 20 Oct 2026 | Technical mentor (call) | Speech-to-text (Sarvam or any other) tells you *what* was said, not *who* said it. It is a different problem. | Split the pipeline into two separate questions, each tested on its own: who answered (F1) and was it right (F2). | `docs/feasibility.md` |
| 20 Oct 2026 | Technical mentor (call) | Recording all day is impractical on a ₹8–10k phone: battery, heat, and the teacher can't take calls or use other apps. | SUNO records only during one fixed reading slot (30–45 min), started and stopped by the teacher. | Decision 16 |
| 20 Oct 2026 | Technical mentor (call) | Asked how the 0.75 confidence gate is set. | Corrected our answer on the call: Claude does not set it. Code computes confidence from measured signals; the gate is the lowest value that keeps precision at or above the target on labelled data, and F1 now picks it that way. | `eval/feasibility/voice_id.py`; deck |
| 20 Oct 2026 | Technical mentor (call) | Understood that the whole audio would go to Claude Opus to work out who spoke. | Corrected: the Claude API takes text and images, not audio. Speech models handle voices; Claude reasons over transcripts and who-spoke labels. The deck must say this plainly. | Architecture slide |
| ~16 Oct 2026 | Organisers (Top 30 WhatsApp group) | Proxy testing with 4–5 children of the same age is acceptable, but real users and real settings score higher. For niche users (CRP/BEO/DEO), show mentor input and how it changed the design. | Added 3 proxy sessions with children and 2 teacher test rounds to the plan; started this log | Build plan; testing slide |

## Internal design decisions
Mirrors HANDOFF.md, "Design decisions since the Ideate deck". Update a row's status when a mentor or a test confirms or kills it.

| # | Decision | Why | Date | Status |
| --- | --- | --- | --- | --- |
| 1 | The teacher wears the phone (lanyard or pocket); the desk is only a fallback | Sound drops 6 dB per doubling of distance: ~60 dB at 1 m becomes ~44 dB at 6 m, below classroom noise | 20 Oct | Dropped (see 20) |
| 2 | Evidence moments come to the mic: call-ons happen near the teacher | Clear audio where it matters; this is ordinary teaching | 20 Oct | Dropped (see 20) |
| 3 | Optional one-tap confirm of which child is reading, for planned call-ons | Removes attribution doubt | 20 Oct | Proposed; now the main attribution signal (see 17) |
| 4 | Precision over recall; publish the measured operating range | A wrong label is the worst failure | 20 Oct | Decided |
| 5 | No full speaker separation: just teacher, one voice, or many | Classroom separation error is 17–45% (arXiv 2505.10879) | 15 Oct | Moot (see 20): only the teacher's own voice is transcribed |
| 6 | Check answers against the expected word, not by open transcription | Child Hindi ASR is weak | 15 Oct | Moot (see 20): no child speech is transcribed; items are checked against the teacher's words |
| 7 | ASR: Sarvam Saaras or IndicConformer, not Whisper | Vaani benchmark: 19.5% / 20.0% vs 32.8% error | 15 Oct | Decided: Sarvam saaras:v4 on the teacher's note |
| 8 | Cadence: every child heard within a week; first conclusions in ~2 weeks | Realistic count of clear moments | 20 Oct | Decided |
| 9 | MVP: Hindi, Grade 2, reading (letters → vowel marks → blending → words); English words second | 12 days, 2 people | 15 Oct | Proposed |
| 10 | Moved to roadmap: language-or-concept flag, numeracy, on-device processing, mentor view | Scope | 15 Oct | Decided |
| 11 | Judges' path runs live; Message Batches for bulk evaluation only | Batches can take hours | 15 Oct | Decided |
| 12 | The school or state owns the data; SUNO is its processor | The DPDP exemption covers institutions, not vendors | 15 Oct | Decided |
| 13 | Cost corrected from ≈₹110 to ≈₹210 per child per year (adds Sarvam ASR) | The deck counted Claude only | 15 Oct | Decided |
| 14 | Deck wording: "worn by the teacher" and "no tests, no extra time" | Matches rows 1–2 | 20 Oct | Proposed |
| 15 | Real-user testing: 3 proxy sessions plus 3 teachers × 2 rounds | Organisers' guidance | 16 Oct | Decided |
| 16 | Record only during one fixed reading slot (30–45 min) that the teacher starts and stops; never all day | Battery, heat and blocked calls on a ₹8–10k phone (technical mentor) | 20 Oct | Superseded by 20: nothing records the classroom |
| 17 | Who answered comes from the teacher's one tap on a planned call-on list (4–6 children a day), or a name she says that matches exactly one child; never from voice matching | F1: voice matching is right for at most 56% of one-word answers even spoken into the phone (class of 5), 13% at 1 m in a class of 35, and never reaches the 90% precision needed to name a child | 20 Oct | Voice matching: Dropped. Tap list: Superseded by 20 (no in-class attribution is needed) |
| 18 | Name calls are one signal, never the only one; the roster carries roll numbers so same-name children stay distinct | Teachers point instead of naming; duplicate names are common (technical mentor) | 20 Oct | Decided |
| 19 | Claude model: `claude-opus-5-5` (Opus 5.5) instead of `claude-opus-5` | Newer, and 20% cheaper ($4 / $20 per million tokens vs $5 / $25); same structured outputs | 20 Oct | Decided |
| 20 | **SUNO listens to the teacher, not the classroom.** After the reading period she speaks a ~60-second voice note in her own words; Claude turns it into per-child observations; code checks and scores them; the morning brief and a 5-child listening list follow. No classroom recording, no child's voice. | The teacher already hears every stumble; what is lost is memory (Ideate deck, problem slide). Classroom audio failed on five counts: F1 (voice can't tell which child answered), distance (back benches beyond ~1 m), phone heat and battery over a whole period, start/stop per period and per teacher, and consent for recording children (DPDP §9; UP and Rajasthan rules on recording in schools) | 27 Oct | Decided (Tushar) |
| 21 | Observations count, opinions don't. Code scores how checkable each statement is (who × specific item × concrete mistake × seen today); "रवि अच्छा है" or a label can never pass the gate and becomes "listen to Ravi read X tomorrow" | Teachers' own picture of weakest readers is often wrong (~40% in Wadmare et al. 2022, `docs/strategy-review.md`); the planner and the confirm list turn impressions into checks | 27 Oct | Decided |
| 22 | The child is resolved by code from the roster (phonetic matching across Devanagari and Latin spellings, roll numbers in digits or Hindi words) and must agree with Claude; a mismatch or a shared name becomes a one-tap question to the teacher | A wrong child is the worst failure; Claude proposes, code verifies | 27 Oct | Decided |
| 23 | Speech-to-text `keyterms` off by default, and a code check: "X को X पढ़ा" (same word on both sides) can't be "correct", it becomes "check tomorrow" | Sarvam returned "किताब को किताब" and "पानी को पानी" when the note said "कताब" / "पनी": it erased the child's misreading, and keyterms made it worse (synthetic sample notes, 27 Oct) | 27 Oct | Decided |
| 24 | Web app (installable PWA, offline recording queue) instead of a native Android app; SQLite instead of Postgres | 4 days left; judges test a hosted link; a PWA records offline and installs on a ₹8k Android phone | 27 Oct | Decided |
| 25 | Maths (number reading, tens and ones, addition, subtraction) and English words join the skill ladder | Teacher speech makes them cheap: no child speech recognition needed. Numeracy is the organisers' own example | 27 Oct | Decided |
| 26 | The language-or-concept flag returns from the roadmap: when the teacher says a child understood once it was explained in the home language, SUNO flags it on the child and in the brief | Claude reads it straight from her words; it was cut only because classroom audio couldn't support it | 27 Oct | Decided |

## Evidence for the Build deck
- [x] Technical mentor call (20 Oct): inputs, and what changed (6 rows above; F1 feasibility test, `docs/feasibility.md`)
- [x] F1: voice matching on real child voices, simulated classroom (`eval/results/f1_voice_id.md`, chart `f1_voice_id.png`): it cannot name the child
- [ ] F2: right vs wrong on real child readings (`eval/results/f2_answer_check.md`), needs the Sarvam key
- [ ] F3: attribution on the mentor's hard cases, synthetic (`eval/results/f3_claude_attribution.md`), needs the Anthropic key
- [ ] Home distance test: accuracy by distance, desk vs worn phone
- [ ] ASER dataset: answer-checker accuracy on real child speech
- [ ] Proxy sessions 1–3: attribution and answer accuracy by distance, and the teacher's reaction to her own brief
- [ ] Teacher tests, round 1 and round 2: problems found, fixes made, before and after
- [ ] Parents: questions and concerns raised during consent
- [ ] Education mentor call (28 Oct): inputs, and what changed
