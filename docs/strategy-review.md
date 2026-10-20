# Is SUNO feasible, useful to teachers, and something this jury will value?

21 Oct 2026. Written after the technical mentor call and the F1 result. It answers Tushar's questions:
- Will teachers understand where children are stuck?
- Will they keep pressing record?
- Does SUNO handle a child who is good at one topic but not another?
- Does it work for teachers and children at the same time?
- Will the judges like it?

Sources are linked inline. Numbers we produced come from scripts in `eval/`.

## Bottom line

1. **Ambient SUNO doesn't work, and the tap version I proposed yesterday doesn't fix the deeper problem.**
   - **Voice can't tell children apart.** That is the F1 result.
   - **Ordinary lessons contain too few individual answers to build a per-child, per-topic picture.**
     - In 1,706 observed Std 2 and Std 4 classrooms, teachers asked any oral questions in only about 57% of them, and group work appeared in about 16% ([Inside Primary Schools](https://neqmap.bangkok.unesco.org/wp-content/uploads/2019/08/Inside-Primary-Schools-Main-Report.pdf), 2011, Table 4.9). This predates NIPUN's structured pedagogy, but nothing suggests individual reading turns have become common.
     - Our model (`eval/results/evidence_rate.md`) shows that listening to ordinary lessons would know about 5% of child × skill cells after four weeks, and 40% of children would never be heard.
     - Tapping during planned call-ons only reaches about 21% after eight weeks, and only on the week's focus skills.
2. **What does work is deliberate, short, planned listening.** SUNO picks 3–5 children a day; each reads a 90-second ladder of items from this week's lesson to the teacher, plus one "what did it mean?" question.
   - It costs 5–8 minutes of the reading period.
   - It knows about 69% of child × skill cells after four weeks, and all of them by week eight.
   - It gives a class-level "move on or reteach?" answer within two days.
3. **On its own, that is an AI reading test, and this jury knows several.**
   - [Pratham's PadhAI](https://pratham.org.uk/pratham-launches-padhai-transforming-literacy-with-ai-powered-reading-assessments) comes from the organisation one juror leads.
   - Gujarat's [Vaachan Samiksha](https://www.wadhwaniai.org/vaachan-samiksha-leveraging-ai-to-bridge-the-literacy-divide/) has reached 1.2 lakh teachers and 25 lakh students.
   - IIT Bombay's [TARA](https://www.iitb.ac.in/research-highlight/iit-bombays-tara-mobile-app-help-achieve-nationwide-oral-reading-fluency) is used with 7 lakh KVS students.
   - UP's [NIPUN Lakshya app](https://www.drishtiias.com/state-pcs-current-affairs/up-implements-nipun-lakshya-to-overhaul-primary-education) has teachers running weekly micro-quizzes.
   - A 2025 [Tools Competition winner](https://tools-competition.org/winner/oral-reading-fluency/) does Hindi reading assessment, groups children into four fluency stages and generates remediation for each group.

   So SUNO's case has to rest on what happens after the listening (point 5).
4. **The biggest open question is behavioural, not technical:** will a teacher run a 5-minute round three or more days a week? Evidence cuts both ways:
   - A Gujarat teacher reports reserving the first two periods for the state's reading-assessment app, in batches of 5–10 children ([Wadhwani AI](https://www.wadhwaniai.org/vaachan-samiksha-leveraging-ai-to-bridge-the-literacy-divide/)).
   - Teachers are drowning in apps: UP teacher leaders report [an hour a day sending data](https://news.careers360.com/school-teacher-data-entry-burden-udiseplus-midday-meal-diksha-attendance-nishtha-ullas-portal-apps-login-monitoring-education/amp).

   Only a test with real teachers can settle it, and the design has to make the round replace work, not add it.
5. **What can make SUNO different and worth the jury's attention:**
   - **Lesson-linked:** it checks yesterday's lesson and says "move on or reteach" for tomorrow.
   - **Diagnosis:** it names the specific confusion, with the child's own 4-second clip as proof.
   - **Understanding:** it judges a child's free spoken answer to a meaning question. This is where Claude is strong and word-matching tools aren't.
   - **Coverage:** a planner plus the Silence Ledger make sure quiet children are heard.
   - **Precision:** claims are made only when certain.

## Your questions, answered

### Will the solution work at all? (technical)
- **Who answered:** solved by design. The app tells the teacher whom to call next, the child reads near her, and no voice matching is needed.
- **Right or wrong:** still unproven. F2 measures Sarvam's speech-to-text on real child single words against the ASER surveyors' labels; it needs the Sarvam key.
- **Understanding:** untested. A child's short spoken answer, recognised by Sarvam and judged by Claude against the passage, needs its own small test (see "Before building more").
- **Build by 1 Nov:** feasible if scope stays Hindi reading for Grade 1–2:
  - the judges' web path;
  - a recorder screen that runs the round, offline-first;
  - the reasoning core, which is already written and tested.

### Can teachers understand where children are lacking?
Only if SUNO speaks their language and shows proof.
- **Teachers' own picture is often wrong.**
  - In a [study of about 1,800 teachers in 848 rural Indian schools](https://www.repository.cam.ac.uk/handle/1810/340145) (Wadmare et al., 2022), about 40% believed their weakest readers had already acquired foundational literacy.
  - Teacher-proctored paper tests in Andhra Pradesh [overstated scores by 16–20 points](https://www.hhs.se/en/about-us/news/department-of-economics/2024/improving-administrative-data-at-scale-experimental-evidence-on-digital-testing-in-indian-schools/) compared with independent retests; tablet-based tests matched.

  SUNO's evidence has to be objective and checkable. Each claim comes with the child's clip, for example "listen: Priya reads क… म… ल without joining".
- **Use the levels teachers already know.** That means the ASER/TaRL ladder (beginner, letter, word, paragraph, story) and the competencies in their teacher guide, not our skill codes.
- **Data alone doesn't change teaching.** States that see results use weekly checks mapped to specific competencies and paired with what to do next ([CSF](https://www.centralsquarefoundation.org/articles/reading-between-the-scores-in-conversation-with-dr-akashi-kaul)). So every finding comes with one action for tomorrow, taken from the teacher guide or activity bank.
- **Output:**
  - a 2-minute Hindi voice brief;
  - one screen with children down the side and the ladder across the top, each cell in words (मदद चाहिए / ठीक / अभी पता नहीं), not only colours.

  Test this with teachers before polishing it.

### Will teachers keep pressing record and stop every time?
Pressing record for each child, every day, during normal teaching: honestly, no, beyond the first week or two. So don't ask for it.
- **One start a day, and the app leads.**
  - The teacher taps "start reading round".
  - The phone shows (or quietly speaks) the next child's name and the items from today's lesson.
  - It moves on by itself when the child stops, or the teacher taps "absent" or "skip".
- **Three days a week is enough.** A skipped day breaks nothing; SUNO says "not enough evidence yet" rather than guessing.
- **Make it replace work.**
  - UP already asks teachers to run weekly micro-quizzes in its app. The roadmap is for SUNO's round to fill that in automatically.
  - Structured-pedagogy teacher guides script checks-for-understanding questions into lessons (for example, [this FLN programme's guides](https://www.csbc.org.in/upload/FLN_teachers_PAP.pdf)); the round can be that step.
- **Be careful about compliance pressure.** A [UP behavioural diagnostic](https://www.socialscienceregistry.org/versions/192795/docs/version/file) found teachers can feel micromanaged by trackable programme requirements. SUNO must stay the teacher's own tool: no supervisor view and no teacher score (already a hard rule).
- **Ask teachers directly in round 1:**
  - Would you do this?
  - Which period?
  - How many minutes is too many?
  - What would make you stop?

### What if a child is good at one topic but not another?
That is exactly what a per-child, per-skill tracker is for, but only if the evidence covers each skill. In the model:

| How evidence is collected | Teacher time a day | Child × skill cells known after 4 weeks | after 8 weeks | Never heard after 4 weeks |
|---|---|---|---|---|
| Listen to ordinary lessons | 0 min | 5% | 10% | 40% |
| Tap on 5 planned call-ons | ~1 min | 5% | 21% | 0% |
| 90-second ladder, 5 children a day | ~7.5 min | 69% | 100% | 0% |
| 90-second ladder, 3 children a day | ~4.5 min | 20% | 86% | 0% |

*Model with stated assumptions (class of 35, 80% attendance, 6 skills, 3 confident moments over 2 days to name a status), not a measurement.*

- **Early Hindi reading is mostly a ladder:** akshara → vowel signs (matra) → joining sounds → words → fluent reading. An adaptive ladder, as ASER uses, finds each child's edge in a minute or two.
- **Understanding is a separate dimension.** A child can sound out words without understanding them, or understand spoken Hindi well but not decode. So each turn ends with one meaning question. NIPUN Bharat's goal is reading *with understanding*.
- **Two speeds:**
  - The class-level answer ("most children can't yet read words with ि and ी; reteach lesson 23") needs only a sample, so it comes within two days.
  - The full child × skill picture takes about four weeks.
  - A baseline week (everyone once) gets the picture started.

### How does SUNO tell which child understands which topic?
1. This week's lesson gives the items: two letters, two vowel-sign words, two blending words, one line, one meaning question.
2. The planner picks today's children: those heard least, those near a skill edge, and anyone the Silence Ledger flags.
3. The child reads to the teacher close to the phone. Speech-to-text runs on each item.
4. **Claude** judges each item against what was expected: right, wrong or partial, plus the error type. It also judges the meaning answer in free Hindi.
5. **Code** computes confidence from the signals and applies the gate. It updates that child's belief for that skill; nothing reaches the teacher below the gate.
6. After two or more days of evidence, a skill turns to "needs support" or "on track". **Claude** then summarises patterns across weeks, for example "drops the ि sign in 4 of 5 words".
7. The brief groups children by the skill they need next, and gives each group one 10-minute activity.

### Is it feasible for teachers and children at the same time?
- **Children:**
  - 90 seconds, about once a week, reading to their own teacher. That's ordinary and low-stakes, and needs no device.
  - Quiet children are guaranteed turns.
  - Watch for shyness when reading in front of others; reading at the teacher's desk helps.
- **The rest of the class:** while the teacher listens, the others need something to do. This matters in multi-grade rooms, where most classes have two or more grades. The brief should suggest a short independent task; test this in the proxy sessions.
- **Teachers:**
  - 5–8 minutes on 3–5 days a week, as part of the reading period.
  - Works offline, uploads later.
  - The brief arrives as a voice note.
  - Whether that's acceptable is the key test for 24 Oct.

## What the jury is likely to ask
| Juror's lens | Likely question | Our answer |
|---|---|---|
| ASER / TaRL (Pratham) | How is this different from PadhAI or the ASER tool? | SUNO doesn't replace the term test. It is lesson-linked and continuous, it tells the teacher tomorrow's groups in TaRL levels, and it shows proof clips. |
| FLN measurement (Gates Foundation) | How accurate is it against human raters? Do you measure understanding? | F2 agreement with ASER labels; a comprehension test; claims only above a measured precision gate. |
| State systems (Samagra) | Is this yet another app? How does it reach scale? | The roadmap feeds the state's weekly assessment and VSK/WhatsApp channels; no new data entry. |
| Anthropic | Why Claude? What are the guardrails? | Error diagnosis, meaning judgment and the Hindi brief; code verifies everything; tested adversarial cases. |
| Product / investors (Udhyam, Suyash) | Will teachers use it? What does it cost? | Teacher test evidence; minutes per day; ₹ per child per year. |
| CSF / IIT Delhi | Does it fit the FLN mission and teacher guides? How deep is the tech? | Lesson-linked items from the teacher guide; the evaluation harness in the repo. |

## Recommendation: what SUNO becomes
**"SUNO listens to a 5-minute reading round and tells the teacher, by tomorrow morning, who is stuck on what, and what to do."**

| Keep | Change | Drop |
|---|---|---|
| Hindi reading, Grade 1–2; voice-first Hindi brief; Claude for diagnosis and the brief; code-computed confidence and gate; Silence Ledger; teacher's reaction as an extra signal; no teacher score | Ambient listening becomes a planned, app-led reading round (one start a day). Add one meaning question per turn. Add a class-level "move on or reteach" for the current lesson. Show ASER/TaRL levels and teacher-guide competencies. "No tests" becomes "no test days: 90 seconds a child, inside the reading period" | Recording whole lessons; voice matching; per-child taps during normal teaching |

Numeracy is the organisers' own example ("knows numbers but struggles with addition"), and spoken numbers are easier for speech-to-text. A maths ladder makes a strong roadmap item, but adding it before 1 Nov risks the build.

## Before building more (next 3 days)
1. **F2**, with the Sarvam key: can it tell right from wrong on real child words close to the phone?
2. **Understanding test:** 10 short spoken answers to a meaning question (role-played by adults if needed), judged by Claude vs. a human.
3. **Paper prototype with 2–3 teachers** before or on 24 Oct. Show a sample brief and the class grid, then check:
   - Can they say who needs what?
   - How long does that take?
   - Would they run a 5-minute round three days a week, and in which period?
4. **Proxy session with 4–5 children:** time the 90-second ladder, and watch what the rest of the room does.

## Risks that remain
- **Teacher habit.** This is the largest risk; no technology fixes it.
- **Children's speech recognition.** F2 measures this.
- **Overlap with existing tools,** which drags on the innovation score. The differentiators above must be visible in the demo, not just claimed.
- **The broken Ideate promise.** We said "no extra teacher time". We change it because of evidence, and the deck should show F1 and this model as the reason.
