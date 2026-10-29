"""Backend port of the local spelling checker (frontend/src/utils/spellChecker.js).

Same assets (data/spelling_assets.json) and the same scoring, so browser and server agree. This is NOT a second
spelling system: tests/test_spell_checker.py replays a fixture generated from the JS engine and requires identical
results. It is purely local; no external provider is ever contacted.

    score = ln(frequency) - lambda * weightedEditCost + mu * bigramContext
    status: 'ok' | 'skip' | 'auto' | 'suggest'
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_PARAMS = {
    "lambda": 3.0, "mu": 0.25, "bigramFloor": 10.0, "autoMargin": 2.0, "maxAutoCost": 1.6, "minAutoLogFreq": 9.0,
}
BIGRAM_CAP = 3
DUP_FACTOR = 0.6
PRED_FACTOR = 0.6

_ASSETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data", "spelling_assets.json",
)

_assets: Optional[Dict[str, Any]] = None
_vocab: Dict[str, int] = {}
_by_length: Dict[int, List[int]] = {}
_counts: List[Tuple[int, ...]] = []


def set_assets(data: Dict[str, Any]) -> None:
    global _assets, _vocab, _by_length, _counts
    _assets = data
    _vocab = {}
    _by_length = {}
    _counts = []
    for i, w in enumerate(data["words"]):
        vec = [0] * 26
        for ch in w:
            vec[ord(ch) - 97] += 1
        _counts.append(tuple(vec))
        _vocab[w] = i
        _by_length.setdefault(len(w), []).append(i)


def load_assets() -> Optional[Dict[str, Any]]:
    if _assets is None and os.path.exists(_ASSETS_PATH):
        with open(_ASSETS_PATH, encoding="utf-8") as f:
            set_assets(json.load(f))
    return _assets


def _params() -> Dict[str, float]:
    return {**DEFAULT_PARAMS, **((_assets or {}).get("params") or {})}


_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_KEY = {c: (r, i + 0.5 * r) for r, row in enumerate(_ROWS) for i, c in enumerate(row)}


def _adjacent(a: str, b: str) -> bool:
    p, q = _KEY.get(a), _KEY.get(b)
    return bool(p and q and a != b and abs(p[0] - q[0]) <= 1 and abs(p[1] - q[1]) <= 1.01)


def weighted_edit_cost(a: str, b: str, max_edits: int = 2) -> Optional[float]:
    assert _assets is not None
    model = _assets["errorModel"]
    c = model["cost"]
    fm = model["firstLetterMultiplier"]
    letter_next = _assets["letterNext"]
    n, k = len(a), len(b)
    if abs(n - k) > max_edits:
        return None
    INF = 1e9
    d = [[(INF, 99) for _ in range(k + 1)] for _ in range(n + 1)]
    d[0][0] = (0.0, 0)

    def better(x, y):
        return x if x[0] < y[0] else y

    def add(x, cost):
        return (x[0] + cost, x[1] + 1)

    for i in range(n + 1):
        for j in range(k + 1):
            cur = d[i][j]
            if cur[0] >= INF:
                continue
            if i < n:
                dup = (i > 0 and a[i] == a[i - 1]) or (i + 1 < n and a[i] == a[i + 1])
                d[i + 1][j] = better(d[i + 1][j], add(cur, c["ins"] * (fm if i == 0 else 1) * (DUP_FACTOR if dup else 1)))
            if j < k:
                pred = letter_next[(ord(b[j - 1]) - 97) * 26 + (ord(b[j]) - 97)] if j > 0 else 0
                d[i][j + 1] = better(d[i][j + 1], add(cur, c["del"] * (fm if j == 0 else 1) * (1 - PRED_FACTOR * pred)))
            if i < n and j < k:
                if a[i] == b[j]:
                    d[i + 1][j + 1] = better(d[i + 1][j + 1], (cur[0], cur[1]))
                else:
                    sub = c["subAdj"] if _adjacent(a[i], b[j]) else c["subFar"]
                    d[i + 1][j + 1] = better(d[i + 1][j + 1], add(cur, sub * (fm if i == 0 else 1)))
            if i + 1 < n and j + 1 < k and a[i] == b[j + 1] and a[i + 1] == b[j] and a[i] != a[i + 1]:
                d[i + 2][j + 2] = better(d[i + 2][j + 2], add(cur, c["trans"] * (fm if i == 0 else 1)))
    res = d[n][k]
    return res[0] if res[1] <= max_edits else None


def _max_edits_for(length: int) -> int:
    return 1 if length <= 4 else 2


def _bigram_bonus(prev: Optional[str], word: str, nxt: Optional[str], p: Dict[str, float]) -> float:
    assert _assets is not None
    bonus = 0.0
    if prev:
        lb = _assets["bigrams"].get(f"{prev} {word}")
        if lb is not None:
            bonus += min(BIGRAM_CAP, max(0.0, lb - p["bigramFloor"]))
    if nxt:
        lb = _assets["bigrams"].get(f"{word} {nxt}")
        if lb is not None:
            bonus += min(BIGRAM_CAP, max(0.0, lb - p["bigramFloor"]))
    return bonus


def all_candidates(word: str) -> List[Dict[str, Any]]:
    assert _assets is not None
    max_edits = _max_edits_for(len(word))
    budget = 2 * max_edits
    q = [0] * 26
    for ch in word:
        q[ord(ch) - 97] += 1
    out: List[Dict[str, Any]] = []
    for length in range(len(word) - max_edits, len(word) + max_edits + 1):
        for idx in _by_length.get(length, ()):
            vec = _counts[idx]
            diff = 0
            for k in range(26):
                diff += abs(q[k] - vec[k])
                if diff > budget:
                    break
            if diff > budget:
                continue
            cand = _assets["words"][idx]
            cost = weighted_edit_cost(word, cand, max_edits)
            if cost is not None:
                out.append({"word": cand, "cost": cost, "logFreq": _assets["logFreq"][idx]})
    return out


def score_candidates(cands, prev, nxt, p=None):
    p = p or _params()
    scored = [
        {**c, "score": c["logFreq"] - p["lambda"] * c["cost"] + p["mu"] * _bigram_bonus(prev, c["word"], nxt, p)}
        for c in cands
    ]
    scored.sort(key=lambda c: -c["score"])  # stable, like the JS sort
    return scored


def is_clear(ranked, p=None) -> bool:
    p = p or _params()
    best = ranked[0]
    margin = best["score"] - ranked[1]["score"] if len(ranked) > 1 else float("inf")
    return margin >= p["autoMargin"] and best["cost"] <= p["maxAutoCost"] and best["logFreq"] >= p["minAutoLogFreq"]


def match_case(original: str, target: str) -> str:
    if original == original.upper() and len(original) > 1:
        return target.upper()
    if original[0] != original[0].lower():
        return target[:1].upper() + target[1:]
    return target


_PREFIXES = ("un", "non", "pre", "dis", "mis", "anti", "inter", "over", "under", "multi", "semi")
_SUFFIXES = ("s", "es", "ed", "d", "ing", "ly", "er", "ers", "est", "ness", "ment", "ments", "able", "ible", "ful",
             "less", "ity", "ion", "ions", "al", "ish")


def is_derived_word(w: str) -> bool:
    """A valid affix on a known base word ('unconfigured') is not a typo, even if the word list lacks it."""
    if len(w) < 6:
        return False
    for p in _PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 4 and w[len(p):] in _vocab:
            return True
    for x in _SUFFIXES:
        if not w.endswith(x):
            continue
        base = w[: len(w) - len(x)]
        if len(base) < 4:
            continue
        if base in _vocab or base + "e" in _vocab:
            return True
        if base[-1] == base[-2] and base[:-1] in _vocab:
            return True
    return False


_CODE = re.compile(r"[{};]|=>|\w\(|\s=\s|`|</?[a-z]+>")


def looks_like_code(text: str) -> bool:
    """Code-like text (statements, tags, backticks) is never spell-checked."""
    return bool(_CODE.search(text))


_TOKEN = re.compile(r"^([^A-Za-z0-9'’]*)([A-Za-z'’]+)([^A-Za-z0-9'’]*)$")


def classify_token(
    raw: str,
    prev: Optional[str] = None,
    nxt: Optional[str] = None,
    at_sentence_start: bool = False,
    protected_words: Optional[Set[str]] = None,
    code_like: bool = False,
) -> Dict[str, Any]:
    if load_assets() is None or not raw:
        return {"status": "skip"}
    m = _TOKEN.match(raw)
    if not m:
        return {"status": "skip"}
    prefix, core, suffix = m.groups()
    if re.search(r"[@#$`<]", prefix) or re.search(r"[`>]", suffix):
        return {"status": "skip"}
    if re.search(r"['’]", core) or len(core) < 3:
        return {"status": "skip"}
    lower = core.lower()
    if protected_words and lower in protected_words:
        return {"status": "skip"}
    if core == core.upper() and len(core) <= 6:
        return {"status": "skip"}
    if re.search(r"[a-z][A-Z]", core):
        return {"status": "skip"}
    if core[0] != core[0].lower() and core[1:] == core[1:].lower() and not at_sentence_start:
        return {"status": "skip"}
    if code_like:
        return {"status": "skip"}
    if lower in _vocab or is_derived_word(lower):
        return {"status": "ok"}

    prev_n = re.sub(r"[^a-z]", "", prev.lower()) if prev else None
    next_n = re.sub(r"[^a-z]", "", nxt.lower()) if nxt else None
    ranked = score_candidates(all_candidates(lower), prev_n or None, next_n or None)[:3]
    if not ranked:
        return {"status": "skip"}
    clear = is_clear(ranked)
    apply = lambda w: f"{prefix}{match_case(core, w)}{suffix}"  # noqa: E731
    return {
        "status": "auto" if clear else "suggest",
        "corrected": apply(ranked[0]["word"]),
        "alternatives": [apply(r["word"]) for r in ranked],
        "confidence": 0.97 if clear else 0.6,
    }
