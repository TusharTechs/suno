# Build submission: the four deliverables

Deadline: **1 Nov 2026, 11:59 pm IST.** Aim to submit by early afternoon. **No commits after the deadline.**

## 1. Demo version

| Field | What to enter |
|---|---|
| Hosted link | https://suno-8qoh.onrender.com (web app; works on any phone or laptop browser; installable as a PWA) |
| Test credentials | One role only: **the teacher**. Code **`SUNO-DEMO`**: every sign-in gets its own fresh copy of a synthetic Grade 2 class. To test setting up a class from scratch, choose *create your own class* on the sign-in page; SUNO gives a class code. No admin, student or parent role exists, by design (no teacher score, no surveillance). |
| Sample inputs | 1–4: four synthetic Hindi voice notes in the app (Note tab → *sample notes*): an ordinary day; hard cases (two Priyas, a label, a name not on the roster, an opinion); maths and home language; Hinglish. 5: a register photo (☰ → Children → *try a sample photo*). 6: a textbook page (☰ → This week's lesson → *try a sample page*). Files: `samples/synthetic/`. |
| Offline behaviour | Works offline: recording (queued on the phone, sent when the network returns), the last brief and its audio, the class picture as last loaded. Needs a network: sending a note (100–250 KB a minute), fetching the next brief. Test: network off → record → network on. |
| Note for evaluators | Free hosting: after 15 idle minutes the first visit takes about a minute to wake the server. |
| Frozen version | See the freeze steps below. |

## 2. Source code

| Field | What to enter |
|---|---|
| Repo | https://github.com/TusharTechs/suno (private) |
| Evaluator access | Waiting for the Tech4Dev evaluator IDs. For each ID: `gh api -X PUT repos/TusharTechs/suno/collaborators/<github-id> -f permission=pull` |
| README | Setup, local run, `.env.example`, the table of every external AI service and where its key goes, test credentials, sample inputs |
| Secrets and personal data | Scanned on 29 Oct: no keys in the tree or history; the only audio is the synthetic samples; no real children's or users' data. Re-run before the freeze (below). |

## 3. Demo video (3 minutes)

- File: `assets/deck/video/demo/SUNO_demo.mp4` (2:57.8, 1080p). Subtitles: `SUNO_demo.srt`. Thumbnail: `SUNO_demo_thumb.jpg`.
- **YouTube: https://youtu.be/GG3v7lQ212M** (public; linked in the README and on the deck's closing slide). If not done yet, add `SUNO_demo.srt` as English subtitles.
- It covers what the organisers list:
  - the challenge and how SUNO addresses it (the classroom, the ASER figure, what we tried first and why we changed);
  - the UI walkthrough (recording, what SUNO understood, the brief, the class picture, a child's page);
  - the key features (one-tap names, labels and opinions held back, the listening list, levels and progress);
  - ease of use (one note a day, voice-first Hindi, two-photo setup, offline).

## 4. PowerPoint deck

- Hosted: https://suno-8qoh.onrender.com/deck (PDF, opens in the browser) and https://suno-8qoh.onrender.com/deck.pptx (PowerPoint download). Copies in `web/deck/`. For the form, a Google Drive link opens instantly (no free-hosting wake-up); paste that if you upload one.
- File: `assets/deck/build/SUNO_build_deck.pptx` (16 slides; PDF alongside). Rebuild: `cd assets/deck/build && NODE_PATH=$PWD/node_modules PPTX_SKILL=<pptx skill dir> node build.js`.
- What it covers:

| Organisers' item | Slides |
|---|---|
| AI/LLM use, in layers (input → processing → guardrails → evaluation → output) | 4 (layers), 5 (each model call, what it does, what code does with it) |
| Guardrails for wrong or inappropriate output | 6 |
| Working in real scenarios: low connectivity, low data, low-cost devices | 9 (offline, network, graceful degradation, how to test) plus 7–8 (evidence) |
| User inputs and testing (1–2 pages) | 11 (what we heard, what we changed), 12 (how the design changed, what is not proven) |
| Future roadmap (1–2 pages) | 14 (phases), 15 (integration, cost, who pays) |

## Freeze steps (1 Nov, before submitting)

1. Final commit of anything pending, then merge `feasibility/voice-attribution` into `main`.
2. Point `render.yaml` at `main`, and set **auto-deploy off** in the Render dashboard (Settings → Build & Deploy → Auto-Deploy: No), so the evaluated version cannot change.
3. Check the live app once: sign in with `SUNO-DEMO`, play the brief, send a sample note.
4. Final secret scan: `git log -p --all | grep -E "sk-ant-|api-subscription-key"` should print nothing.
5. Grant read access to the evaluator IDs.
6. Submit. **Make no commits after 11:59 pm IST on 1 Nov.**
