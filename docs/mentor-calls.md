# Mentor calls

Each call is 30–40 minutes. Full prep docs, with every question written as problem, plan, and what we need:
- Technical: https://claude.ai/code/artifact/9058f84b-db0c-4071-813a-3291dadfc545
- Education: https://claude.ai/code/artifact/3130f8ca-6665-4fc8-a90b-962bf60564ab

## Technical: Saurabh Deshpande, Head of AI Research, NVIDIA
**20 Oct 2026, 7:30 pm IST.**

**Open with our two worries.**
1. Can a phone hear and attribute each child at classroom distances?
2. How do we get real data in time?

**Ask first:** T3, T4, T1, T7. If the call is cut to 10 minutes: T1, T3, T7.

**Extra questions on the two worries:**
1. Can one phone mic hear a child 5–7 m away in a noisy classroom well enough for Hindi ASR? What signal-to-noise ratio do Sarvam or IndicConformer need?
2. Teacher-worn vs desk: how bad is clothing rustle? Can a phone's two mics, recorded in stereo, give the direction of a voice?
3. Which noise cleaning helps distant child speech without hurting recognition: NVIDIA's tools or DeepFilterNet?
4. Would he trust simulated-room results validated on a small real set? How should we design the distance experiment?

**Question index:**
- T1: judges' test path
- T2: test data in 10 days
- T3: ASR engine and answer checking
- T4: separating teacher, chorus and one child
- T5: calibrated confidence
- T6: guardrails and adversarial tests
- T7: scope for 1 Nov
- T8: children's data and privacy
- T9: Claude pipeline, models and credits
- T10: Android recording reliability
- T11: tracker and planner
- T12: evaluations the judges trust
- T13: making the AI legible in the repo

## Education: Rebecca Swittens, Senior Manager FLN, Madhi Foundation (Tamil Nadu state FLN mission)
**28 Oct 2026, 5 pm IST.** Send the pre-read by 5 pm on 27 Oct.

This call is four days before the deadline, so it can't unblock the build:
- Start classroom access and consent outreach yourselves now.
- **Open with a 5-minute live demo.** Her reaction counts as user feedback.
- **Order:** E2, E7, E6, E11, E3, E4, E1, E5.
- **Ask for introductions for on-ground testing between 1 and 18 Nov.** The finale deck asks for real-data testing.
- Her context is Tamil Nadu; ours is Hindi. Ask what carries across.

**Question index:**
- E1: classrooms and finale testing
- E2: does lesson talk hold the evidence?
- E3: teacher trust
- E4: consent and safeguarding
- E5: skills SUNO can honestly detect
- E6: evidence that convinces the jury
- E7: brief format
- E8: calling on quiet children
- E9: absence and two grades in one room
- E10: language or concept?
- E11: who adopts SUNO
- E12: telling the story to education judges

## Report template (paste into Claude Code)
```
Mentor call report:
- Mentor / date:
- Q-ID (e.g. T3) — what they said — our decision — design change (if any)
- Q-ID — ...
- Introductions or offers they made:
- New risks they raised:
- Follow-ups we promised:
```

## Status
| Call | Done | Report logged in decisions.md |
| --- | --- | --- |
| Technical, 20 Oct | [x] | [x] |
| Education, 28 Oct | [x] | [x] |
