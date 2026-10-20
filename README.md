# SUNO: handoff bundle

SUNO turns the ordinary talk of a Grade 1–3 lesson into per-child learning evidence for the teacher, with no tests and no extra teacher time. Built by Team Sunvai for the AI for Foundational Learning Hackathon (Challenge 2).

## What's here
| Path | What |
| --- | --- |
| `CLAUDE.md` | Project instructions that Claude Code reads automatically |
| `docs/HANDOFF.md` | Full context and build spec (offline copy of the live doc) |
| `docs/decisions.md` | Design-change log: the evidence for the Build deck |
| `docs/mentor-calls.md` | Mentor schedule, questions, report template |
| `docs/outreach.md` | Outreach drafts for NGOs, head teachers, LinkedIn and the organisers |
| `data/` | Where datasets and recordings go (`raw/` is git-ignored), plus the labelling template |
| `assets/` | Ideate decks, video sources and renders, organiser PDFs (git-ignored by default) |

## Set up on a new Mac
```bash
brew install uv node ffmpeg poppler postgresql@16
cp .env.example .env   # then fill in the keys
git init && git add . && git commit -m "SUNO: start from handoff bundle"
```
Then open this folder in Claude Code and say: *"Read CLAUDE.md, docs/HANDOFF.md and docs/decisions.md, then propose today's build plan."*

## Feasibility tests (run these before building more)
Python 3.12 via `uv`. Results go to `eval/results/`, and the write-up is `docs/feasibility.md`.
```bash
uv sync --group speech --group dev
uv run python eval/feasibility/prep_aser.py                 # unpack Pratham ASER (download into data/external/aser first)
uv run python eval/feasibility/voice_id.py                  # F1: which child answered, by voice (no keys needed)
uv run python eval/feasibility/answer_check.py              # F2: right vs wrong reading (needs SARVAM_API_KEY)
uv run python eval/feasibility/claude_attribution.py        # F3: Claude + code on hard cases (needs ANTHROPIC_API_KEY)
uv run python eval/feasibility/home_test.py data/raw/<session> --labelled-on worn   # F1 on a real home recording
uv run pytest                                               # guardrail tests, no keys needed
```
External AI services: Anthropic Claude (`ANTHROPIC_API_KEY`, model `claude-opus-5-5`) and Sarvam speech-to-text and text-to-speech (`SARVAM_API_KEY`). Open models, downloaded on first run: SpeechBrain ECAPA and Microsoft WavLM-SV for speaker embeddings.

## Rebuild the existing assets
- **Deck PDF:** run `assets/deck/render.sh suno` (needs Google Chrome and Poppler).
- **Concept video frames:** in `assets/deck/video/`, run `node capture.mjs frames 24`.
- **Encode the frames to MP4:**
  `ffmpeg -framerate 24 -i frames/f%05d.jpg -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart SUNO_concept_walkthrough.mp4`
- **Voiceover (Sarvam):** run `SARVAM_API_KEY=... python3 assets/deck/video/vo/make_vo.py`. It writes `SUNO_concept_walkthrough_voiceover.mp4` and `.srt` into `assets/deck/video/`. Add `VO_SPEAKER=kavya` for a female voice.

## Never commit
Real audio, children's names, consent forms, team photos, `.env`. See `.gitignore`.
