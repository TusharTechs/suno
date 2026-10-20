"""Guardrail tests on the SYNTHETIC adversarial lessons. No model calls."""

import json
from pathlib import Path

import pytest

from server.pipeline.guardrails import check_moments, has_banned_words

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "samples/synthetic/attribution_lessons.json").read_text())
ROSTER = DATA["roster"]
L1, L2 = DATA["lessons"]


def moment(**kw):
    base = {"moment_id": "m1", "prompt_seg_ids": [], "response_seg_ids": [], "uptake_seg_ids": [],
            "addressee_child_id": None, "attribution_basis": "none", "name_quote": "",
            "response_type": "individual", "expected_item": None, "answer_heard": "",
            "teacher_uptake": "none", "teacher_said_answer": False, "note": ""}
    return base | kw


def run(lesson, m):
    kept, problems = check_moments([m], lesson["segments"], lesson["taps"], ROSTER)
    return (kept[0] if kept else None), problems


def test_unique_name_call_is_kept():
    m, _ = run(L1, moment(prompt_seg_ids=["s2"], response_seg_ids=["s3"], uptake_seg_ids=["s4"],
                          addressee_child_id="c01", attribution_basis="name_call", name_quote="रवि", answer_heard="पेड़"))
    assert m["addressee_child_id"] == "c01"


def test_pointing_guess_is_removed():
    # Claude guesses a child the teacher only pointed at: no name in the words, so no attribution.
    m, p = run(L1, moment(prompt_seg_ids=["s5"], response_seg_ids=["s6"], uptake_seg_ids=["s7"],
                          addressee_child_id="c09", attribution_basis="name_call", name_quote="बेटा", answer_heard="गर"))
    assert m["addressee_child_id"] is None and p[0][1] == "unattributed"


def test_shared_name_without_roll_number_is_removed():
    m, p = run(L1, moment(prompt_seg_ids=["s11"], response_seg_ids=["s12"], uptake_seg_ids=["s13"],
                          addressee_child_id="c02", attribution_basis="name_call", name_quote="प्रिया", answer_heard="नाब"))
    assert m["addressee_child_id"] is None and "roll number" in p[0][2]


def test_shared_name_with_roll_number_is_kept():
    m, _ = run(L1, moment(prompt_seg_ids=["s14"], response_seg_ids=["s15"], uptake_seg_ids=["s16"],
                          addressee_child_id="c03", attribution_basis="name_call", name_quote="प्रिया 27 नंबर", answer_heard="मोर"))
    assert m["addressee_child_id"] == "c03"


def test_tap_is_kept():
    m, _ = run(L1, moment(prompt_seg_ids=["s8"], response_seg_ids=["s9"], uptake_seg_ids=["s10"],
                          addressee_child_id="c05", attribution_basis="tap_confirm", answer_heard="कमल"))
    assert m["addressee_child_id"] == "c05"


def test_tap_that_disagrees_with_name_wins_over_claude():
    m, p = run(L2, moment(prompt_seg_ids=["s12"], response_seg_ids=["s13"], uptake_seg_ids=["s14"],
                          addressee_child_id="c11", attribution_basis="name_call", name_quote="नेहा", answer_heard="सन"))
    assert m["addressee_child_id"] is None and "tap" in p[0][2]


def test_chorus_is_never_attributed():
    m, _ = run(L1, moment(prompt_seg_ids=["s25"], response_seg_ids=["s26"], response_type="individual",
                          addressee_child_id="c01", attribution_basis="name_call", name_quote="रवि", answer_heard="किताब"))
    assert m["addressee_child_id"] is None


def test_invented_segment_is_dropped():
    m, p = run(L1, moment(prompt_seg_ids=["s2"], response_seg_ids=["s99"], answer_heard="पेड़"))
    assert m is None and p[0][1] == "dropped"


def test_invented_answer_text_is_dropped():
    m, p = run(L1, moment(prompt_seg_ids=["s17"], response_seg_ids=["s18"], answer_heard="बादल"))
    assert m is None and "answer_heard" in p[0][2]


def test_name_only_in_praise_is_kept():
    m, _ = run(L2, moment(prompt_seg_ids=["s9"], response_seg_ids=["s10"], uptake_seg_ids=["s11"],
                          addressee_child_id="c12", attribution_basis="name_call", name_quote="इमरान", answer_heard="कैट"))
    assert m["addressee_child_id"] == "c12"


def test_nickname_is_kept():
    m, _ = run(L2, moment(prompt_seg_ids=["s15"], response_seg_ids=["s16"], uptake_seg_ids=["s17"],
                          addressee_child_id="c04", attribution_basis="name_call", name_quote="गुड्डू", answer_heard="फिश"))
    assert m["addressee_child_id"] == "c04"


@pytest.mark.parametrize("text", ["Ravi is weak at blending", "रवि कमज़ोर है", "slow reader", "कमजोर"])
def test_banned_words_caught(text):
    assert has_banned_words(text)


def test_support_wording_passes():
    assert not has_banned_words("Ravi needs support with blending; रवि को मिलाकर पढ़ने में मदद चाहिए")
