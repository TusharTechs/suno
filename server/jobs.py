"""Background jobs: process a voice note, build a morning brief. Each runs in a worker thread.

Note:  audio -> Sarvam speech-to-text -> numbered sentences -> Claude (observations)
       -> code checks (grounding, roster, items, labels) -> code confidence -> records + questions
Brief: records -> code picture (tracker, Silence Ledger, listening list) -> Claude (wording)
       -> code checks -> Sarvam text-to-speech
"""

from __future__ import annotations

import logging
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import store
from .pipeline import asr, brief as brief_mod, claude_observations, planner, tts
from .pipeline.claude_client import ClaudeOutputError, Usage

log = logging.getLogger("suno.jobs")
IST = ZoneInfo("Asia/Kolkata")


def class_today(c: dict) -> date:
    d = datetime.now(IST).date()
    if not planner.is_school_day(d):
        d = planner.next_school_day(d)
    for _ in range(c.get("day_offset", 0)):
        d = planner.next_school_day(d)
    return d


def _usage_dict(u: Usage, prompt: str | None = None) -> dict:
    d = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
         "cache_write_tokens": u.cache_write_tokens, "cache_read_tokens": u.cache_read_tokens,
         "usd": round(u.usd, 4)}
    return d | ({"prompt": prompt} if prompt else {})


def yesterday_list(class_id: str, today: date) -> set[str]:
    prev = planner.school_days_before(today, 1)[0].isoformat()
    b = store.get_brief(class_id, prev)
    if b and b.get("picture"):
        return {x["child_id"] for x in b["picture"]["listen_today"]}
    notes = store.q("SELECT listening_json FROM notes WHERE class_id=? AND day=? ORDER BY created_at DESC LIMIT 1",
                    (class_id, prev))
    if notes and notes[0]["listening_json"]:
        import json
        return {x["child_id"] for x in json.loads(notes[0]["listening_json"])}
    return set()


def morning_picture(c: dict, today: date) -> dict:
    """What code knows at the start of `today`: notes from earlier days only."""
    recs = [r for r in store.records(c["class_id"]) if r["day"] < today.isoformat()]
    return planner.picture(c["roster"], c["lesson"], recs, today, yesterday_list(c["class_id"], today))


def process_note(note_id: str, audio: bytes | None = None, text: str | None = None) -> None:
    note = store.get_note(note_id)
    c = store.get_class(note["class_id"])
    timings, usage = {}, Usage()
    try:
        if audio is not None:
            store.update_note(note_id, status="transcribing")
            t = time.time()
            heard = asr.transcribe(audio, c["roster"], c["lesson"])
            timings["speech_to_text_s"] = round(time.time() - t, 1)
            transcript, seconds = heard["transcript"], heard["seconds"]
            del audio  # the voice note is never stored
        else:
            transcript, seconds = (text or "").strip(), None
        sentences = asr.sentences(transcript)
        store.update_note(note_id, status="thinking", transcript=transcript, seconds=seconds,
                          sentences_json=sentences)
        if not sentences:
            raise asr.ASRError("no speech was recognised in the note")
        t = time.time()
        out = claude_observations.extract(sentences, c["roster"], c["lesson"], note["listening"] or [], usage=usage)
        timings["claude_s"] = round(time.time() - t, 1)
        store.add_records(note_id, c["class_id"], note["day"], out["records"])
        store.add_questions(note_id, c["class_id"], out["questions"])
        store.update_note(note_id, status="done", claude_json=out["raw"], problems_json=out["problems"],
                          follow_ups_json=out["follow_ups"], usage_json=_usage_dict(usage, claude_observations.PROMPT),
                          timings_json=timings)
        # A note from an earlier day changes that day's picture; today's brief is rebuilt on request.
    except (asr.ASRError, ClaudeOutputError) as e:
        store.update_note(note_id, status="failed", error=str(e), usage_json=_usage_dict(usage), timings_json=timings)
    except Exception as e:  # never leave a note spinning
        log.exception("note %s failed", note_id)
        store.update_note(note_id, status="failed", error=f"unexpected error: {type(e).__name__}",
                          usage_json=_usage_dict(usage), timings_json=timings)


def make_brief(class_id: str, day: str) -> None:
    c = store.get_class(class_id)
    today = date.fromisoformat(day)
    usage = Usage()
    pic = morning_picture(c, today)
    store.put_brief(class_id, day, status="thinking", picture_json=pic)
    since = planner.school_days_before(today, planner.WINDOW_DAYS)[0].isoformat()
    recent = [r for r in store.records(class_id) if r["status"] == "evidence" and r.get("feedback") != "down"
              and since <= r["day"] < day]
    try:
        b, fixed = brief_mod.write_brief(c["roster"], pic, recent, usage=usage)
    except ClaudeOutputError as e:
        # Fail closed: the teacher still gets the code-built facts, just without the spoken prose.
        store.put_brief(class_id, day, status="fallback", error=str(e), usage_json=_usage_dict(usage))
        return
    except Exception as e:
        log.exception("brief %s %s failed", class_id, day)
        store.put_brief(class_id, day, status="fallback", error=f"unexpected error: {type(e).__name__}")
        return
    store.put_brief(class_id, day, status="speaking", brief_json=b, problems_json=fixed,
                    usage_json=_usage_dict(usage, brief_mod.PROMPT))
    audio_name = f"{class_id}_{day}.mp3"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            mp3 = tts.speak_hi(b["text_hi"], Path(tmp) / audio_name).read_bytes()
        store.put_brief(class_id, day, status="done", audio_file=audio_name, audio=mp3)
    except Exception as e:
        log.warning("text-to-speech failed for %s %s: %s", class_id, day, e)
        store.put_brief(class_id, day, status="done", error=f"voice not available: {type(e).__name__}")

