"""SQLite storage. One file (var/suno.db), no server to run.

Privacy by design:
- No audio is stored. The teacher's voice note is transcribed and dropped.
- No child's voice is ever recorded. A child is a first name and a roll number.
- There is no teacher score or teacher-performance field anywhere.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAR = Path(os.environ.get("SUNO_VAR", ROOT / "var"))
DB_PATH = VAR / "suno.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
  class_id TEXT PRIMARY KEY, name TEXT NOT NULL, grade INTEGER, school TEXT,
  roster_json TEXT NOT NULL, lesson_json TEXT NOT NULL,
  day_offset INTEGER NOT NULL DEFAULT 0,      -- demo only: "next morning" moves the class clock
  synthetic INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  note_id TEXT PRIMARY KEY, class_id TEXT NOT NULL, day TEXT NOT NULL, created_at TEXT NOT NULL,
  source TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
  transcript TEXT, sentences_json TEXT, listening_json TEXT, seconds REAL,
  claude_json TEXT, problems_json TEXT, follow_ups_json TEXT, usage_json TEXT, timings_json TEXT,
  synthetic INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS records (
  rec_id INTEGER PRIMARY KEY AUTOINCREMENT, note_id TEXT NOT NULL, class_id TEXT NOT NULL, day TEXT NOT NULL,
  mention_id TEXT, name_said TEXT, child_id TEXT, kind TEXT, skill_code TEXT, item TEXT, outcome TEXT,
  error_type TEXT, when_ TEXT, home_language TEXT, teacher_quote TEXT, rationale TEXT,
  attribution TEXT, candidates_json TEXT, signals_json TEXT, confidence REAL, status TEXT,
  feedback TEXT
);
CREATE TABLE IF NOT EXISTS questions (
  q_id INTEGER PRIMARY KEY AUTOINCREMENT, note_id TEXT NOT NULL, class_id TEXT NOT NULL,
  mention_id TEXT, type TEXT, name_said TEXT, candidates_json TEXT,
  answer TEXT, answered_at TEXT
);
CREATE TABLE IF NOT EXISTS briefs (
  class_id TEXT NOT NULL, day TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
  picture_json TEXT, brief_json TEXT, problems_json TEXT, audio_file TEXT, error TEXT, usage_json TEXT,
  PRIMARY KEY (class_id, day)
);
CREATE INDEX IF NOT EXISTS records_class ON records(class_id, day);
CREATE INDEX IF NOT EXISTS notes_class ON notes(class_id, day);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        VAR.mkdir(parents=True, exist_ok=True)
        (VAR / "audio").mkdir(exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
    return _conn


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in db().execute(sql, args).fetchall()]


def x(sql: str, args: tuple = ()) -> int:
    with _lock:
        cur = db().execute(sql, args)
        return cur.lastrowid


def j(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---- classes ---------------------------------------------------------------

def create_class(name: str, grade: int, school: str, roster: list[dict], lesson: dict,
                 synthetic: bool = False, class_id: str | None = None) -> str:
    cid = class_id or new_id("cls")
    x("INSERT INTO classes VALUES (?,?,?,?,?,?,?,?,?)",
      (cid, name, grade, school, j(roster), j(lesson), 0, int(synthetic), now()))
    return cid


def get_class(class_id: str) -> dict | None:
    rows = q("SELECT * FROM classes WHERE class_id=?", (class_id,))
    if not rows:
        return None
    c = rows[0]
    c["roster"] = json.loads(c.pop("roster_json"))
    c["lesson"] = json.loads(c.pop("lesson_json"))
    return c


def set_day_offset(class_id: str, offset: int) -> None:
    x("UPDATE classes SET day_offset=? WHERE class_id=?", (offset, class_id))


def update_roster(class_id: str, roster: list[dict]) -> None:
    x("UPDATE classes SET roster_json=? WHERE class_id=?", (j(roster), class_id))


# ---- notes and records -----------------------------------------------------

def create_note(class_id: str, day: str, source: str, listening: list[dict], synthetic: bool = False) -> str:
    nid = new_id("note")
    x("INSERT INTO notes (note_id, class_id, day, created_at, source, status, listening_json, synthetic) "
      "VALUES (?,?,?,?,?,?,?,?)", (nid, class_id, day, now(), source, "queued", j(listening), int(synthetic)))
    return nid


def update_note(note_id: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = tuple(j(v) if k.endswith("_json") else v for k, v in fields.items())
    x(f"UPDATE notes SET {cols} WHERE note_id=?", vals + (note_id,))


def get_note(note_id: str) -> dict | None:
    rows = q("SELECT * FROM notes WHERE note_id=?", (note_id,))
    if not rows:
        return None
    n = rows[0]
    for k in list(n):
        if k.endswith("_json"):
            n[k[:-5]] = json.loads(n.pop(k)) if n[k] else None
    return n


def list_notes(class_id: str) -> list[dict]:
    return q("SELECT note_id, day, created_at, source, status, error, transcript, seconds, synthetic "
             "FROM notes WHERE class_id=? ORDER BY day DESC, created_at DESC", (class_id,))


RECORD_FIELDS = ["mention_id", "name_said", "child_id", "kind", "skill_code", "item", "outcome", "error_type",
                 "when", "home_language", "teacher_quote", "rationale", "attribution", "candidates", "signals",
                 "confidence", "status"]


def add_records(note_id: str, class_id: str, day: str, records: list[dict]) -> None:
    for r in records:
        x("INSERT INTO records (note_id, class_id, day, mention_id, name_said, child_id, kind, skill_code, item, "
          "outcome, error_type, when_, home_language, teacher_quote, rationale, attribution, candidates_json, "
          "signals_json, confidence, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (note_id, class_id, day, r["mention_id"], r["name_said"], r["child_id"], r["kind"], r["skill_code"],
           r["item"], r["outcome"], r["error_type"], r["when"], r["home_language"], r["teacher_quote"],
           r["rationale"], r["attribution"], j(r["candidates"]), j(r["signals"]), r["confidence"], r["status"]))


def _record(row: dict) -> dict:
    row["when"] = row.pop("when_")
    row["candidates"] = json.loads(row.pop("candidates_json") or "[]")
    row["signals"] = json.loads(row.pop("signals_json") or "null")
    return row


def records(class_id: str, note_id: str | None = None) -> list[dict]:
    if note_id:
        rows = q("SELECT * FROM records WHERE note_id=? ORDER BY rec_id", (note_id,))
    else:
        rows = q("SELECT * FROM records WHERE class_id=? ORDER BY day, rec_id", (class_id,))
    return [_record(r) for r in rows]


def get_record(rec_id: int) -> dict | None:
    rows = q("SELECT * FROM records WHERE rec_id=?", (rec_id,))
    return _record(rows[0]) if rows else None


def update_record(rec_id: int, **fields) -> None:
    mapping = {"when": "when_", "candidates": "candidates_json", "signals": "signals_json"}
    cols = ", ".join(f"{mapping.get(k, k)}=?" for k in fields)
    vals = tuple(j(v) if k in ("candidates", "signals") else v for k, v in fields.items())
    x(f"UPDATE records SET {cols} WHERE rec_id=?", vals + (rec_id,))


def add_questions(note_id: str, class_id: str, questions: list[dict]) -> list[int]:
    return [x("INSERT INTO questions (note_id, class_id, mention_id, type, name_said, candidates_json) VALUES (?,?,?,?,?,?)",
          (note_id, class_id, qq["mention_id"], qq["type"], qq["name_said"], j(qq["candidates"])))
            for qq in questions]


def questions(class_id: str, note_id: str | None = None, open_only: bool = False) -> list[dict]:
    sql, args = "SELECT * FROM questions WHERE class_id=?", [class_id]
    if note_id:
        sql += " AND note_id=?"
        args.append(note_id)
    if open_only:
        sql += " AND answered_at IS NULL"
    rows = q(sql + " ORDER BY q_id", tuple(args))
    for r in rows:
        r["candidates"] = json.loads(r.pop("candidates_json") or "[]")
    return rows


def answer_question(q_id: int, answer: str) -> None:
    x("UPDATE questions SET answer=?, answered_at=? WHERE q_id=?", (answer, now(), q_id))


# ---- briefs ----------------------------------------------------------------

def get_brief(class_id: str, day: str) -> dict | None:
    rows = q("SELECT * FROM briefs WHERE class_id=? AND day=?", (class_id, day))
    if not rows:
        return None
    b = rows[0]
    for k in list(b):
        if k.endswith("_json"):
            b[k[:-5]] = json.loads(b.pop(k)) if b[k] else None
    return b


def put_brief(class_id: str, day: str, **fields) -> None:
    existing = get_brief(class_id, day)
    if existing is None:
        x("INSERT INTO briefs (class_id, day, created_at, status) VALUES (?,?,?,?)", (class_id, day, now(), "queued"))
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = tuple(j(v) if k.endswith("_json") else v for k, v in fields.items())
        x(f"UPDATE briefs SET {cols} WHERE class_id=? AND day=?", vals + (class_id, day))


def delete_brief(class_id: str, day: str) -> None:
    x("DELETE FROM briefs WHERE class_id=? AND day=?", (class_id, day))
