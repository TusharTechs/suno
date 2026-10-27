"""Resolve the name a teacher said to roster children, in code. No AI.

Speech-to-text spells names its own way (फातिमा / फ़ातिमा / Fatima), so names are
compared by a phonetic key that works for Devanagari and Latin spellings alike:
aspirates merge with their base letter (ख -> k, kh -> k), sibilants merge (श ष स -> s),
nuktas are dropped, long and short vowels merge, and a final inherent 'a' is dropped.

Roll numbers ("प्रिया, बारह नंबर वाली", "Priya 27") single out children who share a name.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

MATCH_AT = 0.84   # key similarity needed to count as the same name

# Devanagari consonants -> phonetic class
_CONS = {
    "क": "k", "ख": "k", "ग": "g", "घ": "g", "ङ": "n",
    "च": "c", "छ": "c", "ज": "j", "झ": "j", "ञ": "n",
    "ट": "t", "ठ": "t", "ड": "d", "ढ": "d", "ण": "n",
    "त": "t", "थ": "t", "द": "d", "ध": "d", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "b", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "s", "ष": "s", "स": "s", "ह": "h",
}
# Independent vowels and vowel signs -> vowel class
_VOW = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "e", "ओ": "o", "औ": "o",
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "e", "ो": "o", "ौ": "o",
}
_HALANT, _NUKTA, _ANUSVARA, _CHANDRA, _VISARGA = "्", "़", "ं", "ँ", "ः"

_LATIN_DIGRAPHS = [("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("ou", "o"), ("au", "o"), ("ai", "e"),
                   ("kh", "k"), ("gh", "g"), ("ch", "c"), ("jh", "j"), ("th", "t"), ("dh", "d"),
                   ("ph", "f"), ("bh", "b"), ("sh", "s"), ("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks")]


def _deva_key(word: str) -> str:
    out: list[str] = []
    chars = list(word)
    for i, ch in enumerate(chars):
        if ch in _CONS:
            out.append(_CONS[ch])
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == _NUKTA:
                nxt = chars[i + 2] if i + 2 < len(chars) else ""
            if nxt not in _VOW and nxt != _HALANT:
                out.append("a")  # inherent vowel
        elif ch in _VOW:
            out.append(_VOW[ch])
        elif ch in (_ANUSVARA, _CHANDRA):
            out.append("n" if ch == _ANUSVARA else "")
    key = "".join(out)
    return key[:-1] if len(key) > 2 and key.endswith("a") and word[-1] in _CONS else key


def _latin_key(word: str) -> str:
    w = word.lower()
    for a, b in _LATIN_DIGRAPHS:
        w = w.replace(a, b)
    return re.sub(r"[^a-z]", "", w)


def _collapse(key: str) -> str:
    return re.sub(r"(.)\1+", r"\1", key)


def phonetic_key(word: str) -> str:
    w = unicodedata.normalize("NFC", word).strip()
    if not w:
        return ""
    is_deva = any("ऀ" <= ch <= "ॿ" for ch in w)
    return _collapse(_deva_key(w) if is_deva else _latin_key(w))


def tokens(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text)
    return [x for x in re.split(r"[^\wऀ-ॿ]+", t) if x]


def names_of(child: dict) -> list[str]:
    return [child["first_name"], *child.get("aliases", [])]


def name_match(a: str, b: str) -> str | None:
    """'exact' if the phonetic keys are equal, 'close' if they differ by a spelling slip, else None.
    A close match must start with the same sound: सिमरन and इमरान are different children."""
    ka, kb = phonetic_key(a), phonetic_key(b)
    if not ka or not kb:
        return None
    if ka == kb:
        return "exact"
    if ka[0] == kb[0] and SequenceMatcher(None, ka, kb).ratio() >= MATCH_AT:
        return "close"
    return None


def same_name(a: str, b: str) -> bool:
    return name_match(a, b) is not None


def candidates(name_said: str, roster: list[dict]) -> list[dict]:
    """Roster children whose first name or nickname matches a word (or word pair) in name_said.
    Exact phonetic matches win; close matches count only when nobody matches exactly."""
    toks = tokens(name_said)
    exact, close = [], []
    for c in roster:
        best = None
        for n in names_of(c):
            k = len(tokens(n))
            for i in range(len(toks) - k + 1):
                m = name_match("".join(toks[i:i + k]), "".join(tokens(n)))
                if m == "exact" or (m == "close" and best is None):
                    best = m
        if best == "exact":
            exact.append(c)
        elif best == "close":
            close.append(c)
    return exact or close


# Hindi number words (1-100) with common spellings: roll numbers, and numbers in maths items.
_HINDI_NUMBERS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छे": 6, "सात": 7, "आठ": 8,
    "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "पन्द्रह": 15,
    "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20, "इक्कीस": 21, "बाईस": 22, "बाइस": 22,
    "तेईस": 23, "तेइस": 23, "चौबीस": 24, "पच्चीस": 25, "छब्बीस": 26, "सत्ताईस": 27, "सताईस": 27,
    "अट्ठाईस": 28, "अठ्ठाईस": 28, "अठाईस": 28, "उनतीस": 29, "तीस": 30, "इकतीस": 31, "बत्तीस": 32,
    "तैंतीस": 33, "चौंतीस": 34, "पैंतीस": 35, "छत्तीस": 36, "सैंतीस": 37, "अड़तीस": 38, "अड़तीस": 38,
    "उनतालीस": 39, "चालीस": 40, "इकतालीस": 41, "बयालीस": 42, "तैंतालीस": 43, "चवालीस": 44, "पैंतालीस": 45,
    "छियालीस": 46, "सैंतालीस": 47, "संतालीस": 47, "सैतालीस": 47, "अड़तालीस": 48, "उनचास": 49, "पचास": 50,
    "इक्यावन": 51, "बावन": 52, "तिरपन": 53, "चौवन": 54, "पचपन": 55, "छप्पन": 56, "सत्तावन": 57, "अट्ठावन": 58,
    "उनसठ": 59, "साठ": 60, "इकसठ": 61, "बासठ": 62, "तिरसठ": 63, "चौंसठ": 64, "पैंसठ": 65, "छियासठ": 66,
    "सड़सठ": 67, "अड़सठ": 68, "उनहत्तर": 69, "सत्तर": 70, "इकहत्तर": 71, "बहत्तर": 72, "तिहत्तर": 73,
    "चौहत्तर": 74, "पचहत्तर": 75, "छिहत्तर": 76, "सतहत्तर": 77, "अठहत्तर": 78, "उन्यासी": 79, "अस्सी": 80,
    "इक्यासी": 81, "बयासी": 82, "तिरासी": 83, "चौरासी": 84, "पचासी": 85, "छियासी": 86, "सत्तासी": 87,
    "अट्ठासी": 88, "नवासी": 89, "नब्बे": 90, "इक्यानवे": 91, "बानवे": 92, "तिरानवे": 93, "चौरानवे": 94,
    "पचानवे": 95, "छियानवे": 96, "सत्तानवे": 97, "अट्ठानवे": 98, "निन्यानवे": 99, "सौ": 100,
}


def _num_norm(tok: str) -> str:
    return unicodedata.normalize("NFC", tok).replace(_NUKTA, "").replace(_CHANDRA, _ANUSVARA)


_NUMBER_WORDS = {_num_norm(k): v for k, v in _HINDI_NUMBERS.items()}
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def numbers_in(text: str) -> set[int]:
    """Every number in the text, written as digits (Latin or Devanagari) or as a Hindi word."""
    t = unicodedata.normalize("NFC", text).translate(_DEVA_DIGITS)
    found = {int(d) for d in re.findall(r"\d+", t)}
    for tok in tokens(t):
        n = _NUMBER_WORDS.get(_num_norm(tok))
        if n is not None:
            found.add(n)
    return found


def resolve(name_said: str, roster: list[dict]) -> dict:
    """Which child does name_said mean? Returns
    {"status": "unique" | "roll_number" | "ambiguous" | "unknown" | "no_name",
     "child_id": str | None, "candidates": [child_id, ...]}"""
    if not name_said.strip():
        return {"status": "no_name", "child_id": None, "candidates": []}
    cands = candidates(name_said, roster)
    ids = [c["child_id"] for c in cands]
    if not cands:
        return {"status": "unknown", "child_id": None, "candidates": []}
    if len(cands) == 1:
        return {"status": "unique", "child_id": ids[0], "candidates": ids}
    rolls = numbers_in(name_said)
    by_roll = [c for c in cands if c["roll_no"] in rolls]
    if len(by_roll) == 1:
        return {"status": "roll_number", "child_id": by_roll[0]["child_id"], "candidates": ids}
    return {"status": "ambiguous", "child_id": None, "candidates": ids}
