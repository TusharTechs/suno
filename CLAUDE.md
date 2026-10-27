# SUNO: project instructions for Claude Code

## What this is
**SUNO** (सुनो, "listen") is our entry in the **AI for Foundational Learning Hackathon** (Hack2Skill × ShikshaNext × Central Square Foundation × Anthropic), Challenge 2: Learning-Level Visibility. It is in the **Top 30 (Build stage)**.

SUNO is for Grade 1–3 government-school teachers in India. **SUNO listens to the teacher, not the classroom:**
- After the reading period, the teacher speaks a **~60-second voice note** in her own words: who read what, who got stuck where, who was absent.
- Sarvam transcribes it. Claude turns it into **per-child observations**. Code checks every claim against her words and the roster, and computes confidence. Opinions and labels never become evidence.
- Code tracks each child's **level on the ASER/TaRL ladder** and picks five children (two words each) to listen to the next day, so quiet children are not missed.
- Next morning, a ~2-minute **Hindi voice brief** tells her who needs support with what, today's group activity, and whom to listen to.

No tests, no child's voice recorded, about a minute of teacher time a day. The design changed after the Ideate deck (the phone-worn classroom recording was dropped): see decisions 20–31 in `docs/decisions.md`.

Live: https://suno-8qoh.onrender.com (demo code `SUNO-DEMO`). Repo: private, `TusharTechs/suno`.

Team Sunvai:
- **Tushar**: lead, product and engineering
- **Saikiran**: architecture and risk

## Read before doing anything
1. `docs/HANDOFF.md`: the full context. Live version: https://claude.ai/code/artifact/5979df68-0b1e-4895-a86a-3592ee10bd2a (the live doc wins if they differ). It covers rules, scoring, the product, design decisions, the build spec, APIs, the plan, data and evaluation, user testing, privacy, the mentor calls and risks.
2. `docs/decisions.md`: the design-change log. This is the evidence for the Build deck's "User inputs and testing" slide.
3. `docs/mentor-calls.md`: who, when, what to ask, and the report template.
4. `docs/judging.md`: juror-by-juror scoring and what is still missing.
5. `eval/results/`: the simulation (`sim_pipeline.md`, `sim_term.md`) and cost (`cost.md`) results. All SIMULATED.

## Deadlines (IST)
- **Build submission: 1 Nov 2026, 11:59 pm.** Aim to submit by early afternoon. **No commits after the deadline.** Freeze the deploy.
- Education mentor call (Rebecca Swittens, Madhi Foundation): 28 Oct, 5 pm.
- Top 10 announced 10 Nov. Grand finale (in person, live demo): 18 Nov.

## Hard rules
1. **Claude is the reasoning core.** Use `claude-opus-5-5` (Claude Opus 5.5; set effort explicitly, its default is medium) with adaptive thinking (`thinking: {type: "adaptive"}`) and JSON-schema structured outputs. **Code computes confidence, never the model.** Load the Claude API skill before writing API code. Don't guess SDK shapes.
2. **Never commit:** real audio, children's names, consent forms, team photos, or secrets. `.env`, `data/raw/`, `data/external/`, `data/consents/` and `assets/` are git-ignored. Run a secret scan before the freeze.
3. **No teacher score or teacher-performance field anywhere.** Never describe a child as weak, slow or poor; enforce a banned-word list in English and Hindi. Use first names only.
4. **Every claim about a child** must cite real sentence IDs from the teacher's note (the grounding check in code), name a child that code resolves from the roster, and pass the confidence gate (0.75 by default). Below the gate, it becomes "check tomorrow". Opinions never become evidence.
5. **Precision over recall.** When unsure, the answer is "not enough evidence yet".
6. **The judges' path runs live**, with direct API calls. Message Batches are for bulk evaluation only.
7. **Keep the AI visible in the code.** Prompts go in `prompts/` and JSON schemas in `schemas/`, as versioned files. One module per pipeline stage. Tests for the guardrails, including the adversarial cases listed in HANDOFF.md.
8. **Label synthetic and simulated data** as such everywhere. Never invent evaluation numbers: every number comes from a script in `eval/`.
9. **No child's voice is ever recorded.** The teacher's voice note is deleted after transcription; the register photo is not stored.

## Repo layout
```
server/   api.py (FastAPI + web app), jobs.py, store.py (SQLite or Postgres), demo.py
server/pipeline/   asr, claude_observations, names, guardrails, confidence, ladder,
                   planner, brief, tts, roster_photo  (one module per stage)
web/      teacher web app (PWA, offline queue, हिं | EN)
prompts/  schemas/  config/ (skill ladder, activities)  tests/
eval/     sim/ (simulation), cost.py, seed_demo.py, feasibility/, results/
samples/synthetic/   demo class, demo history, sample notes (all synthetic)
docs/     data/ (raw is ignored)  assets/ (ignored)
```
Retired v0 (classroom recording): `claude_moments.py`, `claude_evidence.py`, `claude_brief.py`, `prompts/*.v1.md` except `observations.v1.md`.

## When Tushar sends "Mentor call report:" (or user-testing notes)
1. Append each item to `docs/decisions.md`: date, source, what they said or did, what we changed, and where it shows.
2. Update the matching rows in HANDOFF.md, "Design decisions since the Ideate deck" (Proposed → Decided or Dropped). Adjust the build plan.
3. Add any user or mentor evidence to the "Evidence for the Build deck" list in `docs/decisions.md`.
4. Reply with a short summary of what changes in the code this week, and anything that needs Tushar's decision.

## Environment
- `.env`:
  - `ANTHROPIC_API_KEY`: the hackathon key, $500 of credits. Running cost is about ₹15 a teacher-day (`eval/results/cost.md`); simulations cost a few dollars each. Track spend weekly.
  - `SARVAM_API_KEY`: speech-to-text and text-to-speech.
  - `SUNO_DATABASE_URL` (optional): Postgres when set, else SQLite in `var/`. `.env.example` lists the rest.
- Hosting: Render, **free plan only** (`render.yaml`: free web service + free Postgres, Singapore). Do not use paid plans or the Render account's credits.
- Tools: Python 3.12 via `uv`, Node 22+, `ffmpeg`, Google Chrome (screenshots via `scripts/shoot.mjs`, deck and video rendering), Docker via colima (optional).

## Existing assets (not code)
- `assets/deck/`:
  - the Ideate decks: `suno.html` and `pahunch.html`, plus `shared.css` and the PDFs
  - `render.sh suno` re-renders the PDF
- `assets/deck/video/`:
  - `walkthrough.html` plus `capture.mjs`: the 91-second concept animation
  - the MP4s (silent, and with voiceover), the SRT and the thumbnail
  - `vo/make_vo.py`: the Sarvam voiceover pipeline. It reads `SARVAM_API_KEY`; set `VO_SPEAKER` to change the voice.
- The silent concept video on YouTube, linked from the deck: https://youtu.be/e8ZQBmMNkPY
- `assets/reference/`: the organisers' guidelines, key messages and tech-evaluation PDFs.
