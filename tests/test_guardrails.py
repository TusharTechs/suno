"""Banned-label guardrail tests (English and Hindi). No model calls.
The teacher's-note guardrails (grounding, names, opinions, confidence) are in test_notes_guardrails.py."""

import pytest

from server.pipeline.guardrails import has_banned_words, mask_banned


@pytest.mark.parametrize("text", ["Ravi is weak at blending", "रवि कमज़ोर है", "slow reader", "कमजोर"])
def test_banned_words_caught(text):
    assert has_banned_words(text)


def test_support_wording_passes():
    assert not has_banned_words("Ravi needs support with blending; रवि को मिलाकर पढ़ने में मदद चाहिए")


def test_masked_label_is_never_repeated():
    assert not has_banned_words(mask_banned("सोनू तो कमज़ोर है"))
