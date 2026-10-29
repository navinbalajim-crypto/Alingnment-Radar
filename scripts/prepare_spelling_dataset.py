"""
Dataset Preprocessing and Evaluation Preparation Script for Alignment Radar.

LOCAL DEVELOPMENT ONLY. The inputs are third-party corpora whose redistribution terms are unresolved, so neither
the inputs nor anything this script writes is committed (see .gitignore and docs/DATA_PROVENANCE.md). The runtime
spelling asset does not depend on this script's output.

Processes:
1. archive/ (JFLEG grammar error correction data; licence unverified, see docs/DATA_PROVENANCE.md)
   - test.csv and validation.csv: sentence-level corrections
2. archive (1)/ (Peter Norvig's spelling files & Roger Mitton's Birkbeck / Aspell / Wikipedia lists)
   - big.txt: English corpus for frequency dictionary
   - spell-testset1.txt & spell-testset2.txt: Held-out evaluation test sets (strictly isolated)
   - aspell.txt, birkbeck.txt, wikipedia.txt: Training and validation typo pairs
"""

import os
import re
import csv
import json
import random
from collections import Counter
from typing import Dict, List, Tuple, Set

random.seed(42)

ARCHIVE_DIR = "archive"
ARCHIVE_1_DIR = "archive (1)"
DATA_DIR = "data"

DOMAIN_VOCABULARY = {
    "anirudh": 15000,
    "vijay": 15000,
    "spotify": 25000,
    "youtube": 25000,
    "hukum": 8000,
    "tamil": 12000,
    "whatsapp": 20000,
    "github": 18000,
    "submission": 15000,
    "deadline": 18000,
    "deliverable": 10000,
    "project": 30000,
    "review": 20000,
    "frontend": 12000,
    "backend": 12000,
    "api": 25000,
    "fastapi": 8000,
    "vite": 8000,
    "react": 18000,
    "socketio": 6000,
    "alignment": 15000,
    "radar": 15000,
    "tmrw": 10000,
    "bcoz": 10000,
    "ok": 35000,
    "yes": 45000,
    "no": 50000,
}

def parse_colon_separated_pairs(filepath: str) -> List[Tuple[str, str]]:
    """Parse 'correct_word: error1 error2 ...' format into (error, correct) pairs."""
    pairs = []
    if not os.path.exists(filepath):
        return pairs

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            parts = line.split(":", 1)
            correct = parts[0].strip().lower()
            errors = parts[1].strip().split()
            for err in errors:
                err = err.strip().lower()
                # Clean punctuation if attached
                err = re.sub(r"[^a-z]", "", err)
                correct_clean = re.sub(r"[^a-z]", "", correct)
                if err and correct_clean and err != correct_clean and len(err) > 1 and len(correct_clean) > 1:
                    pairs.append((err, correct_clean))
    return pairs


def build_frequency_dict(big_txt_path: str) -> Counter:
    """Build word frequency counts from text corpus."""
    word_counter = Counter()
    if os.path.exists(big_txt_path):
        with open(big_txt_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read().lower()
            words = re.findall(r"\b[a-z]+\b", text)
            word_counter.update(words)

    # Add domain vocabulary
    for word, count in DOMAIN_VOCABULARY.items():
        word_counter[word] = max(word_counter.get(word, 0), count)

    return word_counter


def process_jfleg_csv(csv_path: str) -> List[Dict[str, any]]:
    """Clean and parse JFLEG sentence GEC CSV."""
    rows = []
    if not os.path.exists(csv_path):
        return rows

    with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            src = row[0].strip()
            # Parse corrections string
            refs_raw = row[1].strip()
            refs = []
            if refs_raw.startswith("[") and refs_raw.endswith("]"):
                # Clean up python list-like string representation
                cleaned = refs_raw[1:-1]
                # Split by newline or quote markers
                matches = re.findall(r"['\"](.*?)['\"]", cleaned, re.DOTALL)
                refs = [m.strip() for m in matches if m.strip()]
            if not refs and refs_raw:
                refs = [refs_raw]
            
            if src and refs:
                rows.append({"sentence": src, "corrections": refs})
    return rows


def main():
    print("--- 1. Processing Frequency Corpus (big.txt) ---")
    big_path = os.path.join(ARCHIVE_1_DIR, "big.txt")
    freq_counter = build_frequency_dict(big_path)
    print(f"Total unique words in corpus: {len(freq_counter)}")

    # Write frequency dictionary for SymSpell
    freq_dict_path = os.path.join(DATA_DIR, "frequency_dictionary.txt")
    with open(freq_dict_path, "w", encoding="utf-8") as f:
        for word, count in freq_counter.most_common():
            f.write(f"{word} {count}\n")
    print(f"Saved frequency dictionary to {freq_dict_path}")

    print("\n--- 2. Processing Spelling Error Datasets ---")
    # Held-out test sets (STRICT ISOLATION to prevent data leakage)
    test1_path = os.path.join(ARCHIVE_1_DIR, "spell-testset1.txt")
    test2_path = os.path.join(ARCHIVE_1_DIR, "spell-testset2.txt")
    test_pairs = parse_colon_separated_pairs(test1_path) + parse_colon_separated_pairs(test2_path)
    # Deduplicate test pairs
    test_pairs = list(dict.fromkeys(test_pairs))
    test_error_set = {err for err, _ in test_pairs}
    print(f"Held-out test pairs: {len(test_pairs)} (strictly preserved for evaluation)")

    # Training and Validation sources: aspell, birkbeck, wikipedia
    train_sources = [
        os.path.join(ARCHIVE_1_DIR, "aspell.txt"),
        os.path.join(ARCHIVE_1_DIR, "wikipedia.txt"),
        os.path.join(ARCHIVE_1_DIR, "birkbeck.txt"),
    ]
    raw_train_pairs = []
    for src in train_sources:
        p = parse_colon_separated_pairs(src)
        print(f"Extracted {len(p)} pairs from {src}")
        raw_train_pairs.extend(p)

    # Clean & Deduplicate, strictly removing any test pairs (Zero Leakage)
    clean_pool = []
    seen = set()
    leakage_count = 0
    for err, corr in raw_train_pairs:
        if (err, corr) in seen:
            continue
        seen.add((err, corr))
        # Leakage check: if this error is in the held-out test set, exclude it from train/val
        if err in test_error_set:
            leakage_count += 1
            continue
        clean_pool.append({"error": err, "correction": corr})

    print(f"Filtered {leakage_count} overlapping pairs to prevent test leakage.")
    print(f"Clean pool of non-leaked pairs: {len(clean_pool)}")

    random.shuffle(clean_pool)
    val_split_idx = int(len(clean_pool) * 0.20)
    val_pairs = clean_pool[:val_split_idx]
    train_pairs = clean_pool[val_split_idx:]

    print(f"Train split: {len(train_pairs)} pairs")
    print(f"Validation split: {len(val_pairs)} pairs")
    print(f"Test split: {len(test_pairs)} pairs")

    with open(os.path.join(DATA_DIR, "train_pairs.json"), "w", encoding="utf-8") as f:
        json.dump(train_pairs, f, indent=2)

    with open(os.path.join(DATA_DIR, "val_pairs.json"), "w", encoding="utf-8") as f:
        json.dump(val_pairs, f, indent=2)

    with open(os.path.join(DATA_DIR, "test_pairs.json"), "w", encoding="utf-8") as f:
        json.dump([{"error": e, "correction": c} for e, c in test_pairs], f, indent=2)

    print("\n--- 3. Processing JFLEG Sentence GEC Datasets (archive/) ---")
    jfleg_val = process_jfleg_csv(os.path.join(ARCHIVE_DIR, "validation.csv"))
    jfleg_test = process_jfleg_csv(os.path.join(ARCHIVE_DIR, "test.csv"))
    print(f"JFLEG Validation Sentences: {len(jfleg_val)}")
    print(f"JFLEG Test Sentences: {len(jfleg_test)}")

    with open(os.path.join(DATA_DIR, "jfleg_clean_validation.json"), "w", encoding="utf-8") as f:
        json.dump(jfleg_val, f, indent=2)

    with open(os.path.join(DATA_DIR, "jfleg_clean_test.json"), "w", encoding="utf-8") as f:
        json.dump(jfleg_test, f, indent=2)

    # Compile dataset metadata documentation
    metadata = {
        "datasets": {
            "archive_jfleg": {
                "source": "JHU Fluency-Extended GUG (JFLEG) Grammar Error Correction Benchmark",
                "authors": "Sakaguchi, Post, and Tetreault (TACL 2017)",
                "license": "Unverified for this copy; reported as CC BY-NC-SA 4.0. Not redistributed. See docs/DATA_PROVENANCE.md",
                "files": {
                    "test.csv": {"size_bytes": os.path.getsize(os.path.join(ARCHIVE_DIR, "test.csv")), "rows": len(jfleg_test)},
                    "validation.csv": {"size_bytes": os.path.getsize(os.path.join(ARCHIVE_DIR, "validation.csv")), "rows": len(jfleg_val)},
                },
                "structure": "sentence, corrections (each with 4 fluent reference rewrites)",
                "intended_use": "Evaluates sentence-level grammatical clarity, tense, and fluency improvements. Unsuitable for word-level typo correction training due to complex multi-word structural rewrites.",
            },
            "archive_norvig_mitton": {
                "source": "Peter Norvig Spelling Corpus, Roger Mitton Birkbeck Spelling Error Collection, GNU Aspell, Wikipedia Misspellings",
                "authors": "Peter Norvig, Roger Mitton, GNU Aspell, Wikipedia Contributors",
                "license": "Unresolved and different for each file. Not redistributed. See docs/DATA_PROVENANCE.md",
                "files": {
                    "big.txt": {"size_bytes": os.path.getsize(big_path), "unique_vocabulary": len(freq_counter)},
                    "spell-testset1.txt": {"held_out_test": True},
                    "spell-testset2.txt": {"held_out_test": True},
                    "aspell.txt": {"training_val_pool": True},
                    "wikipedia.txt": {"training_val_pool": True},
                    "birkbeck.txt": {"training_val_pool": True},
                },
                "splits": {
                    "train_pairs": len(train_pairs),
                    "val_pairs": len(val_pairs),
                    "test_pairs": len(test_pairs),
                    "leakage_prevention": "Strict: all test error tokens excluded from training and validation sets.",
                },
                "intended_use": "Frequency-based spelling correction dictionary and word-level typo correction evaluation.",
            }
        }
    }

    with open(os.path.join(DATA_DIR, "dataset_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nAll dataset splits, frequency dictionaries, and metadata successfully created in '{DATA_DIR}/'!")

if __name__ == "__main__":
    main()
