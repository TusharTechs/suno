# How each juror is likely to score SUNO, and what gets it to full marks

27 Oct 2026. Based on public statements by each juror (research with sources, summarised below) and on SUNO as it stands today: hosted app, simulations in `eval/results/sim_*.md`, no real-teacher testing yet. Scores are our honest estimate out of 10 per criterion, **before** the work in "What we do next". They are a planning tool, not a prediction.

**Rubric weights:**
- Efficacy and user-centricity: 35%. Impact; intuitive UI; built for vernacular, voice-first users; proof of testing and refinement from user input.
- Effective AI and technical strength: 30%. AI used for its strengths; guardrails; works in real scenarios.
- Innovation: 25%. Novel approach; meaningful differentiation from existing tools.
- Roadmap: 10%. A path to development, and integration into existing systems.

## The jury

### Rukmini Banerji (Pratham; built ASER, led TaRL)
- **What she values:**
  - Assessment that is simple and fast: "the tool is simple because you can move fast".
  - Assessment and activity as one thing: "teach at the level of the child".
  - Skepticism about AI that "steps in to do what a teacher finds difficult".
  - "too much assessment now".
- **Her likely scores today:**
  - Efficacy 7: next-morning groups and activities fit TaRL; no real classroom evidence yet.
  - AI 7.
  - Innovation 8: no test at all, the teacher's own ear.
  - Roadmap 6.
- **Why lower:**
  - No proof with real teachers.
  - She will ask whether teacher reports agree with what an ASER test would find.
- **What wins her:**
  - The ladder levels are ASER/TaRL levels: beginner, letter, word, sentence, story.
  - Groups and a 10-minute activity come out the next morning.
  - SUNO says "not enough evidence yet" instead of guessing.
  - A concrete plan to compare SUNO's levels with the ASER tool on the same children (finale testing).
  - Framing: SUNO keeps the teacher in charge; it remembers, it doesn't replace.

### Jonathan Stern (Gates Foundation; formerly RTI, EGRA research)
- **What he values:**
  - Validated measurement.
  - Learner profiles that "guide instruction".
  - Targeting the lowest performers, not mean scores.
  - Skepticism about large-effect claims.
- **His likely scores today:** efficacy 6, AI 8, innovation 7, roadmap 6.
- **Why lower:**
  - Teacher-reported observations are not a validated measure.
  - Simulation is not evidence of impact.
- **What wins him:**
  - Precision reported with counts and stated assumptions, and a conservative "rule of three" for zero-error results.
  - Levels that map to EGRA-style learner profiles.
  - A planner that keeps the quietest children in view: 7× more of their struggles found in simulation.
  - A pre-registered validation design against ORF/ASER for the finale.
  - Never overclaiming.

### Ishmeet Singh (CEO, Central Square Foundation, the organiser)
- **What he values:**
  - Data that "rarely fed back into instructional decisions in time" is his core critique of NIPUN monitoring; he wants formative checks built into teaching, aligned with EGRA/EGMA.
  - A pathway from innovation to state adoption.
- **His likely scores today:** efficacy 8, AI 7, innovation 8, roadmap 5.
- **Why lower:** the roadmap doesn't yet show how SUNO plugs into NIPUN, the VSKs, or state teacher apps.
- **What wins him:**
  - "Evidence reaches the teacher the next morning, as an action."
  - An integration story with no new data entry: SUNO levels export to the NIPUN competency framework and VSK dashboards, aggregated, with no teacher score.

### Rahul Kulkarni (Chief Technologist, Samagra; his team built UP's NIPUN Lakshya app)
- **What he values:**
  - LLM factual accuracy.
  - Digital public goods and open standards.
  - Systems governments can own.
  - Interoperability with existing state stacks.
- **His likely scores today:** efficacy 7, AI 8, innovation 7, roadmap 5.
- **Why lower:**
  - He will ask why SUNO isn't simply a feature inside NIPUN Lakshya.
  - He will want an open schema and data export.
- **What wins him:**
  - The grounding check, live: every claim cites the teacher's sentence; code resolves the child; Claude never sets confidence.
  - Open JSON schemas.
  - Offline queue and low data use.
  - The cost per teacher per month.
  - Position SUNO as a capability that can live inside NIPUN Lakshya or DIKSHA (the roadmap), not "yet another app".

### Mekin Maheshwari (Udhyam; formerly Flipkart)
- **What he values:**
  - Working "within government systems".
  - Teacher agency.
  - Habit-forming products.
  - WhatsApp-first delivery.
- **His likely scores today:** efficacy 7, AI 7, innovation 8, roadmap 6.
- **Why lower:** there's no evidence teachers will keep sending notes.
- **What wins him:**
  - A 60-second habit that pays back the next morning.
  - The teacher's own words as the input, with no surveillance.
  - A WhatsApp voice-note channel on the roadmap.
  - Any real teacher using it and saying something unprompted.

### Raahil Rai (Anthropic, Beneficial Deployments)
- **What he values:**
  - Claude used for what it is good at.
  - Guardrails.
  - "AI education should increase human agency."
- **His likely scores today:** efficacy 7, AI 9, innovation 8, roadmap 6.
- **What wins him:**
  - Messy code-mixed Hindi speech becomes structured, cited observations: a real Claude strength.
  - Two calls only, each with a versioned prompt and schema, adaptive thinking, structured outputs, prompt caching and server-side refusal fallback.
  - Code verifies every claim.
  - The trace view that shows all of this in the app.

### Shridhar Sethuram (Suyash Advisors, private equity; Ashoka entrepreneurship faculty)
- **What he values (inferred):** unit economics, adoption path, a sharp story.
- **His likely scores today:** efficacy 7, AI 7, innovation 7, roadmap 6.
- **What wins him:**
  - Cost per child per year, computed from the logs, not guessed.
  - Who pays: the state, under Samagra Shiksha's FLN budget.
  - A credible adoption path.

### Piyush Prasad (IHFC, IIT Delhi; education research and teacher training)
- **What he values (inferred):** teacher usability, a training-light rollout, research rigour.
- **His likely scores today:** efficacy 7, AI 8, innovation 8, roadmap 6.
- **What wins him:**
  - A teacher learning it in five minutes.
  - Hindi-only mode.
  - Clear evaluation methodology.

## Overall today, weighted

| | Efficacy 35% | AI 30% | Innovation 25% | Roadmap 10% | Weighted |
|---|---|---|---|---|---|
| Average across the jury | 7.0 | 7.6 | 7.6 | 5.8 | **7.3 / 10** |

The two cheapest points to win:
1. **Real-user proof** (efficacy, 35%).
2. **A concrete integration roadmap** (10%).

## Where SUNO is already strong, and should say so plainly

- **Differentiation:** PadhAI, TARA, Vaachan Samiksha and NIPUN Lakshya are assessment events: one child reads into an app. SUNO has no test and records no child's voice. It turns what the teacher already noticed into checked, per-child evidence, and tells her the next morning whom to listen to and what to do. These are complementary, not competing.
- **Measured precision (SIMULATED, 32 voice notes, 4 teacher styles, real speech-to-text):**
  - No evidence about the wrong child: 0 of 114.
  - Right/wrong direction always right: 114 of 114.
  - No opinion, label or vague remark became evidence: 0 of 42.
  - Labels never repeated.
  - Every unclear name was resolved by one tap: 24 of 24.
  - Source: `eval/results/sim_pipeline.md`.
- **The design learns from failure, on the record:**
  - F1 killed classroom audio.
  - The term simulation showed the first planner made detection *worse* by spreading attention.
  - The fix (the ladder model and two-item mini-ladders) is in `docs/decisions.md`.
  - That is exactly the "refinement" the rubric asks for.

## What we do next, in priority order

1. **Real users, even a few** (efficacy, all jurors).
   - 2–3 real teachers each record one or two real notes about their own class. Use first names, or replace names. Let them hear the brief, and log what they say and what we change.
   - Tomorrow's call with Rebecca (Madhi) counts as mentor input: open with the live demo.
   - Even one teacher who sends a second note on day two is the best possible evidence.
2. **Validation design for the finale** (Banerji, Stern): SUNO's levels vs the ASER tool on the same 20–30 children, with a written protocol and agreement measured by level.
3. **Roadmap slide** (Singh, Kulkarni, Maheshwari):
   - a WhatsApp voice-note channel;
   - export of levels to the NIPUN competency codes and VSK dashboards (aggregated, no teacher score);
   - a SUNO module inside NIPUN Lakshya or DIKSHA;
   - Bhashini or IndicConformer for state-owned speech;
   - Tamil and Marathi next;
   - cost per child per year from the logs.
4. **App polish for real teachers** (Prasad, Maheshwari, the "intuitive interface" criterion):
   - Hindi-only mode;
   - roster from a photo of the attendance register (Claude vision);
   - this week's lesson words set by the teacher;
   - persistent storage;
   - two items per listed child;
   - TaRL levels in the class view.
5. **Demo video:** show the loop in 3 minutes.
   - Teacher speaks.
   - SUNO catches a label and an unclear name.
   - The next morning's brief.
   - The listening list finds a quiet child.
   - End on the simulation numbers and the honest limits.
