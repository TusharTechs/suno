# SUNO सुनो

**SUNO listens to the teacher, not the classroom.** After the reading period, a Grade 1–3 government-school teacher speaks a 60-second voice note in her own words: who read what, who got stuck where, who was absent. Next morning she hears a 2-minute Hindi brief telling her who needs support with what, today's small-group activity, and which five children to listen to today, each with one word or sum from this week's lesson.

No child's voice is recorded. Nothing records the classroom. There are no tests and no data entry.

Team Sunvai's entry in the AI for Foundational Learning Hackathon (Challenge 2: Learning-Level Visibility).

## Try it

- **Hosted:** _link added at deploy_. It runs on Render's free plan: after 15 idle minutes the server sleeps, and the first visit takes about a minute to wake it. Demo classes are re-created at every login, so the demo is unaffected; a class you create yourself is lost when the server sleeps.
- **Code:** `SUNO-DEMO`. Each login gets its own fresh copy of a **synthetic** Grade 2 class: 30 fictional children, eight school days of teacher notes already run through the pipeline, and this morning's brief.

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

You can also create your own class from the login page and use it for real.

## How it works

```
Teacher's voice note (phone, offline-capable)
  → Sarvam saaras:v4 speech-to-text → numbered sentences s1, s2, …
  → Claude ①  observations: per child, skill, item, outcome, mistake type   [prompts/observations.v2.md, schemas/observations.v1.json]
  → code checks: cited sentences exist; quote and item really are in her words; the child is resolved
    from the roster by code (phonetic names, roll numbers) and must agree with Claude; labels masked;
    "किताब को किताब पढ़ा" (speech-to-text erasing the misreading) can't be "correct"
  → code confidence (who × how specific × how concrete × how recent); gate 0.75
       below the gate, and every opinion → "listen again tomorrow", never a label
  → tracker (Beta per child × skill; named only with ≥3 observations over ≥2 days),
    Silence Ledger, listening plan (code, no AI)
  → Claude ②  words the brief from code-decided facts                    [prompts/brief.v2.md, schemas/brief.v2.json]
  → code checks: no unbacked "needs support", exact listening list and ledger, activity fits the skill, banned words
       fail twice → the app shows the code facts without prose (fail closed)
  → Sarvam bulbul:v3 Hindi voice
```

| Layer | What | Where |
| --- | --- | --- |
| Input | Teacher's voice note (or typed note) | `web/app.js` (MediaRecorder, offline queue in IndexedDB) |
| Processing | Speech-to-text; sentences; Claude ① | `server/pipeline/asr.py`, `claude_observations.py` |
| Guardrails | Grounding, roster resolution, item check, labels, erased-misreading check, computed confidence | `server/pipeline/guardrails.py`, `names.py`, `confidence.py` |
| Decisions | Tracker, Silence Ledger, listening plan | `server/pipeline/tracker.py`, `planner.py` |
| Output | Claude ② brief, checked; Hindi voice | `server/pipeline/brief.py`, `tts.py` |
| Teacher feedback | ✓/✗ on every observation (✗ removes it from the tracker); one-tap name questions | `server/api.py` |

**Claude** (`claude-opus-5-5`, adaptive thinking, JSON-schema structured outputs, explicit effort, prompt-cached roster and lesson, server-side refusal fallback) makes two calls: reading the note, and wording the brief. **Code computes every confidence, decides every fact, and checks everything Claude returns.**

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

**External AI services**, with keys in `.env` (never committed):
- **Anthropic Claude:** `ANTHROPIC_API_KEY`, model `claude-opus-5-5`.
- **Sarvam AI:** speech-to-text `saaras:v4` and text-to-speech `bulbul:v3`, key `SARVAM_API_KEY`.

**Regenerate the synthetic demo data** (costs about $0.40 of Claude credit):

```bash
uv run python eval/seed_demo.py
uv run python eval/make_samples.py
```

## Repo map

| Path | What |
| --- | --- |
| `server/api.py`, `jobs.py`, `store.py`, `demo.py` | Web API, background jobs, SQLite storage, per-login demo sandboxes |
| `server/pipeline/` | One module per stage: `asr`, `claude_observations`, `names`, `guardrails`, `confidence`, `tracker`, `planner`, `brief`, `tts` |
| `prompts/`, `schemas/` | Versioned prompts and JSON schemas for every Claude call |
| `config/` | Skill ladder (Hindi reading, maths, English words) and activity bank (placeholder, not NCERT text) |
| `web/` | Teacher web app (installable PWA, Hindi first, English sub-labels for reviewers) |
| `samples/synthetic/` | **Synthetic** demo class, demo history, sample notes and audio |
| `tests/` | Guardrail and adversarial tests, planner, brief checks, API flow |
| `eval/` | Feasibility tests (F1 voice matching), demo seeding, evaluation scripts |
| `docs/` | Handoff, design-change log, feasibility and strategy notes |

**Retired v0 pipeline:** `claude_moments.py`, `claude_evidence.py`, `claude_brief.py` and `prompts/*.v1.md` (moments, evidence, brief) belong to the first design, which recorded the whole lesson. The F1 test (`docs/feasibility.md`) showed that voice matching cannot tell which child answered. Classroom constraints did the rest: distance from the back bench, phone heat, starting and stopping per period, and children's-voice consent. We kept those files as the record of what we tried.

## Never commit

Real audio, children's names, consent forms, team photos, `.env`. See `.gitignore`.
