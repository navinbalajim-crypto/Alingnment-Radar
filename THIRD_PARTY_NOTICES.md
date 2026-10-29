# Third-party notices

Alignment Radar's own source code is licensed under the MIT License (see [LICENSE](LICENSE)). That licence does
not cover the third-party material listed here, which remains under its own terms.

## Data redistributed in this repository

### SymSpell / symspellpy dictionaries

`data/spelling_assets.json` and `frontend/src/data/spelling_assets.json` contain a subset of the English word
frequency list `frequency_dictionary_en_82_765.txt` and the bigram list `frequency_bigramdictionary_en_243_342.txt`,
as bundled with symspellpy 6.10.0 (<https://github.com/mammothb/symspellpy>), a Python port of SymSpell
(<https://github.com/wolfgarbe/SymSpell>).

- symspellpy: MIT License, Copyright (c) 2025 mmb L and Copyright (c) 2021 Wolf Garbe. Full text:
  [licenses/symspellpy-LICENSE.txt](licenses/symspellpy-LICENSE.txt).
- SymSpell: MIT License, Copyright (c) 2018 Wolf Garbe. Full text:
  [licenses/SymSpell-LICENSE.txt](licenses/SymSpell-LICENSE.txt).

According to the SymSpell README, the unigram list was created by intersecting two sources:

- **Google Books Ngram** data. The Google Books Ngram datasets are licensed under a Creative Commons Attribution
  3.0 Unported License (<https://creativecommons.org/licenses/by/3.0/>), as stated at
  <https://storage.googleapis.com/books/ngrams/books/datasetsv3.html>. Word frequencies in this repository are
  derived from that data.
- **SCOWL** (Spell Checker Oriented Word Lists) by Kevin Atkinson, <http://wordlist.aspell.net/>. SymSpell does
  not say which release it used. The SCOWL v1 copyright and permission notice, which includes the notices of the
  sources SCOWL draws on (among them 12dicts, UKACD and WordNet), is reproduced verbatim in
  [licenses/SCOWL-Copyright.txt](licenses/SCOWL-Copyright.txt).

SymSpell does not document the source of the bigram list. See
[docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md#open-questions).

## Frontend libraries bundled into the built web app

The production build (`npm run build`) bundles these runtime dependencies and their transitive dependencies.
Their licence texts are in each package under `frontend/node_modules/<package>/`.

| Package | Version | Licence |
|---|---|---|
| react, react-dom | 19.3.1 | MIT |
| react-router, react-router-dom | 7.18.4 | MIT |
| axios | 1.20.0 | MIT |
| socket.io-client (with engine.io-client, socket.io-parser) | 4.8.4 | MIT |
| lucide-react | 1.59.0 | ISC |
| react-aria-components (Adobe React Aria) | 1.22.1 | Apache-2.0 |

The full production dependency tree (135 packages at the time of writing) is MIT, ISC, Apache-2.0, BSD-3-Clause
or 0BSD, except `caniuse-lite` (CC BY 4.0), which is used by the build tooling (Autoprefixer) and is not shipped in
the bundle. To regenerate the list:

```bash
cd frontend && npm ls --omit=dev --all
```

## Backend libraries

Backend dependencies are installed from PyPI by the user (`pip install -r backend/requirements.txt`) and are not
redistributed in this repository. At the time of writing they are licensed under MIT, BSD-3-Clause, Apache-2.0,
The Unlicense (email-validator) and PSF-2.0 (part of greenlet).

## Material not redistributed

Third-party spelling and grammar corpora used during development (Norvig, Birkbeck, Aspell and Wikipedia
misspelling lists, and JFLEG) and a third-party design-guideline skill are kept out of this repository because
their redistribution terms are unresolved. See [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md).
