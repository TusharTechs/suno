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

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import demo, jobs, store
from .pipeline import claude_observations, planner
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


def _start_brief(c: dict, day: str, force: bool = False) -> None:
    b = store.get_brief(c["class_id"], day)
    if b and not force and b["status"] in ("queued", "thinking", "speaking", "done"):
        return
    if store.count_today("briefs", c["class_id"]) >= BRIEFS_PER_DAY:
        raise HTTPException(429, "brief limit for today reached for this class")
    store.delete_brief(c["class_id"], day)
    store.put_brief(c["class_id"], day, status="queued")
    _run(jobs.make_brief, c["class_id"], day)


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


@app.post("/api/login")
def login(body: Login, response: Response):
    code = body.code.strip()
    if code.upper() == DEMO_CODE:
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
        out.append({"child_id": cid, "first_name": name, "roll_no": roll, "aliases": [a for a in aliases if a]})
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
        "brief": None if not b else {
            "status": b["status"], "brief": b["brief"], "error": b["error"],
            "audio_url": f"/api/audio/{b['audio_file']}" if b.get("audio_file") else None,
            "problems_fixed": b.get("problems") or [], "usage": b.get("usage")},
        "open_questions": len(open_q),
        "notes_today": [n for n in store.list_notes(c["class_id"]) if n["day"] == day],
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
    return store.list_notes(c["class_id"])


@app.get("/api/notes/{note_id}")
def note(note_id: str, c: dict = Depends(current_class)):
    n = store.get_note(note_id)
    if not n or n["class_id"] != c["class_id"]:
        raise HTTPException(404)
    return {
        "note_id": n["note_id"], "day": n["day"], "status": n["status"], "error": n["error"],
        "source": n["source"], "transcript": n["transcript"], "seconds": n["seconds"],
        "sentences": n["sentences"], "follow_ups": n["follow_ups"] or [],
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
        "note_id": note_id, "day": n["day"], "status": n["status"], "transcript": n["transcript"],
        "sentences": n["sentences"], "listening": n["listening"], "claude_output": n["claude"],
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
    store.delete_note(note_id)
    return {"ok": True}


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
            "next_steps": pic["needs_support"], "language_flags": pic["language_flags"], "last_described": last}


@app.get("/api/children/{child_id}")
def child(child_id: str, c: dict = Depends(current_class)):
    if child_id not in _names(c):
        raise HTTPException(404)
    t = jobs.class_today(c)
    recs = store.records(c["class_id"])
    lads = planner.ladders(recs, t)
    state = planner.ladder.skill_views(lads)
    row = planner.grid([_names(c)[child_id]], state)[child_id]
    levels = {area: {"level": st.level, "moments": st.moments, "days": len(st.days),
                     "post": [round(p, 3) for p in st.post]} for (cid, area), st in lads.items() if cid == child_id}
    nxt = planner.ladder.next_steps(state, child_id)
    mine = [_public_record(r) for r in recs if r["child_id"] == child_id and r["status"] != "dismissed"]
    return {"child": _names(c)[child_id], "grid": row, "records": list(reversed(mine)), "levels": levels,
            "next_steps": nxt,
            "language_flag": next((f for f in planner.language_flags(recs, t) if f["child_id"] == child_id), None)}


# ---- samples, health, web app ---------------------------------------------------

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


@app.get("/healthz")
def healthz():
    return {"ok": True, "demo_fixture": demo.FIXTURE.exists()}


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
