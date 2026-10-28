"""SUNO web API and the teacher web app (served from web/).

Run locally:  uv run uvicorn server.api:app --reload
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import demo, jobs, store
from .pipeline import brief as brief_mod
from .pipeline import claude_observations, planner
from .pipeline import lesson_photo as lesson_photo_mod
from .pipeline import roster_photo as roster_photo_mod
from .pipeline.claude_client import ClaudeOutputError
from .pipeline.roster_photo import first_name_only
from .pipeline.config import ACTIVITIES, SKILLS
from .pipeline.guardrails import mask_banned, settle_attribution

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("suno.api")

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DEMO_CODE = os.environ.get("SUNO_DEMO_CODE", "SUNO-DEMO").upper()
NOTES_PER_DAY = int(os.environ.get("SUNO_NOTES_PER_DAY", "25"))      # per class: keeps an open demo from burning credits
BRIEFS_PER_DAY = int(os.environ.get("SUNO_BRIEFS_PER_DAY", "12"))
MAX_UPLOAD = 8 * 1024 * 1024
MAX_TEXT = 3000

@asynccontextmanager
async def lifespan(_app):
    try:
        n = store.cleanup_demo()
        if n:
            log.info("removed %d demo sandboxes older than %d h", n, store.DEMO_KEEP_HOURS)
    except Exception:
        log.exception("demo cleanup failed")
    yield


app = FastAPI(title="SUNO", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


# ---- sessions: a signed class id in a cookie ---------------------------------

def _secret() -> bytes:
    env = os.environ.get("SESSION_SECRET")
    if env:
        return env.encode()
    f = store.VAR / "session_secret"
    store.VAR.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def _sign(class_id: str) -> str:
    return class_id + "." + hmac.new(_secret(), class_id.encode(), hashlib.sha256).hexdigest()[:32]


def _unsign(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    cid, sig = token.rsplit(".", 1)
    return cid if hmac.compare_digest(_sign(cid), token) else None


def current_class(suno: str | None = Cookie(default=None)) -> dict:
    cid = _unsign(suno)
    c = store.get_class(cid) if cid else None
    if not c:
        raise HTTPException(401, "not signed in")
    return c


def _set_session(resp: Response, class_id: str) -> None:
    resp.set_cookie("suno", _sign(class_id), max_age=60 * 60 * 24 * 60, httponly=True, samesite="lax",
                    secure=os.environ.get("SUNO_SECURE_COOKIE", "0") == "1")


# ---- helpers ---------------------------------------------------------------

def _names(c: dict) -> dict:
    return {ch["child_id"]: ch for ch in c["roster"]}


def _public_record(r: dict) -> dict:
    out = {k: r[k] for k in ("rec_id", "note_id", "day", "mention_id", "name_said", "child_id", "kind", "skill_code",
                             "item", "outcome", "error_type", "when", "home_language", "rationale", "attribution",
                             "candidates", "signals", "confidence", "status", "feedback")}
    out["teacher_quote"] = mask_banned(r["teacher_quote"] or "")
    return out


def _run(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


def _brief_running(b: dict | None) -> bool:
    return bool(b) and b["status"] in ("queued", "thinking", "speaking") and not store.is_stale(b["created_at"], BRIEF_STALE_S)


def _start_brief(c: dict, day: str, force: bool = False) -> None:
    b = store.get_brief(c["class_id"], day)
    if _brief_running(b):
        return                      # never two jobs for the same brief (and no way round the quota)
    if b and not force and b["status"] == "done":
        return
    if store.count_today("briefs", c["class_id"]) >= BRIEFS_PER_DAY:
        raise HTTPException(429, "brief limit for today reached for this class")
    store.count_use("briefs", c["class_id"])
    store.delete_brief(c["class_id"], day)
    store.put_brief(c["class_id"], day, status="queued")
    _run(jobs.make_brief, c["class_id"], day)


def _note_view_status(n: dict) -> tuple[str, str | None]:
    """A note still 'processing' long after it started was interrupted: show it as failed, with a reason."""
    if n["status"] in ("queued", "transcribing", "thinking") and store.is_stale(n["created_at"], NOTE_STALE_S):
        return "failed", "processing was interrupted (the server restarted); please send the note again"
    return n["status"], n["error"]


def settle_question(class_id: str, q_id: int, answer: str) -> None:
    """The teacher tapped which child a name meant (or 'skip'). Code re-scores the mention."""
    qq = next((x for x in store.questions(class_id) if x["q_id"] == q_id), None)
    if qq is None:
        raise HTTPException(404, "no such question")
    c = store.get_class(class_id)
    if answer != "skip" and answer not in _names(c):
        raise HTTPException(400, "not a child in this class")
    rec = next((r for r in store.records(class_id, qq["note_id"]) if r["mention_id"] == qq["mention_id"]), None)
    store.answer_question(q_id, answer)
    if rec is None:
        return
    if answer == "skip":
        store.update_record(rec["rec_id"], status="dismissed")
        return
    r = settle_attribution(rec, answer)
    store.update_record(rec["rec_id"], child_id=r["child_id"], attribution=r["attribution"],
                        confidence=r["confidence"], status=r["status"])


# ---- auth and class ----------------------------------------------------------

class Login(BaseModel):
    code: str


DEMO_PER_HOUR = int(os.environ.get("SUNO_DEMO_PER_HOUR", "30"))
_demo_logins: dict[str, list[float]] = {}
NOTE_STALE_S, BRIEF_STALE_S = 300, 240   # a job this old and unfinished was interrupted (restart, deploy)


def _demo_allowed(ip: str) -> bool:
    """Each demo login makes a sandbox with its own quotas: cap them per address."""
    import time
    now = time.time()
    hits = [h for h in _demo_logins.get(ip, []) if now - h < 3600]
    if len(hits) >= DEMO_PER_HOUR:
        _demo_logins[ip] = hits
        return False
    _demo_logins[ip] = hits + [now]
    return True


@app.post("/api/login")
def login(body: Login, response: Response, request: Request):
    code = body.code.strip()
    if code.upper() == DEMO_CODE:
        if not _demo_allowed(request.client.host if request.client else "?"):
            raise HTTPException(429, "too many demo sessions from this address; try again in an hour")
        cid = demo.clone_demo()
    elif store.class_by_code(code):
        cid = store.class_by_code(code)
    else:
        raise HTTPException(401, "code not recognised")
    _set_session(response, cid)
    return {"class_id": cid}


class NewClass(BaseModel):
    name: str
    grade: int = 2
    names: list[str] = []


def _clean_roster(entries: list[dict], old: list[dict]) -> list[dict]:
    """First names only; existing children keep their ids (their evidence stays theirs)."""
    old_by_id = {c["child_id"]: c for c in old}
    used = {c["child_id"] for c in old}
    next_n = max([int(c["child_id"][1:]) for c in old if c["child_id"][1:].isdigit()] + [0]) + 1
    out, rolls = [], set()
    for i, e in enumerate(entries[:80], 1):
        name = first_name_only(e.get("first_name", ""))
        if not name:
            continue
        cid = e.get("child_id") if e.get("child_id") in old_by_id else None
        if cid is None:
            while f"c{next_n:02d}" in used:
                next_n += 1
            cid = f"c{next_n:02d}"
            used.add(cid)
        roll = e.get("roll_no") if isinstance(e.get("roll_no"), int) and e.get("roll_no") > 0 else None
        if roll is None or roll in rolls:
            roll = max(rolls | {0}) + 1
        rolls.add(roll)
        aliases = [first_name_only(a) for a in (e.get("aliases") or [])][:3]
        entry = {"child_id": cid, "first_name": name, "roll_no": roll, "aliases": [a for a in aliases if a]}
        if cid in old_by_id and old_by_id[cid].get("baseline"):
            entry["baseline"] = old_by_id[cid]["baseline"]
        out.append(entry)
    return out


@app.post("/api/classes")
def create_class(body: NewClass, response: Response):
    roster = _clean_roster([{"first_name": n, "roll_no": i} for i, n in enumerate(body.names, 1)], [])
    lesson = demo.json.loads(demo.CLASS.read_text())["lesson"]  # starts on a sample week; the teacher edits it
    lesson = dict(lesson, title="इस हफ़्ते का पाठ (बदलें)")
    cid = store.create_class(body.name.strip()[:60] or "मेरी कक्षा", max(1, min(body.grade, 5)), "", roster, lesson)
    _set_session(response, cid)
    return {"class_id": cid, "code": store.get_class(cid)["code"]}


class RosterBody(BaseModel):
    children: list[dict]


@app.put("/api/roster")
def put_roster(body: RosterBody, c: dict = Depends(current_class)):
    roster = _clean_roster(body.children, c["roster"])
    if not roster:
        raise HTTPException(400, "add at least one child")
    store.update_roster(c["class_id"], roster)
    return {"roster": roster}


@app.post("/api/roster/photo")
async def roster_photo(photo: UploadFile = File(...), c: dict = Depends(current_class)):
    """Claude reads a photo of the attendance register into a draft list. Nothing is saved here;
    the teacher reviews the list and saves it with PUT /api/roster. The photo is not stored."""
    data = await photo.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "photo too large")
    try:
        return roster_photo_mod.read_register(data, photo.content_type or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except ClaudeOutputError as e:
        raise HTTPException(502, f"could not read the photo: {e}")


class BaselineBody(BaseModel):
    levels: dict[str, dict]   # {child_id: {"hindi": level | None, "maths": level | None}}


@app.put("/api/baseline")
def put_baseline(body: BaselineBody, c: dict = Depends(current_class)):
    """Starting levels from an ASER-style check (letter, word, paragraph, story; numbers). They seed each
    child's ladder and fade like any evidence; the teacher's notes then track progress from there."""
    n = {a["area"]: len(a["levels"]) for a in SKILLS["areas"]}
    day = jobs.class_today(c).isoformat()
    roster = []
    for ch in c["roster"]:
        ch = dict(ch)
        given = body.levels.get(ch["child_id"])
        if given is not None:
            b = {}
            for area in ("hindi", "maths"):
                v = given.get(area)
                if isinstance(v, int) and 0 <= v < n[area]:
                    b[area] = v
            ch["baseline"] = dict(b, day=day) if b else None
        roster.append(ch)
    store.update_roster(c["class_id"], roster)
    return {"ok": True, "children_with_baseline": sum(1 for ch in roster if ch.get("baseline"))}


@app.post("/api/lesson/photo")
async def lesson_photo(photo: UploadFile = File(...), c: dict = Depends(current_class)):
    """Claude reads this week's textbook page into a draft lesson. Nothing is saved here: the teacher
    reviews the items and saves them with PUT /api/lesson. The photo is not stored."""
    data = await photo.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "photo too large")
    try:
        return lesson_photo_mod.read_page(data, photo.content_type or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except ClaudeOutputError as e:
        raise HTTPException(502, f"could not read the photo: {e}")


class LessonBody(BaseModel):
    title: str
    focus_skills: list[str]
    items: dict[str, list[str]]


@app.put("/api/lesson")
def put_lesson(body: LessonBody, c: dict = Depends(current_class)):
    codes = {s["code"] for s in SKILLS["skills"]}
    items = {k: [i.strip()[:40] for i in v if i.strip()][:10] for k, v in body.items.items() if k in codes}
    items = {k: v for k, v in items.items() if v}
    if not items:
        raise HTTPException(400, "add at least one word or sum")
    focus = [f for f in body.focus_skills if f in items] or list(items)
    lesson = {"lesson_id": c["lesson"].get("lesson_id", "week"), "title": body.title.strip()[:80] or "इस हफ़्ते का पाठ",
              "focus_skills": focus, "items": items}
    store.update_lesson(c["class_id"], lesson)
    return {"lesson": lesson}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("suno")
    return {"ok": True}


@app.get("/api/me")
def me(c: dict = Depends(current_class)):
    return {"class_id": c["class_id"], "code": c.get("code"), "name": c["name"], "grade": c["grade"], "school": c["school"],
            "synthetic": bool(c["synthetic"]), "roster": c["roster"], "lesson": c["lesson"],
            "today": jobs.class_today(c).isoformat(), "day_offset": c["day_offset"],
            "skills": SKILLS, "activities": ACTIVITIES}


# ---- today: brief + listening list -----------------------------------------

@app.get("/api/today")
def today(c: dict = Depends(current_class)):
    day = jobs.class_today(c).isoformat()
    b = store.get_brief(c["class_id"], day)
    pic = (b or {}).get("picture") or jobs.morning_picture(c, date.fromisoformat(day))
    open_q = store.questions(c["class_id"], open_only=True)
    return {
        "today": day,
        "listen_today": pic["listen_today"],
        "silent": pic["silent"],
        "needs_support": pic["needs_support"],
        "language_flags": pic["language_flags"],
        "heard_this_week": pic["heard_this_week"],
        "levels": pic.get("levels", {}),
        "class_view": pic.get("class_view", []),
        "brief": None if not b else {
            "status": b["status"] if (b["status"] == "done" or b["status"] == "fallback" or _brief_running(b)) else "fallback",
            "brief": b["brief"],
            "error": b["error"] if (b["status"] in ("done", "fallback") or _brief_running(b)) else "interrupted: the server restarted while building it",
            # the version in the URL makes a rebuilt brief's new voice bypass any cached copy
            "audio_url": f"/api/audio/{b['audio_file']}?v={(b.get('created_at') or '').replace(':', '')}" if b.get("audio_file") else None,
            "problems_fixed": b.get("problems") or [], "usage": b.get("usage")},
        "open_questions": len(open_q),
        "notes_today": [n for n in store.list_notes(c["class_id"]) if n["day"] == day and _note_view_status(n)[0] != "failed"],
    }


@app.post("/api/brief")
def brief(force: bool = False, c: dict = Depends(current_class)):
    _start_brief(c, jobs.class_today(c).isoformat(), force=force)
    return {"ok": True}


@app.get("/api/audio/{name}")
def audio(name: str, c: dict = Depends(current_class)):
    prefix = c["class_id"] + "_"
    if not name.startswith(prefix) or "/" in name or ".." in name or not name.endswith(".mp3"):
        raise HTTPException(404)
    data = store.get_brief_audio(c["class_id"], name[len(prefix):-4])
    if data is None:
        raise HTTPException(404)
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.post("/api/next-day")
def next_day(c: dict = Depends(current_class)):
    """Demo only: move this class to the next school morning and build that morning's brief."""
    if not c["synthetic"]:
        raise HTTPException(403, "only the demo class can move its clock")
    store.set_day_offset(c["class_id"], c["day_offset"] + 1)
    c = store.get_class(c["class_id"])
    day = jobs.class_today(c).isoformat()
    _start_brief(c, day)
    return {"today": day}


# ---- notes -------------------------------------------------------------------

@app.post("/api/notes")
async def add_note(audio: UploadFile | None = File(default=None), text: str | None = Form(default=None),
                   day: str | None = Form(default=None), c: dict = Depends(current_class)):
    today_ = jobs.class_today(c)
    note_day = today_
    if day:  # a note recorded offline on an earlier day keeps its own day
        try:
            note_day = min(date.fromisoformat(day), today_)
        except ValueError:
            raise HTTPException(400, "day must be YYYY-MM-DD")
        if (today_ - note_day).days > 14:
            raise HTTPException(400, "notes older than two weeks are not accepted")
    if store.count_today("notes", c["class_id"]) >= NOTES_PER_DAY:
        raise HTTPException(429, "note limit for today reached for this class")
    store.count_use("notes", c["class_id"])
    data = await audio.read(MAX_UPLOAD + 1) if audio else None
    if data is not None and len(data) > MAX_UPLOAD:
        raise HTTPException(413, "recording too large")
    if data is None and not (text and text.strip()):
        raise HTTPException(400, "send a recording or type the note")
    if text and len(text) > MAX_TEXT:
        raise HTTPException(413, "note too long")
    b = store.get_brief(c["class_id"], note_day.isoformat())
    pic = (b or {}).get("picture") or jobs.morning_picture(c, note_day)
    nid = store.create_note(c["class_id"], note_day.isoformat(), "audio" if data else "text", pic["listen_today"])
    _run(jobs.process_note, nid, data, None if data else text)
    return {"note_id": nid}


@app.get("/api/notes")
def notes(c: dict = Depends(current_class)):
    out = []
    for n in store.list_notes(c["class_id"]):
        st, err = _note_view_status(n)
        out.append(dict(n, status=st, error=err, transcript=mask_banned(n["transcript"] or "")))
    return out


@app.get("/api/notes/{note_id}")
def note(note_id: str, c: dict = Depends(current_class)):
    n = store.get_note(note_id)
    if not n or n["class_id"] != c["class_id"]:
        raise HTTPException(404)
    st, err = _note_view_status(n)
    return {
        "note_id": n["note_id"], "day": n["day"], "status": st, "error": err,
        "source": n["source"], "transcript": mask_banned(n["transcript"] or ""), "seconds": n["seconds"],
        "sentences": _masked(n["sentences"]), "follow_ups": n["follow_ups"] or [], "listening": n["listening"] or [],
        "records": [_public_record(r) for r in store.records(c["class_id"], note_id)],
        "questions": store.questions(c["class_id"], note_id),
        "synthetic": bool(n["synthetic"]),
    }


@app.get("/api/notes/{note_id}/trace")
def trace(note_id: str, c: dict = Depends(current_class)):
    """Everything SUNO did with one note: transcript, Claude's raw output, each code check and score."""
    n = store.get_note(note_id)
    if not n or n["class_id"] != c["class_id"]:
        raise HTTPException(404)
    return {
        "note_id": note_id, "day": n["day"], "status": n["status"], "transcript": mask_banned(n["transcript"] or ""),
        "sentences": _masked(n["sentences"]), "listening": n["listening"], "claude_output": n["claude"],
        "code_checks": n["problems"] or [], "records": [_public_record(r) for r in store.records(c["class_id"], note_id)],
        "questions": store.questions(c["class_id"], note_id), "usage": n["usage"], "timings": n["timings"],
        "prompt_file": "prompts/" + (n["usage"] or {}).get("prompt", claude_observations.PROMPT),
        "schema_file": "schemas/" + claude_observations.SCHEMA,
    }


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str, c: dict = Depends(current_class)):
    """The teacher can delete a note she didn't mean to send; its observations go with it."""
    n = store.get_note(note_id)
    if not n or n["class_id"] != c["class_id"]:
        raise HTTPException(404)
    if _note_view_status(n)[0] in ("queued", "transcribing", "thinking"):
        raise HTTPException(409, "this note is still being processed; delete it in a minute")
    store.delete_note(note_id)
    return {"ok": True}


def _masked(sentences: list[dict] | None) -> list[dict]:
    """Labels a teacher may say ("कमज़ोर") are never shown back, not even in her own transcript."""
    return [dict(x, text=mask_banned(x["text"])) for x in (sentences or [])]


class Answer(BaseModel):
    answer: str  # a child_id, or "skip"


@app.post("/api/questions/{q_id}")
def answer(q_id: int, body: Answer, c: dict = Depends(current_class)):
    settle_question(c["class_id"], q_id, body.answer)
    return {"ok": True}


class Feedback(BaseModel):
    verdict: str  # up | down | clear


@app.post("/api/records/{rec_id}/feedback")
def feedback(rec_id: int, body: Feedback, c: dict = Depends(current_class)):
    r = store.get_record(rec_id)
    if not r or r["class_id"] != c["class_id"]:
        raise HTTPException(404)
    if body.verdict not in ("up", "down", "clear"):
        raise HTTPException(400, "verdict must be up, down or clear")
    store.update_record(rec_id, feedback=None if body.verdict == "clear" else body.verdict)
    return {"ok": True}


# ---- class picture -----------------------------------------------------------

@app.get("/api/class")
def class_picture(c: dict = Depends(current_class)):
    """The class grid as of now (today's notes included)."""
    t = jobs.class_today(c)
    recs = store.records(c["class_id"])
    pic = planner.picture(c["roster"], c["lesson"], recs, t, jobs.yesterday_list(c["class_id"], t))
    last = {}
    for r in recs:
        if r["child_id"] and r["status"] not in ("dismissed",):
            last[r["child_id"]] = r["day"]
    return {"today": t.isoformat(), "grid": pic["grid"], "silent": pic["silent"], "levels": pic["levels"],
            "class_view": pic["class_view"],
            "next_steps": pic["needs_support"], "language_flags": pic["language_flags"], "last_described": last}


@app.get("/api/children/{child_id}")
def child(child_id: str, c: dict = Depends(current_class)):
    if child_id not in _names(c):
        raise HTTPException(404)
    t = jobs.class_today(c)
    recs = store.records(c["class_id"])
    lads = planner.ladders(recs, t, c["roster"])
    state = planner.ladder.skill_views(lads)
    row = planner.grid([_names(c)[child_id]], state)[child_id]
    levels = {area: {"level": st.level, "moments": st.moments, "days": len(st.days),
                     "post": [round(p, 3) for p in st.post]} for (cid, area), st in lads.items() if cid == child_id}
    nxt = planner.ladder.next_steps(state, child_id)
    mine = [_public_record(r) for r in recs if r["child_id"] == child_id and r["status"] != "dismissed"]
    return {"child": _names(c)[child_id], "grid": row, "records": list(reversed(mine)), "levels": levels,
            "progress": planner.progress(recs, t, _names(c)[child_id]),
            "next_steps": nxt,
            "language_flag": next((f for f in planner.language_flags(recs, t) if f["child_id"] == child_id), None)}


# ---- samples, health, web app ---------------------------------------------------

# SUNO's ladder levels -> ASER-style categories (approximate mapping, for aggregate reporting).
ASER_READING = {0: "beginner", 1: "letter", 2: "word", 3: "word", 4: "paragraph", 5: "story"}
ASER_MATHS = {0: "beginner", 1: "number recognition 10-99", 2: "number recognition 10-99", 3: "subtraction"}


@app.get("/api/export/summary.json")
def export_summary(c: dict = Depends(current_class)):
    """Aggregate levels for a block or state dashboard (for example a Vidya Samiksha Kendra):
    counts only, no names, no teacher field. Only children whose level SUNO is sure of are counted."""
    t = jobs.class_today(c)
    lads = planner.ladders(store.records(c["class_id"]), t, c["roster"])
    counts = {"hindi_reading": {}, "maths": {}}
    for (cid, area), st in lads.items():
        if st.level is None:
            continue
        if area == "hindi":
            k = ASER_READING[st.level]; counts["hindi_reading"][k] = counts["hindi_reading"].get(k, 0) + 1
        elif area == "maths":
            k = ASER_MATHS[st.level]; counts["maths"][k] = counts["maths"].get(k, 0) + 1
    return {"as_of": t.isoformat(), "grade": c["grade"], "children_on_roll": len(c["roster"]),
            "levels_known": {k: sum(v.values()) for k, v in counts.items()},
            "aser_style_levels": counts,
            "note": "ASER-style categories mapped approximately from SUNO's ladder levels. Counts only: no names, "
                    "no teacher field. Children whose level is not yet certain are not counted."}


@app.get("/api/export/class.csv")
def export_class_csv(c: dict = Depends(current_class)):
    """The teacher's own class list with levels and next steps (names included: for her, not for upload)."""
    import csv
    import io
    t = jobs.class_today(c)
    recs = store.records(c["class_id"])
    lads = planner.ladders(recs, t, c["roster"])
    views = planner.ladder.skill_views(lads)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["roll_no", "first_name", "hindi_level", "hindi_next_step", "maths_level", "maths_next_step", "observations"])
    levels = {a["area"]: a["levels"] for a in SKILLS["areas"]}
    for ch in c["roster"]:
        nx = planner.ladder.next_steps(views, ch["child_id"])
        row = [ch["roll_no"], ch["first_name"]]
        for area in ("hindi", "maths"):
            st = lads.get((ch["child_id"], area))
            row.append(levels[area][st.level]["label_hi"] if st and st.level is not None else "")
            row.append(nx.get(area, ""))
        row.append(sum(1 for r in recs if r["child_id"] == ch["child_id"] and r["status"] == "evidence"))
        w.writerow(row)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="suno-{c.get("code") or "demo"}-{t}.csv"'})


@app.get("/api/samples")
def samples():
    import json
    f = ROOT / "samples" / "synthetic" / "sample_notes.json"
    return json.loads(f.read_text()) if f.exists() else {"notes": []}


@app.get("/samples/audio/{name}")
def sample_audio(name: str):
    f = ROOT / "samples" / "synthetic" / "audio" / name
    if "/" in name or ".." in name or not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/samples/images/{name}")
def sample_image(name: str):
    """SYNTHETIC sample photos (a register page and a textbook page) so reviewers can try the photo setup."""
    f = ROOT / "samples" / "synthetic" / "images" / name
    if "/" in name or ".." in name or not name.endswith(".jpg") or not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="image/jpeg")


@app.get("/api/evidence")
def evidence():
    """Public: the numbers on the Evidence page, read from the files the evaluation scripts write
    (eval/results/), so the page can never drift from what the scripts report. SIMULATED results."""
    import json
    from collections import Counter
    res = ROOT / "eval" / "results"
    out: dict = {"label": "SIMULATED: simulated classrooms and teachers, not real children. Scripts and assumptions in eval/sim/.",
                 "files": {"observations": f"prompts/{claude_observations.PROMPT} · schemas/{claude_observations.SCHEMA}",
                           "brief": f"prompts/{brief_mod.PROMPT} · schemas/{brief_mod.SCHEMA}"}}
    f = res / "sim_pipeline.json"
    if f.exists():
        d = json.loads(f.read_text())
        before, after = Counter(), Counter()
        for r in d["results"]:
            before.update(r["totals"]["voice_before"])
            after.update(r["totals"]["voice_after"])
        out["pipeline"] = {
            "notes": sum(len(r["notes"]) for r in d["results"]), "styles": [r["style"] for r in d["results"]],
            "evidence": before["evidence"], "wrong_child_evidence": before["wrong_child_evidence"],
            "direction_ok": before["evidence_direction_ok"],
            "not_evidence": before["expect_not_evidence"], "not_evidence_became_evidence": before["not_evidence_became_evidence"],
            "labels_used": before["statements_with_label"], "labels_repeated": before["banned_in_output"],
            "clear_obs": before["expect_evidence"], "clear_obs_evidence": before["expect_evidence_became_evidence"],
            "unclear_names": after["expect_ask_then_evidence"], "unclear_names_resolved": after["expect_ask_then_evidence_became_evidence"],
            "questions": after["questions"],
        }
    f = res / "real_notes.json"
    if f.exists():
        d = json.loads(f.read_text())
        B, A = d["before_taps"], d["after_taps"]
        out["real_speech"] = {
            "recordings": d["recordings"],
            "settings": {k: {"recordings": v["recordings"], "wer": v["wer_errors"] / max(1, v["wer_words"])} for k, v in d["settings"].items()},
            "evidence": B.get("evidence", 0), "wrong_child_evidence": B.get("wrong_child_evidence", 0),
            "direction_ok": B.get("evidence_direction_ok", 0),
            "not_evidence": B.get("expect_not_evidence", 0), "not_evidence_became_evidence": B.get("not_evidence_became_evidence", 0),
            "clear_obs": B.get("expect_evidence", 0), "clear_obs_evidence": B.get("expect_evidence_became_evidence", 0),
            "absent": A.get("expect_absent", 0), "absent_found": A.get("absent_found", 0),
        }
    f = res / "sim_term.json"
    if f.exists():
        d = json.loads(f.read_text())
        pick = ["children_found", "children_flag_precision", "quiet_with_evidence", "quiet_struggling_found", "level_exact"]
        out["term"] = {"runs": d["runs"], "rates": d["rates"],
                       "arms": {arm: {wk: {m: v.get(m) for m in pick} for wk, v in weeks.items()} for arm, weeks in d["results"].items()}}
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from eval.cost import compute
        out["cost"] = compute()
    except Exception:
        log.exception("cost computation unavailable")
    return out


class DeleteClass(BaseModel):
    confirm: str  # the class code (or, for a demo class, its name)


@app.delete("/api/class")
def delete_class(body: DeleteClass, response: Response, c: dict = Depends(current_class)):
    """Delete the class and everything in it: roster, notes, observations, briefs. Cannot be undone."""
    want = (c.get("code") or c["name"]).strip().upper()
    if body.confirm.strip().upper().replace(" ", "") != want.replace(" ", ""):
        raise HTTPException(400, "type the class code to confirm")
    for table in ("records", "questions", "notes", "briefs", "usage", "classes"):
        store.x(f"DELETE FROM {table} WHERE class_id=?", (c["class_id"],))
    response.delete_cookie("suno")
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return {"ok": True, "demo_fixture": demo.FIXTURE.exists(), "storage": "postgres" if store.PG else "sqlite"}


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.middleware("http")
async def no_stale_shell(request, call_next):
    """The page, the service worker and the app files must never be served stale by a browser or
    proxy cache after a deploy (offline caching is the service worker's job, network first)."""
    resp = await call_next(request)
    p = request.url.path
    if p in ("/", "/index.html", "/sw.js", "/app.js", "/style.css", "/manifest.webmanifest"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
