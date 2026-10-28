"""Storage: SQLite on a laptop (var/suno.db), Postgres when SUNO_DATABASE_URL is set (hosted).

The same SQL runs on both: `?` placeholders are rewritten for Postgres, and the two schema
differences (auto-increment ids, binary columns) are handled here.

Privacy by design:
- No voice note is stored. The teacher's voice note is transcribed and dropped.
- No child's voice is ever recorded. A child is a first name and a roll number.
- There is no teacher score or teacher-performance field anywhere.
- The only audio kept is SUNO's own spoken brief (text-to-speech), so it plays offline.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAR = Path(os.environ.get("SUNO_VAR", ROOT / "var"))
DB_PATH = VAR / "suno.db"
PG_URL = os.environ.get("SUNO_DATABASE_URL", "")
PG = PG_URL.startswith(("postgres://", "postgresql://"))
DEMO_KEEP_HOURS = 48   # demo sandboxes are deleted after two days

SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
  class_id TEXT PRIMARY KEY, name TEXT NOT NULL, grade INTEGER, school TEXT,
  roster_json TEXT NOT NULL, lesson_json TEXT NOT NULL,
  day_offset INTEGER NOT NULL DEFAULT 0,      -- demo only: "next morning" moves the class clock
  synthetic INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, code TEXT
);
CREATE TABLE IF NOT EXISTS notes (
  note_id TEXT PRIMARY KEY, class_id TEXT NOT NULL, day TEXT NOT NULL, created_at TEXT NOT NULL,
  source TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
  transcript TEXT, sentences_json TEXT, listening_json TEXT, seconds REAL,
  claude_json TEXT, problems_json TEXT, follow_ups_json TEXT, usage_json TEXT, timings_json TEXT,
  synthetic INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS records (
  rec_id SERIALID, note_id TEXT NOT NULL, class_id TEXT NOT NULL, day TEXT NOT NULL,
  mention_id TEXT, name_said TEXT, child_id TEXT, kind TEXT, skill_code TEXT, item TEXT, outcome TEXT,
  error_type TEXT, when_ TEXT, home_language TEXT, teacher_quote TEXT, rationale TEXT,
  attribution TEXT, candidates_json TEXT, signals_json TEXT, confidence REAL, status TEXT,
  feedback TEXT, share TEXT
);
CREATE TABLE IF NOT EXISTS questions (
  q_id SERIALID, note_id TEXT NOT NULL, class_id TEXT NOT NULL,
  mention_id TEXT, type TEXT, name_said TEXT, candidates_json TEXT,
  answer TEXT, answered_at TEXT
);
CREATE TABLE IF NOT EXISTS briefs (
  class_id TEXT NOT NULL, day TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
  picture_json TEXT, brief_json TEXT, problems_json TEXT, audio_file TEXT, error TEXT, usage_json TEXT,
  audio BLOBTYPE,
  PRIMARY KEY (class_id, day)
);
CREATE INDEX IF NOT EXISTS records_class ON records(class_id, day);
CREATE INDEX IF NOT EXISTS notes_class ON notes(class_id, day);
"""

_lock = threading.RLock()
_conn = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect():
    if PG:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(PG_URL, autocommit=True, row_factory=dict_row)
        ddl = SCHEMA.replace("SERIALID", "BIGSERIAL PRIMARY KEY").replace("BLOBTYPE", "BYTEA") \
                    .replace(" REAL", " DOUBLE PRECISION")
        for stmt in [x.strip() for x in ddl.split(";") if x.strip()]:
            conn.execute(stmt)
        conn.execute("ALTER TABLE classes ADD COLUMN IF NOT EXISTS code TEXT")
        conn.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS share TEXT")
        return conn
    VAR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA.replace("SERIALID", "INTEGER PRIMARY KEY AUTOINCREMENT").replace("BLOBTYPE", "BLOB"))
    for ddl in ("ALTER TABLE classes ADD COLUMN code TEXT", "ALTER TABLE records ADD COLUMN share TEXT"):
        try:
            conn.execute(ddl)  # databases made before these columns
        except sqlite3.OperationalError:
            pass
    return conn


def db():
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def _run(sql: str, args: tuple):
    """Execute with one reconnect: a free hosted Postgres drops idle connections."""
    global _conn
    if PG:
        sql = sql.replace("?", "%s")
    for attempt in (0, 1):
        try:
            return db().execute(sql, args)
        except Exception as e:  # psycopg.OperationalError, or a closed connection
            dropped = any(w in str(e).lower() for w in ("closed", "terminat", "connection"))
            if not PG or attempt or not dropped:
                raise
            _conn = None


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _run(sql, args).fetchall()]


def x(sql: str, args: tuple = (), returning: str | None = None):
    with _lock:
        if returning and PG:
            return _run(sql + f" RETURNING {returning}", args).fetchone()[returning]
        cur = _run(sql, args)
        return cur.lastrowid if returning else None


def since_today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def count_today(table: str, class_id: str) -> int:
    assert table in ("notes", "briefs")
    return q(f"SELECT COUNT(*) AS n FROM {table} WHERE class_id=? AND created_at >= ?",
             (class_id, since_today_utc()))[0]["n"]


def cleanup_demo() -> int:
    """Delete demo sandboxes (synthetic classes) older than DEMO_KEEP_HOURS, and everything in them."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=DEMO_KEEP_HOURS)).isoformat(timespec="seconds")
    old = [r["class_id"] for r in q("SELECT class_id FROM classes WHERE synthetic=1 AND created_at < ?", (cutoff,))]
    for cid in old:
        for t in ("records", "questions", "notes", "briefs", "classes"):
            x(f"DELETE FROM {t} WHERE class_id=?", (cid,))
    return len(old)


def j(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---- classes ---------------------------------------------------------------

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L: easy to read out on the phone


def new_code() -> str:
    import secrets
    while True:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = f"{raw[:4]}-{raw[4:]}"
        if not q("SELECT 1 FROM classes WHERE code=?", (code,)):
            return code


def create_class(name: str, grade: int, school: str, roster: list[dict], lesson: dict,
                 synthetic: bool = False, class_id: str | None = None) -> str:
    cid = class_id or new_id("cls")
    x("INSERT INTO classes (class_id, name, grade, school, roster_json, lesson_json, day_offset, synthetic, created_at, code) "
      "VALUES (?,?,?,?,?,?,?,?,?,?)",
      (cid, name, grade, school, j(roster), j(lesson), 0, int(synthetic), now(), None if synthetic else new_code()))
    return cid


def class_by_code(code: str) -> str | None:
    c = code.strip().upper().replace(" ", "")
    if len(c) == 8:
        c = f"{c[:4]}-{c[4:]}"
    rows = q("SELECT class_id FROM classes WHERE code=?", (c,))
    return rows[0]["class_id"] if rows else None


def update_lesson(class_id: str, lesson: dict) -> None:
    x("UPDATE classes SET lesson_json=? WHERE class_id=?", (j(lesson), class_id))


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
                 "confidence", "status", "share"]


def add_records(note_id: str, class_id: str, day: str, records: list[dict]) -> None:
    for r in records:
        x("INSERT INTO records (note_id, class_id, day, mention_id, name_said, child_id, kind, skill_code, item, "
          "outcome, error_type, when_, home_language, teacher_quote, rationale, attribution, candidates_json, "
          "signals_json, confidence, status, share) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (note_id, class_id, day, r["mention_id"], r["name_said"], r["child_id"], r["kind"], r["skill_code"],
           r["item"], r["outcome"], r["error_type"], r["when"], r["home_language"], r["teacher_quote"],
           r["rationale"], r["attribution"], j(r["candidates"]), j(r["signals"]), r["confidence"], r["status"],
           r.get("share")))


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
              (note_id, class_id, qq["mention_id"], qq["type"], qq["name_said"], j(qq["candidates"])), returning="q_id")
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

BRIEF_COLS = "class_id, day, created_at, status, picture_json, brief_json, problems_json, audio_file, error, usage_json"


def get_brief_audio(class_id: str, day: str) -> bytes | None:
    rows = q("SELECT audio FROM briefs WHERE class_id=? AND day=?", (class_id, day))
    return bytes(rows[0]["audio"]) if rows and rows[0]["audio"] is not None else None


def get_brief(class_id: str, day: str) -> dict | None:
    rows = q(f"SELECT {BRIEF_COLS} FROM briefs WHERE class_id=? AND day=?", (class_id, day))
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


def delete_note(note_id: str) -> None:
    for t in ("records", "questions", "notes"):
        x(f"DELETE FROM {t} WHERE note_id=?", (note_id,))


def delete_brief(class_id: str, day: str) -> None:
    x("DELETE FROM briefs WHERE class_id=? AND day=?", (class_id, day))
