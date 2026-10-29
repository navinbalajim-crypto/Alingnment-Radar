"""
Build the shared spelling assets used by BOTH the browser engine (frontend/src/utils/spellChecker.js)
and the backend engine (backend/app/services/spell_checker.py).

Inputs (all local, reproducible without any third-party spelling corpus):
  - symspellpy's bundled frequency_dictionary_en_82_765.txt and frequency_bigramdictionary_en_243_342.txt.
    SymSpell documents the unigram list as an intersection of Google Books Ngram (CC BY 3.0) and SCOWL
    (MIT-like); it documents no source for the bigram list. See THIRD_PARTY_NOTICES.md.
  - DOMAIN_VOCABULARY words (app/domain terms, common chat vocabulary), authored for this project.
  - PROJECT_ERROR_MODEL and PROJECT_PARAMS below, authored for this project.

No misspelling corpus (Birkbeck, Aspell, Wikipedia, Norvig, JFLEG) is read here, so no counts or statistics
derived from those corpora end up in the runtime asset.

Usage (from the repo root):
  backend/.venv/Scripts/python.exe scripts/build_spelling_assets.py
  node scripts/evaluate_spelling.mjs --tune     # tunes params on the project-authored chat DEV split, writes params
  node scripts/evaluate_spelling.mjs            # evaluation
"""

import json
import math
import os
import re
from importlib.metadata import version

import symspellpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(symspellpy.__file__)
UNIGRAMS = os.path.join(PKG, "frequency_dictionary_en_82_765.txt")
BIGRAMS = os.path.join(PKG, "frequency_bigramdictionary_en_243_342.txt")
OUT_PATHS = [
    os.path.join(ROOT, "data", "spelling_assets.json"),
    os.path.join(ROOT, "frontend", "src", "data", "spelling_assets.json"),
]

MAX_WORDS = 60000
MAX_BIGRAMS = 40000
MIN_WORD_LEN = 1

# Common chat vocabulary missing from a book-derived list.
DOMAIN_VOCABULARY = [
    "ok", "okay", "yeah", "yep", "nope", "hi", "hey", "thanks", "thx", "pls", "plz", "lol", "haha", "bye", "cool",
    "spotify", "youtube", "whatsapp", "github", "api", "frontend", "backend", "deadline", "deliverable", "deliverables",
    "submission", "teammate", "teammates", "standup", "roadmap", "timeline", "tomorrow", "alignment", "radar",
    "fastapi", "vite", "react", "socket", "login", "username", "email", "app", "apps", "website", "online", "offline",
    "const", "var", "async", "await", "def", "elif", "func", "impl", "enum", "struct", "args", "kwargs", "regex", "json",
    "html", "css", "npm", "repo", "repos", "config", "configs", "localhost", "middleware", "auth", "oauth", "usernames",
    "admin", "apis", "url", "urls", "uuid", "sql", "sqlite", "postgres", "redis", "docker", "kubernetes", "gitlab",
    "webhook", "webhooks", "websocket", "websockets", "typescript", "javascript", "python", "bool", "boolean", "stdout",
    "stderr", "param", "params", "init", "cli", "ui", "ux", "timestamp", "timestamps", "dev", "prod", "staging",
    "wifi", "unfollow", "signup", "timezone", "workflow", "feedback", "kickoff", "onboarding", "bugfix", "hotfix",
]

# Edit costs for the weighted Damerau distance, authored for this project (not learned from any corpus).
# Start from the textbook unit-cost Damerau-Levenshtein distance (every edit costs 1.0) and apply the typing
# prior this project already used for chat text: swapping two neighbouring letters and hitting a neighbouring
# key are the cheapest slips. A wrong first letter is rare when typing, so edits at position 0 cost more.
PROJECT_ERROR_MODEL = {
    "source": "project-authored defaults (unit-cost Damerau-Levenshtein with a keyboard typing prior)",
    "cost": {"ins": 1.0, "del": 1.0, "trans": 0.7, "subAdj": 0.8, "subFar": 1.0},
    "firstLetterMultiplier": 2.0,
}

# Scoring parameters. These are the engine's documented defaults (DEFAULT_PARAMS in spellChecker.js and
# spell_checker.py); `node scripts/evaluate_spelling.mjs --tune` may replace them with values tuned on the
# project-authored chat DEV split only.
PROJECT_PARAMS = {"lambda": 3.0, "mu": 0.25, "bigramFloor": 10.0, "autoMargin": 2.0, "maxAutoCost": 1.6, "minAutoLogFreq": 9.0}
PROJECT_PARAMS_SOURCE = "project-authored defaults"
CHAT_DEV_PARAMS_SOURCE = "tuned on data/chat_spelling_eval.json (dev split, project-authored)"


def main():
    vocab = {}
    with open(UNIGRAMS, encoding="utf-8") as f:
        for line in f:
            w, c = line.split()
            if re.fullmatch(r"[a-z]+", w) and (len(w) > 1 or w in ("a", "i")):
                vocab[w] = int(c)
    # keep the top-N most frequent words
    top = sorted(vocab.items(), key=lambda kv: -kv[1])[:MAX_WORDS]
    vocab = dict(top)
    floor = int(math.exp(12.5))
    for w in DOMAIN_VOCABULARY:
        vocab[w] = max(vocab.get(w, 0), floor)
    words = sorted(vocab, key=lambda w: -vocab[w])

    bigrams = {}
    with open(BIGRAMS, encoding="utf-8") as f:
        for line in f:
            a, b, c = line.split()
            if a in vocab and b in vocab:
                bigrams[f"{a} {b}"] = int(c)
    best = sorted(bigrams.items(), key=lambda kv: -kv[1])[:MAX_BIGRAMS]

    # P(next letter | previous letter) over the top-20k words: an omitted letter that English makes predictable
    # (e.g. 'u' after 'q') is a far more likely typing slip than an arbitrary deletion.
    trans = [[0] * 26 for _ in range(26)]
    for w in words[:20000]:
        for x, y in zip(w, w[1:]):
            trans[ord(x) - 97][ord(y) - 97] += 1
    letter_next = []
    for row in trans:
        total_row = sum(row) or 1
        letter_next.extend(round(c / total_row, 3) for c in row)

    assets = {
        "version": 3,
        "sources": {
            "unigrams": f"symspellpy {version('symspellpy')} frequency_dictionary_en_82_765.txt (SymSpell documents: Google Books Ngram, CC BY 3.0, intersected with SCOWL)",
            "bigrams": "symspellpy frequency_bigramdictionary_en_243_342.txt (upstream source not documented by SymSpell)",
            "letterNext": "computed from the top 20,000 unigram words above",
            "domainVocabulary": "project-authored (scripts/build_spelling_assets.py)",
            "errorModel": PROJECT_ERROR_MODEL["source"],
            "params": PROJECT_PARAMS_SOURCE,
        },
        "words": words,
        "logFreq": [round(math.log(vocab[w]), 2) for w in words],
        "bigrams": {k: round(math.log(v), 1) for k, v in best},
        "letterNext": letter_next,
        "errorModel": {"cost": dict(PROJECT_ERROR_MODEL["cost"]), "firstLetterMultiplier": PROJECT_ERROR_MODEL["firstLetterMultiplier"]},
        "params": dict(PROJECT_PARAMS),
    }
    for path in OUT_PATHS:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # keep params on rebuild only if they were tuned on the project-authored chat set
        if os.path.exists(path):
            try:
                old = json.load(open(path, encoding="utf-8"))
                if old.get("sources", {}).get("params") == CHAT_DEV_PARAMS_SOURCE:
                    assets["params"] = old["params"]
                    assets["sources"]["params"] = CHAT_DEV_PARAMS_SOURCE
            except Exception:
                pass
        with open(path, "w", encoding="utf-8") as f:
            json.dump(assets, f, separators=(",", ":"))
        print(f"wrote {path} ({os.path.getsize(path) // 1024} KB)")
    print("words:", len(words), "bigrams:", len(best), "error model:", assets["errorModel"])


if __name__ == "__main__":
    main()
