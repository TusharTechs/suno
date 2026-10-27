"""The web API end to end with Claude stubbed out: demo login, a typed note, a name question,
feedback, the class grid, and the demo clock. No network, no keys."""

import importlib
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUNO_VAR", str(tmp_path))
    from server import store
    importlib.reload(store)
    from server import jobs, demo, api
    for m in (jobs, demo, api):
        importlib.reload(m)

    def fake_claude(*, prompt, schema, stable_context, request, **kw):
        assert "THE NOTE" in request and "ROSTER" in stable_context
        return {"mentions": [
            {"mention_id": "m1", "sent_ids": ["s1"], "name_said": "पिंकी", "child_id": "c04", "kind": "observation",
             "skill_code": "hi.blend_no_matra", "item": "कमल", "outcome": "incorrect",
             "error_type": "segments_without_blending", "when": "today", "home_language": "none",
             "teacher_quote": "पिंकी ने कमल को क म ल पढ़ा", "rationale": "read कमल as क-म-ल"},
            {"mention_id": "m2", "sent_ids": ["s2"], "name_said": "प्रिया", "child_id": "c12", "kind": "observation",
             "skill_code": "hi.words_with_matras", "item": "मछली", "outcome": "incorrect", "error_type": "matra_omitted",
             "when": "today", "home_language": "none", "teacher_quote": "प्रिया ने मछली को मछल पढ़ा",
             "rationale": "dropped ी"}],
            "follow_ups": []}

    from server.pipeline import claude_observations
    monkeypatch.setattr(claude_observations, "call_structured", fake_claude)
    monkeypatch.setattr(api, "_run", lambda fn, *a: fn(*a))  # run jobs inline
    return TestClient(api.app)


def test_flow(client):
    assert client.get("/api/me").status_code == 401
    r = client.post("/api/login", json={"code": "suno-demo"})
    assert r.status_code == 200
    me = client.get("/api/me").json()
    assert me["synthetic"] and len(me["roster"]) == 30

    today = client.get("/api/today").json()
    assert len(today["listen_today"]) == 5

    nid = client.post("/api/notes", data={"text": "पिंकी ने कमल को क म ल पढ़ा। प्रिया ने मछली को मछल पढ़ा।"}).json()["note_id"]
    n = client.get(f"/api/notes/{nid}").json()
    assert n["status"] == "done"
    by = {r["mention_id"]: r for r in n["records"]}
    assert by["m1"]["status"] == "evidence" and by["m2"]["status"] == "unattributed"
    q = n["questions"][0]
    assert q["candidates"] == ["c12", "c27"]

    assert client.post(f"/api/questions/{q['q_id']}", json={"answer": "c27"}).status_code == 200
    n = client.get(f"/api/notes/{nid}").json()
    m2 = next(r for r in n["records"] if r["mention_id"] == "m2")
    assert m2["child_id"] == "c27" and m2["attribution"] == "teacher_confirmed" and m2["status"] == "evidence"

    rid = next(r for r in n["records"] if r["mention_id"] == "m1")["rec_id"]
    assert client.post(f"/api/records/{rid}/feedback", json={"verdict": "down"}).status_code == 200

    trace = client.get(f"/api/notes/{nid}/trace").json()
    assert trace["claude_output"]["mentions"] and trace["prompt_file"].startswith("prompts/observations")

    grid = client.get("/api/class").json()
    assert set(grid["grid"]) == {c["child_id"] for c in me["roster"]}
    assert client.get("/api/children/c27").json()["records"]


def test_other_class_data_is_not_reachable(client):
    client.post("/api/login", json={"code": "SUNO-DEMO"})
    nid = client.post("/api/notes", data={"text": "पिंकी ने कमल को क म ल पढ़ा। प्रिया ने मछली को मछल पढ़ा।"}).json()["note_id"]
    client.post("/api/logout")
    client.cookies.clear()
    client.post("/api/login", json={"code": "SUNO-DEMO"})  # a second, separate sandbox
    assert client.get(f"/api/notes/{nid}").status_code == 404


def test_bad_inputs(client):
    client.post("/api/login", json={"code": "SUNO-DEMO"})
    assert client.post("/api/notes", data={}).status_code == 400
    assert client.post("/api/notes", data={"text": "x" * 4000}).status_code == 413
    assert client.post("/api/login", json={"code": "nope"}).status_code == 401
    assert client.get("/api/audio/../../etc/passwd").status_code == 404


def test_real_class_setup(client, monkeypatch):
    r = client.post("/api/classes", json={"name": "कक्षा 2-अ", "grade": 2})
    code = r.json()["code"]
    assert len(code) == 9 and code[4] == "-" and not set(code) & set("0O1IL")
    me = client.get("/api/me").json()
    assert me["roster"] == [] and not me["synthetic"] and me["code"] == code

    # First names only; numbers and surnames dropped; duplicate roll numbers fixed.
    r = client.put("/api/roster", json={"children": [
        {"first_name": "प्रिया शर्मा", "roll_no": 1}, {"first_name": "12. रवि", "roll_no": 1},
        {"first_name": "  ", "roll_no": 3}, {"first_name": "गोलू", "aliases": ["गुड्डू सिंह"]}]})
    roster = r.json()["roster"]
    assert [c["first_name"] for c in roster] == ["प्रिया", "रवि", "गोलू"]
    assert len({c["roll_no"] for c in roster}) == 3 and roster[2]["aliases"] == ["गुड्डू"]

    # Editing keeps existing ids (their evidence stays theirs) and adds new ones.
    keep = roster[0]["child_id"]
    r = client.put("/api/roster", json={"children": [dict(roster[0], first_name="प्रिया"), {"first_name": "नेहा"}]})
    ids = [c["child_id"] for c in r.json()["roster"]]
    assert ids[0] == keep and ids[1] not in {c["child_id"] for c in roster}

    r = client.put("/api/lesson", json={"title": "पाठ 3", "focus_skills": ["hi.matras", "nope"],
                                        "items": {"hi.matras": ["का", " कि ", ""], "bogus": ["x"]}})
    assert r.json()["lesson"]["items"] == {"hi.matras": ["का", "कि"]} and r.json()["lesson"]["focus_skills"] == ["hi.matras"]
    assert client.put("/api/lesson", json={"title": "", "focus_skills": [], "items": {}}).status_code == 400

    # Sign in again on "another phone" with the code, typed loosely.
    client.post("/api/logout"); client.cookies.clear()
    assert client.post("/api/login", json={"code": code.lower().replace("-", " ")}).status_code == 200
    assert client.get("/api/me").json()["name"] == "कक्षा 2-अ"


def test_roster_photo_keeps_first_names_only(client, monkeypatch):
    from server.pipeline import roster_photo
    monkeypatch.setattr(roster_photo, "call_structured", lambda **kw: {
        "children": [{"roll_no": 1, "first_name": "आरव यादव"}, {"roll_no": 1, "first_name": "Golu Singh"},
                     {"roll_no": None, "first_name": "७"}], "unreadable": 1, "note": ""})
    client.post("/api/classes", json={"name": "x"})
    r = client.post("/api/roster/photo", files={"photo": ("r.jpg", b"\xff\xd8fake", "image/jpeg")})
    assert r.json()["children"] == [{"roll_no": 1, "first_name": "आरव"}, {"roll_no": None, "first_name": "Golu"}]
    assert client.post("/api/roster/photo", files={"photo": ("r.txt", b"hi", "text/plain")}).status_code == 400


def test_evidence_is_public_and_from_the_scripts(client):
    d = client.get("/api/evidence").json()
    assert "SIMULATED" in d["label"]
    assert d["pipeline"]["evidence"] > 0 and d["pipeline"]["wrong_child_evidence"] == 0
    assert d["term"]["runs"] >= 30 and d["cost"]["child_year_inr"] > 0


def test_delete_class_needs_the_code(client):
    code = client.post("/api/classes", json={"name": "मिटाने वाली"}).json()["code"]
    assert client.request("DELETE", "/api/class", json={"confirm": "wrong"}).status_code == 400
    assert client.request("DELETE", "/api/class", json={"confirm": code.lower()}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/login", json={"code": code}).status_code == 401
