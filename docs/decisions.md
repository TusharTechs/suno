# Design-change log

This file is the evidence for the Build deck's **"User inputs and testing"** slide. The organisers score real user contact, and the changes it caused. Add a row whenever a teacher, child session, parent, mentor or organiser changes what we build. Newest first.

## Input from users, mentors and organisers
| Date | Source | What they said or did | What we changed | Where it shows |
| --- | --- | --- | --- | --- |
| ~16 Oct 2026 | Organisers (Top 30 WhatsApp group) | Proxy testing with 4–5 children of the same age is acceptable, but real users and real settings score higher. For niche users (CRP/BEO/DEO), show mentor input and how it changed the design. | Added 3 proxy sessions with children and 2 teacher test rounds to the plan; started this log | Build plan; testing slide |

## Internal design decisions
Mirrors HANDOFF.md, "Design decisions since the Ideate deck". Update a row's status when a mentor or a test confirms or kills it.

| # | Decision | Why | Date | Status |
| --- | --- | --- | --- | --- |
| 1 | The teacher wears the phone (lanyard or pocket); the desk is only a fallback | Sound drops 6 dB per doubling of distance: ~60 dB at 1 m becomes ~44 dB at 6 m, below classroom noise | 20 Oct | Proposed |
| 2 | Evidence moments come to the mic: call-ons happen near the teacher | Clear audio where it matters; this is ordinary teaching | 20 Oct | Proposed |
| 3 | Optional one-tap confirm of which child is reading, for planned call-ons | Removes attribution doubt | 20 Oct | Proposed |
| 4 | Precision over recall; publish the measured operating range | A wrong label is the worst failure | 20 Oct | Decided |
| 5 | No full speaker separation: just teacher, one voice, or many | Classroom separation error is 17–45% (arXiv 2505.10879) | 15 Oct | Proposed |
| 6 | Check answers against the expected word, not by open transcription | Child Hindi ASR is weak | 15 Oct | Proposed |
| 7 | ASR: Sarvam Saaras or IndicConformer, not Whisper | Vaani benchmark: 19.5% / 20.0% vs 32.8% error | 15 Oct | Proposed |
| 8 | Cadence: every child heard within a week; first conclusions in ~2 weeks | Realistic count of clear moments | 20 Oct | Decided |
| 9 | MVP: Hindi, Grade 2, reading (letters → vowel marks → blending → words); English words second | 12 days, 2 people | 15 Oct | Proposed |
| 10 | Moved to roadmap: language-or-concept flag, numeracy, on-device processing, mentor view | Scope | 15 Oct | Decided |
| 11 | Judges' path runs live; Message Batches for bulk evaluation only | Batches can take hours | 15 Oct | Decided |
| 12 | The school or state owns the data; SUNO is its processor | The DPDP exemption covers institutions, not vendors | 15 Oct | Decided |
| 13 | Cost corrected from ≈₹110 to ≈₹210 per child per year (adds Sarvam ASR) | The deck counted Claude only | 15 Oct | Decided |
| 14 | Deck wording: "worn by the teacher" and "no tests, no extra time" | Matches rows 1–2 | 20 Oct | Proposed |
| 15 | Real-user testing: 3 proxy sessions plus 3 teachers × 2 rounds | Organisers' guidance | 16 Oct | Decided |

## Evidence for the Build deck
- [ ] Technical mentor call (20 Oct): inputs, and what changed
- [ ] Home distance test: accuracy by distance, desk vs worn phone
- [ ] ASER dataset: answer-checker accuracy on real child speech
- [ ] Proxy sessions 1–3: attribution and answer accuracy by distance, and the teacher's reaction to her own brief
- [ ] Teacher tests, round 1 and round 2: problems found, fixes made, before and after
- [ ] Parents: questions and concerns raised during consent
- [ ] Education mentor call (28 Oct): inputs, and what changed
