"""Backend spelling engine: parity with the browser engine, correctness, protection rules, no external calls."""

import json
import os
from unittest.mock import patch

import pytest

from app.providers.groq_provider import GroqProvider
from app.providers.nvidia_provider import NvidiaProvider
from app.services import spell_checker as sc
from app.services.spelling_engine import get_spelling_corrections

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "spelling_parity.json")


@pytest.fixture(scope="module", autouse=True)
def _assets():
    assert sc.load_assets() is not None, "run scripts/build_spelling_assets.py"


def test_python_engine_matches_the_browser_engine_on_every_fixture_case():
    cases = json.load(open(FIXTURE, encoding="utf-8"))
    assert len(cases) > 300
    mismatches = []
    for c in cases:
        r = sc.classify_token(c["raw"], c["prev"], c["next"], c["atSentenceStart"])
        got = {"status": r["status"], "corrected": r.get("corrected"), "alternatives": r.get("alternatives")}
        if got != c["expected"]:
            mismatches.append((c["raw"], c["expected"], got))
    assert not mismatches, mismatches[:5]


@pytest.mark.parametrize("typo,fix", [
    ("yuo", "you"), ("qick", "quick"), ("teh", "the"), ("becuase", "because"), ("tomorow", "tomorrow"), ("recieve", "receive"),
])
def test_headline_typos_are_corrected(typo, fix):
    corrections, text = get_spelling_corrections(f"please {typo} now")
    assert text == f"please {fix} now"
    assert corrections[0]["corrected"] == fix


def test_sentence_with_several_typos_keeps_valid_words_and_spacing():
    corrections, text = get_spelling_corrections("the project is delay because of yuo so qick it fast")
    assert text == "the project is delay because of you so quick it fast"
    assert [c["original"] for c in corrections] == ["yuo", "qick"]


@pytest.mark.parametrize("text", [
    "see https://exmple.com/qick and mail bob@exmple.com", "ping @alise_t now", "the NASA team", "call getUserNmae",
    "Anirudh joined the call", "valid words only here", "I will be there at 5pm",
])
def test_protected_and_valid_text_is_untouched(text):
    corrections, out = get_spelling_corrections(text)
    assert out is None and corrections == []


def test_case_and_punctuation_are_preserved():
    _, text = get_spelling_corrections("Yuo, (becuase) QICK! Recieve.")
    assert text == "You, (because) QICK! Receive."  # short ALL-CAPS tokens are treated as acronyms


def test_checker_makes_no_network_or_provider_calls():
    with patch.object(GroqProvider, "_post_chat_completion", side_effect=AssertionError("provider called")), \
         patch.object(NvidiaProvider, "_post_chat_completion", side_effect=AssertionError("provider called")):
        get_spelling_corrections("yuo qick teh becuase tomorow")
