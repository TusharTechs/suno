# SUNO: roadmap, integration and validation

27 Oct 2026. Source material for the Build deck's roadmap slides (10% of the score: "clarity on intended pathways to further development of the product, and integration into existing systems").

## Where SUNO fits

SUNO is not another assessment app. PadhAI, TARA, Vaachan Samiksha and NIPUN Lakshya are assessment events: a child reads into a device, one at a time. SUNO has no test and records no child's voice. It turns what the teacher already notices into checked, per-child evidence, and tells her the next morning whom to listen to and what to do.

The two kinds of tool fit together:
- an assessment result (a term-end ORF score, a NIPUN spot check) can seed a child's starting level on SUNO's ladder;
- SUNO's daily evidence tells the teacher what to do between assessments.

## Phase 1: November 2026, classroom pilot and validation (before the 18 Nov finale)

- **Classrooms:**
  - 3–5 Grade 1–3 teachers in Hindi-medium government schools, for two weeks, through the Madhi Foundation and other mentor introductions.
  - Head teacher's written permission; parents informed at an SMC meeting.
- **Validation design** (agreed before any data is seen):
  - **Question:** does SUNO's level for a child agree with an independent ASER-style one-to-one check?
  - **Children:** the 20–30 children with a level SUNO is sure of after two weeks, plus 10 it is not yet sure of (to check that "not enough evidence" is honest).
  - **Reference:** a trained volunteer, who doesn't know SUNO's level, runs the ASER reading tool (letter → word → paragraph → story) and the number tool one-to-one, in the same week.
  - **Measures:**
    - agreement by level (exact, within one);
    - precision of "needs support" (how many flagged children the ASER check confirms);
    - how many children SUNO calls "not enough evidence" whom ASER places clearly.
    - Report counts, not κ: the sample is small.
  - **What would change the design:** if agreement within one level falls below 80%, raise the naming threshold, and look at which skills disagree.
- **Teacher measures:** time to set up a class, seconds per note, notes per week, briefs listened to, and what they say unprompted.
- **Already in place:** the scorer (`eval/real_notes/score.py`), the simulation (`eval/sim/`), and the evidence page.

## Phase 2: early 2027, one block, the channel teachers already use

- **WhatsApp voice notes.**
  - The teacher sends her 60-second note to a SUNO number, the way she already sends voice notes all day, and the morning brief comes back as a voice note.
  - The web app stays for the class view and setup.
  - Udhyam and Samagra both run teacher-facing WhatsApp bots; the pipeline is unchanged and only the input and output change.
- **Block dashboard (VSK-style):**
  - aggregate counts of children by level per school and grade (`/api/export/summary.json`);
  - **no names, no teacher field, no ranking of teachers**;
  - the cluster resource person sees which schools need reading support, not who taught badly.
- **State-owned speech:**
  - optional AI4Bharat IndicConformer (open weights) or Bhashini instead of Sarvam, so a state can own the speech stack;
  - the code already isolates speech-to-text in one module (`server/pipeline/asr.py`).
- **Starting levels from existing assessments:** import NIPUN Lakshya or school ORF results to seed each child's level, so SUNO starts informed rather than at zero.

## Phase 3: 2027–28, state adoption

- **A SUNO module inside an existing state app** (NIPUN Lakshya in UP, or DIKSHA), not a separate app on the teacher's phone. The open JSON schemas (`schemas/`) and the export make this an integration, not a migration.
- **More languages:** Marathi, Tamil (with the Madhi Foundation's context) and Odia, each with its own skill ladder and activity bank in `config/`.
- **The teacher guide's own activities:** replace the placeholder activity bank with the state teacher guide's activities, retrieved by skill.
- **Coaching, with consent only:** a teacher can choose to share her class's progress (never her own performance) with a cluster mentor.

## Cost and who pays

- **Today:** about ₹15.5 per teacher per school day, about ₹103 per child per year (`eval/results/cost.md`, from logged usage).
- **Leaner configuration** (overnight batch processing, a lower-effort brief): estimated at about half that.
- **Who pays:** the state, as part of the Samagra Shiksha FLN budget for teacher support and assessment. SUNO is the state's processor; the school or state owns the data (DPDP Act 2023 and Rules 2025).

## Risks we are watching

| Risk | What we do |
|---|---|
| Teachers stop sending notes after the first week | One 60-second note pays back the next morning; a skipped day breaks nothing; WhatsApp in phase 2; measured in the pilot |
| A teacher's impression is wrong | Opinions never become evidence; the listening list asks for specific words from specific children; ASER validation in phase 1 |
| Seen as surveillance | No teacher score anywhere; the teacher is the only person who sees names; aggregates only, never teacher rankings |
| Speech-to-text erases a child's mistake | A code check (decision 23); evidence needs a specific word (decision 32) |
| Children's data | No child's voice is ever recorded; first names only; delete-class in the app; the school or state owns the data |
