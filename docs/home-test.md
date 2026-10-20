# Home test: can a phone tell who answered? (F1-real)

The technical mentor's request on 20 Oct: before building anything else, check with a real recording that SUNO can tell which person answered. This takes about 45 minutes with 3–5 people. Adults are fine for a first run; children aged 6–8 (with parents' written consent) are the real test.

## What you need
- 3–5 people: one plays the teacher, the rest play children. More people makes the test harder and more honest.
- Two phones, both recording with the built-in voice recorder app:
  - **worn:** in the "teacher's" shirt pocket or on a lanyard
  - **desk:** on a table at the front
- The biggest room you have, a fan on, and some background noise (a classroom-noise video on a laptop at the back, at a moderate volume).
- A Grade 2 Hindi page with 20–30 single words.

## Steps
1. **Voice samples (enrolment), 2 minutes.** Each "child" holds the worn phone about 30 cm from their mouth and reads a short paragraph for about 20 seconds, in a quiet moment. Save one file per person as `data/raw/<session>/enrol/<name>.m4a`. Use first names only.
2. **Seat the "children"** at 1, 2, 4 and 6 m from the teacher. Swap seats halfway so everyone answers from more than one distance.
3. **Start both phones recording**, then clap once loudly: the clap helps line up the two recordings.
4. **Teach for 10–15 minutes as normal.** Call on people to read one word each, about 40 answers in total. Mix it up:
   - call some by name, and only point at others ("haan, tum batao")
   - let people answer wrongly sometimes, and react naturally ("shabaash", "phir se")
   - include a few chorus answers ("sab log bolo")
   - if two people share a first name, even better
5. **Stop both recordings.** Copy them to `data/raw/<session>/phone_worn.m4a` and `phone_desk.m4a`.
6. **Label the answers (about 15 minutes).** Open `phone_worn.m4a` in Audacity, select each single-person answer, and add a label `<name>@<distance>` (for example `asha@4`). Skip the teacher and the chorus answers. Then use *File → Export → Export Labels* to save `data/raw/<session>/labels.txt`.
7. **Score it:**

```bash
uv run --group speech python eval/feasibility/home_test.py data/raw/<session> --labelled-on worn
```

It prints, for each phone and distance, how many answers were matched to the right person. It also writes `eval/results/home_<session>.md`.

## Rules
- `data/raw/` is git-ignored. Never commit recordings, names or consent forms.
- With children: get parents' written consent first, and the child's own okay. Keep their voices out of anything public.
- Write down anything surprising (a child too shy to answer from far away, the teacher forgetting to say names). It goes in `docs/decisions.md`.
