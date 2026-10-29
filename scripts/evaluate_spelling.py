"""
Evaluation script for Alignment Radar's Fast Local Spelling-Correction Engine.
Benchmarks accuracy on held-out test sets, measures local vs NVIDIA latency,
and evaluates preservation of names, slang, URLs, and code.
"""

import os
import re
import time
import json
from typing import Dict, List, Tuple
from symspellpy import SymSpell, Verbosity

# Load paths
DATA_DIR = "data"
TEST_PAIRS_PATH = os.path.join(DATA_DIR, "test_pairs.json")
FREQ_DICT_PATH = os.path.join(DATA_DIR, "frequency_dictionary.txt")

# Initialize SymSpell
sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
if os.path.exists(FREQ_DICT_PATH):
    sym_spell.load_dictionary(FREQ_DICT_PATH, term_index=0, count_index=1)

# Import common typos and logic from backend
from app.services.spelling_engine import COMMON_TYPOS, get_spelling_corrections, _match_case

def local_correct_word(word: str) -> str:
    """Evaluate local correction on a single word."""
    lower = word.lower()
    # 1. Direct typo dictionary lookup
    if lower in COMMON_TYPOS:
        return _match_case(word, COMMON_TYPOS[lower])
    
    # 2. SymSpell lookup (distance 1 or 2 with high frequency)
    suggestions = sym_spell.lookup(lower, Verbosity.CLOSEST, max_edit_distance=2)
    if suggestions and suggestions[0].distance > 0:
        best = suggestions[0]
        # Only accept if confident
        if best.count >= 5 or best.distance == 1:
            return _match_case(word, best.term)
    return word

def evaluate_held_out_test():
    """Evaluate accuracy on the held-out test set."""
    if not os.path.exists(TEST_PAIRS_PATH):
        print(f"Test pairs file not found: {TEST_PAIRS_PATH}")
        return 0, 0, 0.0

    with open(TEST_PAIRS_PATH, "r", encoding="utf-8") as f:
        test_pairs = json.load(f)

    total = len(test_pairs)
    correct_count = 0
    start_time = time.perf_counter()

    for item in test_pairs:
        err = item["error"]
        expected = item["correction"]
        pred = local_correct_word(err).lower()
        if pred == expected.lower():
            correct_count += 1

    elapsed = time.perf_counter() - start_time
    avg_latency_ms = (elapsed / total) * 1000
    accuracy = (correct_count / total) * 100

    print(f"=== Held-Out Test Evaluation ({total} pairs) ===")
    print(f"Correctly corrected: {correct_count}/{total} ({accuracy:.2f}%)")
    print(f"Total time: {elapsed:.3f}s | Average per-word latency: {avg_latency_ms:.3f}ms")
    return correct_count, total, accuracy, avg_latency_ms

def evaluate_realistic_sentences():
    """Evaluate realistic sentences, names, slang, and code preservation."""
    test_cases = [
        # (input_text, expected_corrected, should_change)
        ("I like Anirudh misic", "I like Anirudh music", True),
        ("Please recomend some songs", "Please recommend some songs", True),
        ("I will send it tomorow", "I will send it tomorrow", True),
        ("tomorrow is submission", "The submission is due tomorrow.", True),
        ("I am going to meet Vijay in Chennai.", "I am going to meet Vijay in Chennai.", False),
        ("The server is listening on port 8000 at http://localhost:5173", "The server is listening on port 8000 at http://localhost:5173", False),
        ("const result = await fetch('/api/v1/status')", "const result = await fetch('/api/v1/status')", False),
        ("Hey bro, that beat was lit and super cool!", "Hey bro, that beat was lit and super cool!", False),
    ]

    print("\n=== Realistic Sentence Evaluation ===")
    all_passed = True
    latencies = []

    for text, expected, should_change in test_cases:
        t0 = time.perf_counter()
        corrections, corrected_text = get_spelling_corrections(text)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)

        actual_output = corrected_text if corrected_text else text
        passed = (actual_output.strip().lower() == expected.strip().lower())
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False

        print(f"[{status}] Input: '{text}'")
        print(f"       Output: '{actual_output}'")
        if not passed:
            print(f"       Expected: '{expected}'")

    avg_sentence_lat = sum(latencies) / len(latencies)
    print(f"\nAverage sentence correction latency: {avg_sentence_lat:.2f}ms")
    return all_passed, avg_sentence_lat

if __name__ == "__main__":
    evaluate_held_out_test()
    evaluate_realistic_sentences()
