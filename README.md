# SUNO सुनो

**SUNO listens to the teacher, not the classroom.** After the reading period, a Grade 1–3 government-school teacher speaks a 60-second voice note in her own words: who read what, who got stuck where, who was absent. Next morning she hears a 2-minute Hindi brief telling her who needs support with what, today's small-group activity, and which five children to listen to today, each with one word or sum from this week's lesson.

No child's voice is recorded. Nothing records the classroom. There are no tests and no data entry.

Team Sunvai's entry in the AI for Foundational Learning Hackathon (Challenge 2: Learning-Level Visibility).

## Try it

- **Hosted:** https://suno-8qoh.onrender.com. It runs on Render's free plan: after 15 idle minutes the server sleeps, and the first visit takes about a minute to wake it. Classes are kept in a free Postgres database.
- **Code:** `SUNO-DEMO`. Each login gets its own fresh copy of a **synthetic** Grade 2 class: 30 fictional children, eight school days of teacher notes already run through the pipeline, and this morning's brief.

### Test credentials (every role)

SUNO has **one role: the teacher**. There is no admin, student or parent login, and no teacher score anywhere.

| What to test | How to sign in |
|---|---|
| A class already in use (recommended) | Code **`SUNO-DEMO`**. Every sign-in gets its own fresh copy of a synthetic Grade 2 class, so reviewers can't disturb each other. |
| Setting up a new class from scratch | On the sign-in page choose **create your own class**. SUNO gives you a class code (like `K7Q2-M9XD`) that opens the class on any phone. |

### Sample inputs (all synthetic)

| # | Input | Where | What it shows |
|---|---|---|---|
| 1 | **"An ordinary day"**: a Hindi voice note | बोलिए / Note → *sample notes* | Per-child observations from her own words: a misreading (कमल as क-म-ल), a correct read, an absence |
| 2 | **"Hard cases"**: a Hindi voice note | same | Two children named Priya (one-tap question), a label (कमज़ोर, masked and never evidence), a name not on the roster, and an opinion that becomes "check tomorrow" |
| 3 | **"Maths, and home language"**: a voice note | same | Reading two-digit numbers, adding, place value (tens in 32), and a child who understood a question only in Bhojpuri, her home language |
| 4 | **"Hinglish"**: code-mixed Hindi and English | same | Names in Latin script (Neha, Geeta) resolved to the roster, an English word misread (sun as son), blending, an absence |
| 5 | **Attendance register photo** ([`register.jpg`](samples/synthetic/images/register.jpg)) | ☰ → Children → *try a sample photo* | Claude reads first names only; surnames, fathers' names and attendance marks are dropped, and nothing is stored |
| 6 | **Textbook page photo** ([`textbook.jpg`](samples/synthetic/images/textbook.jpg)) | ☰ → This week's lesson → *try a sample page* | This week's words, matras, sentences and questions, sorted by skill |

**Demo video (3 min):** https://youtu.be/GG3v7lQ212M

**Build deck:** https://suno-8qoh.onrender.com/deck (PDF in the browser) · [PowerPoint](https://suno-8qoh.onrender.com/deck.pptx)

**For reviewers:** the landing page links to **How we tested SUNO** (`/#evidence`): where each model call happens, how wrong AI output is handled, the simulation results with their limits, and running cost. **Privacy** (`/#privacy`) lists what is never stored, and lets a teacher delete her class.

**Suggested path, about 5 minutes:**
1. **आज (Today):** play the brief. It names three children who need support, with what, and today's activity. Below it are the five children to listen to today.
2. **बोलिए (Note):** record a note, type one, or open *sample notes* and send one as audio (Sarvam-voiced, synthetic). Try **"Hard cases"**: two children named Priya, a label ("कमज़ोर"), a name that isn't on the roster, and an opinion.
3. Watch what SUNO understood:
   - green cards are evidence;
   - amber cards are "listen again tomorrow";
   - red cards ask "which Priya?" and are settled with one tap.

   Open **"how SUNO decided"** to see Claude's raw output, every code check, and the confidence arithmetic.
4. **कक्षा (Class):** the child × skill grid. A cell changes only after 3+ checked observations on 2+ days. Tap a child for their evidence.
5. **Today → "अगली सुबह / next morning":** moves the demo class one school day forward and builds that morning's brief live, including your note (about 30 s).

**Use it for a real class:** on the login page, choose *create your own class*. Then:

1. **Children:** photograph your attendance register. Claude reads first names only; you check the list, and the photo is not stored.
2. **This week's words:** photograph this week's textbook page, and Claude proposes the words, sentences and questions by skill. You can also type them.
3. **Starting levels (optional):** if you have done an ASER-style check, enter each child's level (letter, word, paragraph, story). SUNO starts from there and shows progress week by week.
4. **Reminder:** set a daily reminder for when the reading period ends. It goes into your phone's own calendar; no new app.
5. **Every day:** send **one** 60-second note after the reading period. Talk about the whole class ("most children got stuck on vowel signs") and about individual children. After each note, SUNO lists the children from today's list you didn't mention, with a 10-second add-on.

Your class code (like `K7Q2-M9XD`) opens your class on any phone. Data is kept in a free Render Postgres database.

## How it works

```
Teacher's voice note (phone, offline-capable)
  → Sarvam saaras:v4 speech-to-text → numbered sentences s1, s2, …
  → Claude ①  observations: per child, skill, item, outcome, mistake type   [prompts/observations.v3.md, schemas/observations.v2.json]
  → code checks: cited sentences exist; quote and item really are in her words; the child is resolved
    from the roster by code (phonetic names, roll numbers) and must agree with Claude; labels masked;
    "किताब को किताब पढ़ा" (speech-to-text erasing the misreading) can't be "correct"
  → code confidence (who × how specific × how concrete × how recent); gate 0.75
       below the gate, and every opinion → "listen again tomorrow", never a label
  → ladder (code, no AI): for each child, a probability for each level of the Hindi-reading and maths
    ladders (ASER/TaRL levels), updated by Bayes' rule; one observation informs several skills, and
    the described mistake counts ("क-म-ल" means the letters are known). A child is named only after
    ≥3 observations over ≥2 days; "needs support" = the lowest rung not yet reached (TaRL groups)
  → listening plan (code): the 5 children and items that would tell SUNO the most, confirm-first,
    quiet children included; two items each (one at the likely level, one a rung away)
  → Silence Ledger (code)
  → Claude ②  words the brief from code-decided facts                    [prompts/brief.v4.md, schemas/brief.v3.json]
  → code checks: no unbacked "needs support", exact listening list and ledger, activity fits the skill, banned words
       fail twice → the app shows the code facts without prose (fail closed)
  → Sarvam bulbul:v3 Hindi voice
```

| Layer | What | Where |
| --- | --- | --- |
| Input | Teacher's voice note (or typed note) | `web/app.js` (MediaRecorder, offline queue in IndexedDB) |
| Processing | Speech-to-text; sentences; Claude ① | `server/pipeline/asr.py`, `claude_observations.py` |
| Guardrails | Grounding, roster resolution, item check, labels, erased-misreading check, computed confidence | `server/pipeline/guardrails.py`, `names.py`, `confidence.py` |
| Decisions | Ladder levels, Silence Ledger, listening plan | `server/pipeline/ladder.py`, `planner.py` |
| Setup | Roster from a photo of the attendance register (Claude ③, vision), checked by code and the teacher | `server/pipeline/roster_photo.py` |
| Output | Claude ② brief, checked; Hindi voice | `server/pipeline/brief.py`, `tts.py` |
| Teacher feedback | ✓/✗ on every observation (✗ removes it from the tracker); one-tap name questions | `server/api.py` |

**Claude** (`claude-opus-5-5`, adaptive thinking, JSON-schema structured outputs, explicit effort, prompt-cached roster and lesson, server-side refusal fallback) makes two calls: reading the note, and wording the brief. **Code computes every confidence, decides every fact, and checks everything Claude returns.**

### Tested in simulation, because real classroom evidence wasn't possible in time

**SIMULATED**, not real children or teachers. Every number comes from a script; the assumptions are written in `eval/sim/`.

- **The pipeline on simulated classrooms** (`eval/results/sim_pipeline.md`): 32 voice notes from simulated teachers in 4 styles (precise, brief, impressionistic, Hinglish), including shared names, unknown nicknames, labels and opinions. Each was voiced by Sarvam text-to-speech and transcribed by Sarvam speech-to-text. Results:
  - **0 of 101** evidence records were about the wrong child;
  - **101 of 101** had the right right/wrong direction;
  - **0 of 42** opinions, labels or vague remarks became evidence;
  - labels were never repeated;
  - **17 of 19** unclear names were resolved with one tap (none misassigned);
  - **89%** of clear, specific observations became evidence after speech-to-text (96% on clean text). The rest were held back as "check tomorrow", never wrong: mostly habit remarks and the impressionistic teacher.
- **A 12-week term, 200 times over** (`eval/results/sim_term.md`), with SUNO's real tracker and planner and the error rates above (floored at 3/n). Compared with a *perfect diary* of what the teacher naturally notices, SUNO's listening list (followed 80% of the time):
  - hears the quietest third of the class far sooner: **93% vs 41%** by week 2;
  - finds **50% vs 26%** of the children who need support in Hindi reading by week 8;
  - finds **36% vs 4%** of the quiet children's gaps;
  - keeps precision at about 98%.
- **The same term in classrooms built from published data** (`eval/results/sim_aser.md`, 200 runs per state). Each class's reading levels follow ASER 2024's Std II table for India, Uttar Pradesh, Bihar, Madhya Pradesh or Rajasthan. Absence follows each state's attendance in government primary schools (59–76% present), and some children are absent far more than others. The children are still simulated. Against the same perfect diary, SUNO's list (followed 80%):
  - hears the quietest third by week 2 in **72–87% vs 39–41%** of cases. It is lowest in Madhya Pradesh and Bihar, where about 40% of children are absent on a given day;
  - finds **51–59% vs 31–37%** of the children who need support by week 8;
  - keeps precision of "needs support" at about **99%** in every state.
  - Two assumptions are stated in `eval/sim/aser2024.json` and `world.py`: ASER's single "word" level is split in two, and the table covers government and private schools together.
- **The simulation changed the design.** The first planner made detection *worse*: it spread a teacher's few observations too thin. That led to the ladder model and the two-item mini-ladder (`docs/decisions.md`).
- **Honest limits:**
  - At about 5 children a day, a struggling child is flagged with confidence after about 6 weeks.
  - The simulated teacher speaks clean, synthetic Hindi.
  - Real teachers' speech, habits and judgement are untested until classroom testing in November.

```bash
uv run python eval/sim/run_pipeline_sim.py --days 8    # Stage A, about $3 of Claude credit
uv run python eval/sim/run_term_sim.py --runs 200      # Stage B, no API calls
uv run python eval/sim/run_aser_sim.py --runs 200      # Stage B in ASER 2024-calibrated classes, no API calls
```

### Running cost

About **₹17.6 per teacher per school day** (Claude and Sarvam), about **₹117 per child per year**, computed by `eval/cost.py` from logged API usage and Sarvam's published prices (`eval/results/cost.md`). A leaner configuration of the same design is estimated at about half that.

### Real-speech test

One real speaker read 5 scripted notes (a fictional class) into an ordinary phone, each in three settings: a quiet room, a fan on full, and classroom noise playing. That's 15 recordings, run through Sarvam speech-to-text and SUNO's real pipeline (`eval/results/real_notes.md`). At a 15–22% speech-to-text word error rate:

- **0 of 56** evidence records were about the wrong child, and **56 of 56** had the right right/wrong direction;
- **0 of 21** opinions or vague remarks became evidence;
- **98%** of specific observations were captured;
- **15 of 15** absences were recorded.

The test changed two things (decisions 32–33):
- evidence now needs a specific word or sum;
- roll numbers as people say them ("रोल तेरा" = 13) are understood.

**Limit:** one speaker, a man; most primary teachers are women. The scripts and the scorer are in `docs/real-notes-protocol.md` and `eval/real_notes/`.

### Offline and low network

- **Works offline:** recording (saved on the phone and sent automatically when the network returns), the last brief and its audio, the class grid and child pages as last loaded.
- **Needs a network:** sending a note (about 100–250 KB a minute) and fetching the next brief (a few KB of text plus the audio).

### Privacy

- No child's voice is ever recorded.
- The teacher's voice note is transcribed and then dropped; no audio is stored.
- Children are first names and roll numbers.
- There is no teacher score or teacher-performance field anywhere.
- Labels such as "weak" or कमज़ोर are masked and never repeated.
- Per-class sandboxes: one class cannot read another's data (`tests/test_api_flow.py`).

## Run locally

```bash
brew install uv ffmpeg              # Python 3.12 via uv
cp .env.example .env                # add ANTHROPIC_API_KEY and SARVAM_API_KEY
uv sync
uv run uvicorn server.api:app --reload --port 8765
# open http://localhost:8765 and sign in with SUNO-DEMO
uv run python -m pytest             # guardrail, planner, brief and API tests; no keys needed
```

Docker: `docker build -t suno . && docker run -p 8000:8000 --env-file .env suno`.

Deploy: `render.yaml` is a Render Blueprint (free plan, Singapore, Docker); you enter the two API keys in the Render dashboard.

**External AI services.** These are every model the app calls. Keys go in `.env` locally, or in Render's environment settings when hosted; they are never committed.

| Service | Model | What it does | Key |
|---|---|---|---|
| Anthropic Claude | `claude-opus-5-5` | ① reads the teacher's note into per-child observations; ② words the morning brief; reads the register photo and the textbook page photo (vision) | `ANTHROPIC_API_KEY` |
| Sarvam AI | `saaras:v4` | Speech-to-text for the teacher's note (Hindi, code-mixed) | `SARVAM_API_KEY` |
| Sarvam AI | `bulbul:v3` | Text-to-speech for the Hindi morning brief | `SARVAM_API_KEY` |

The tests and the term simulations need no keys.

**Regenerate the synthetic demo data** (costs about $0.40 of Claude credit):

```bash
uv run python eval/seed_demo.py
uv run python eval/make_samples.py
```

## Repo map

| Path | What |
| --- | --- |
| `server/api.py`, `jobs.py`, `store.py`, `demo.py` | Web API, background jobs, storage (SQLite locally, Postgres hosted), per-login demo sandboxes |
| `server/pipeline/` | One module per stage: `asr`, `claude_observations`, `names`, `guardrails`, `confidence`, `ladder`, `planner`, `brief`, `tts`, `roster_photo`, `lesson_photo` |
| `prompts/`, `schemas/` | Versioned prompts and JSON schemas for every Claude call |
| `config/` | Skill ladder (Hindi reading, maths, English words) and activity bank (placeholder, not NCERT text) |
| `web/` | Teacher web app (installable PWA, offline queue; Hindi or English, one language at a time: हिं / EN switch) |
| `samples/synthetic/` | **Synthetic** demo class, demo history, sample notes and audio, sample register and textbook photos |
| `tests/` | Guardrail and adversarial tests, planner, brief checks, API flow |
| `eval/` | Simulations (`eval/sim/`, including ASER 2024-calibrated classes), real-speech scorer (`eval/real_notes/`), cost (`cost.py`), feasibility tests, demo seeding; results in `eval/results/` |
| `docs/` | Handoff, design-change log, feasibility and strategy notes |

**Retired v0 pipeline:** `claude_moments.py`, `claude_evidence.py`, `claude_brief.py` and `prompts/*.v1.md` (moments, evidence, brief) belong to the first design, which recorded the whole lesson. The F1 test (`docs/feasibility.md`) showed that voice matching cannot tell which child answered. Classroom constraints did the rest: distance from the back bench, phone heat, starting and stopping per period, and children's-voice consent. We kept those files as the record of what we tried.

## Never commit

Real audio, children's names, consent forms, team photos, `.env`. See `.gitignore`.
