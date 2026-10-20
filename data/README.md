# Data

Real recordings and personal data **never** go into git. `raw/`, `external/` and `consents/` are git-ignored.

| Folder | What goes here | Licence and notes |
| --- | --- | --- |
| `external/aser/` | [Pratham ASER dataset](https://github.com/PrathamOrg/ASER-Dataset): 5,301 child reading recordings (Hindi, Marathi, English), labelled right or wrong | CC BY-NC-SA 4.0. Non-commercial; credit Pratham |
| `external/hiacc/` | [HiACC](https://zenodo.org/records/15551669): 2 hours of Hinglish child speech, phone-recorded in a school | CC BY-NC 4.0 |
| `raw/<session-id>/` | Our recordings: home distance test, proxy sessions, role-play lessons | Consented. Keep a consent record for each child, offline |
| `labels/` | Moment-level labels, one CSV per session (see `labels_template.csv`) | No surnames |
| `consents/` | Scans of signed consent forms | Better kept off the laptop entirely |
| `../samples/synthetic/` | Synthetic lessons for the judges' demo | Always labelled synthetic; safe to commit |

Labelling: one row per question–answer moment. `speaker` is one of `teacher`, `child:<first name>`, `chorus` or `unknown`. `correct` is one of `yes`, `no` or `partial`.
