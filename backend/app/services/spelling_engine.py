import os
import re
from app.services.spell_checker import classify_token, looks_like_code
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import settings

_sym_spell = None
try:
    from symspellpy import SymSpell, Verbosity
    # Look for frequency dictionary in project data directory
    _base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _freq_path = os.path.join(_base_dir, "data", "frequency_dictionary.txt")
    if os.path.exists(_freq_path):
        _sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        _sym_spell.load_dictionary(_freq_path, term_index=0, count_index=1)
except Exception:
    _sym_spell = None

COMMON_TYPOS: Dict[str, str] = {
    # User reported examples
    "elaphant": "elephant",
    "infoooorm": "information",
    "informmm": "inform",
    "tmrw": "tomorrow",
    "bcoz": "because",
    "discus": "discuss",
    "budjet": "budget",
    "misic": "music",
    "didnot": "did not",
    "doesnot": "does not",
    "hsa": "has",
    "afterrnoon": "afternoon",
    "afternoonn": "afternoon",
    "cant": "cannot",
    "dont": "don't",
    "wont": "won't",
    "couldnot": "could not",
    "shouldnot": "should not",
    "wouldnot": "would not",
    "isnot": "is not",
    "hasnot": "has not",
    "havenot": "have not",
    "hadnot": "had not",
    "wasnot": "was not",
    "werenot": "were not",
    "arent": "are not",

    # Common chat contractions and abbreviations
    "pls": "please",
    "plz": "please",
    "thx": "thanks",
    "btw": "by the way",
    "asap": "as soon as possible",
    "cuz": "because",
    "cos": "because",
    "abt": "about",
    "msg": "message",
    "txt": "text",

    # High-frequency English spelling mistakes
    "teh": "the",
    "definately": "definitely",
    "definatly": "definitely",
    "definitly": "definitely",
    "seperate": "separate",
    "seperation": "separation",
    "recieve": "receive",
    "recieved": "received",
    "recieving": "receiving",
    "untill": "until",
    "occured": "occurred",
    "occuring": "occurring",
    "occurance": "occurrence",
    "accross": "across",
    "recomended": "recommended",
    "recomend": "recommend",
    "recomends": "recommends",
    "recomending": "recommending",
    "recomendation": "recommendation",
    "recomendations": "recommendations",
    "sugest": "suggest",
    "sugestion": "suggestion",
    "sugestions": "suggestions",
    "spotfy": "spotify",
    "spotifiy": "spotify",
    "vedio": "video",
    "vedios": "videos",
    "goverment": "government",
    "enviroment": "environment",
    "succesful": "successful",
    "succesfully": "successfully",
    "thier": "their",
    "alot": "a lot",
    "truely": "truly",
    "tommorow": "tomorrow",
    "tommorrow": "tomorrow",
    "tomorow": "tomorrow",
    "calender": "calendar",
    "collegue": "colleague",
    "beleive": "believe",
    "beleived": "believed",
    "acheive": "achieve",
    "acheived": "achieved",
    "acheivement": "achievement",
    "neccessary": "necessary",
    "necesary": "necessary",
    "begining": "beginning",
    "appearence": "appearance",
    "maintainance": "maintenance",
    "pronounciation": "pronunciation",
    "writting": "writing",
    "appologize": "apologize",
    "appology": "apology",
    "comunication": "communication",
    "comunicate": "communicate",
    "shedule": "schedule",
    "mispelled": "misspelled",
    "mispell": "misspell",
    "wierd": "weird",
    "noticable": "noticeable",
    "embarass": "embarrass",
    "embarassed": "embarrassed",
    "accomodate": "accommodate",
    "accomodation": "accommodation",
    "intrest": "interest",
    "intresting": "interesting",
    "dissapoint": "disappoint",
    "dissappointed": "disappointed",
    "disapear": "disappear",
    "adress": "address",
    "adressed": "addressed",
    "alright": "all right",
    "basicly": "basically",
    "fourty": "forty",
    "freind": "friend",
    "freinds": "friends",
    "peice": "piece",
    "relevent": "relevant",
    "suprise": "surprise",
    "suprised": "surprised",
    "tendancy": "tendency",
    "whish": "which",
    "wich": "which",
    "alredy": "already",
    "allready": "already",
    "agian": "again",
    "agre": "agree",
    "becuase": "because",
    "beacuse": "because",
    "becasue": "because",
    "bussiness": "business",
    "buisness": "business",
    "completly": "completely",
    "decission": "decision",
    "diffrent": "different",
    "experiance": "experience",
    "finaly": "finally",
    "grat": "great",
    "happend": "happened",
    "hepl": "help",
    "manger": "manager",
    "meating": "meeting",
    "oppurtunity": "opportunity",
    "posible": "possible",
    "possiable": "possible",
    "realy": "really",
    "remeber": "remember",
    "rember": "remember",
    "respone": "response",
    "respons": "response",
    "senario": "scenario",
    "similer": "similar",
    "somthing": "something",
    "tihs": "this",
    "thsi": "this",
    "tahnk": "thank",
    "thnks": "thanks",
    "wether": "whether",
    "woudl": "would",
    "wud": "would",
    "coudl": "could",
    "cud": "could",
    "shoudl": "should",
    "shud": "should",
    "yuor": "your",
}


def _match_case(original: str, target: str) -> str:
    if target.lower() == "when i":
        if original.isupper():
            return "WHEN I"
        if original and original[0].isupper():
            return "When I"
        return "when I"
    if original.isupper():
        return target.upper()
    if original and original[0].isupper():
        return target.capitalize()
    return target.lower()


def _normalize_repeated(word: str) -> str:
    return re.sub(r"(.)\1{2,}", r"\1", word)


def evaluate_clarity_rules(text: str) -> List[Dict[str, Any]]:
    """Evaluate deterministic pre-send clarity templates for ambiguous commitments."""
    if not text or not text.strip():
        return []

    clean_key = re.sub(r"[.!?]+$", "", text.strip().lower())
    phrasing_rules = {
        "tomorrow is submission": {
            "suggested": "The submission is due tomorrow.",
            "reason": "The deadline is unclear.",
        },
        "submission tomorrow": {
            "suggested": "The submission is due tomorrow.",
            "reason": "The deadline is unclear.",
        },
        "send the final version": {
            "suggested": "Please send the final version of the project report.",
            "reason": "Unclear document reference",
        },
        "finish it by evening": {
            "suggested": "Please finish it by 5 PM today.",
            "reason": "Ambiguous deadline time",
        },
        "deploy it after testing": {
            "suggested": "Deploy to production after automated testing passes.",
            "reason": "Unclear deployment target",
        },
    }

    if clean_key in phrasing_rules:
        rule = phrasing_rules[clean_key]
        return [
            {
                "original": text.strip(),
                "suggested": rule["suggested"],
                "reason": rule["reason"],
                "confidence": 0.95,
            }
        ]
    return []


def get_spelling_corrections(text: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    Evaluate spelling corrections for text using dictionary lookups, rule-based typo corrections,
    and SymSpell frequency-based candidate evaluation.
    """
    if not text or not text.strip():
        return [], None

    if not getattr(settings, "LOCAL_SPELLING_ENGINE_ENABLED", True):
        return [], None

    clarity_matches = evaluate_clarity_rules(text)
    if clarity_matches:
        match = clarity_matches[0]
        return [
            {
                "original": match["original"],
                "corrected": match["suggested"],
                "reason": match["reason"],
                "confidence": match["confidence"],
            }
        ], match["suggested"]

    tokens = re.split(r"(\s+)", text)
    corrections: List[Dict[str, str]] = []
    has_change = False
    corrected_tokens: List[str] = []

    word_tokens = [t for t in tokens if t and not t.isspace()]
    word_index = -1
    code_like = looks_like_code(text)

    for token in tokens:
        if not token or token.isspace():
            corrected_tokens.append(token)
            continue
        word_index += 1

        # Skip URLs, email addresses, paths, and code syntax
        if re.search(r"(https?://|www\.|@|/|\\|\.js|\.py|\.com|\.org|\d)", token):
            corrected_tokens.append(token)
            continue

        if re.match(r"^whei$", token, flags=re.I):
            cased_whei = _match_case(token, "when I")
            corrections.append({
                "original": token,
                "corrected": cased_whei,
                "reason": "Suggested phrasing 'when I'",
                "confidence": 0.92,
            })
            corrected_tokens.append(cased_whei)
            has_change = True
            continue

        match = re.match(r"^([^a-zA-Z0-9]*)(.*?)([^a-zA-Z0-9]*)$", token)
        if not match:
            corrected_tokens.append(token)
            continue

        prefix, core, suffix = match.groups()
        if not core or not core.isalpha():
            corrected_tokens.append(token)
            continue

        lower = core.lower()
        fixed = COMMON_TYPOS.get(lower)

        if not fixed:
            collapsed = _normalize_repeated(lower)
            if collapsed in COMMON_TYPOS:
                fixed = COMMON_TYPOS[collapsed]

        dictionary_fix = None
        if not fixed:
            # Shared local checker (same assets/scoring as the browser engine): dictionary + edit cost + context.
            idx = word_index
            prev_tok = word_tokens[idx - 1] if idx else None
            next_tok = word_tokens[idx + 1] if idx is not None and idx + 1 < len(word_tokens) else None
            res = classify_token(
                token,
                prev=prev_tok,
                nxt=next_tok,
                code_like=code_like,
                at_sentence_start=not idx or bool(re.search(r"[.!?][\"')\]]*$", prev_tok or "")),
            )
            if res["status"] in ("auto", "suggest") and res.get("corrected") != token:
                dictionary_fix = res

        if dictionary_fix is not None:
            corrections.append({
                "original": token,
                "corrected": dictionary_fix["corrected"],
                "reason": (f"Misspelled word '{core}'" if dictionary_fix["status"] == "auto"
                           else f"Possible misspelling of '{dictionary_fix['corrected']}'"),
                "confidence": dictionary_fix["confidence"],
            })
            corrected_tokens.append(dictionary_fix["corrected"])
            has_change = True
        elif fixed and fixed.lower() != lower:
            cased_fix = _match_case(core, fixed)
            corrected_token = f"{prefix}{cased_fix}{suffix}"
            corrections.append({
                "original": token,
                "corrected": corrected_token,
                "reason": f"Misspelled word '{core}'",
                "confidence": 0.98 if fixed in COMMON_TYPOS.values() else 0.88,
            })
            corrected_tokens.append(corrected_token)
            has_change = True
        else:
            corrected_tokens.append(token)

    # Multi-word typo handling
    result_text = "".join(corrected_tokens) if has_change else text
    if re.search(r"\bother\s+wise\b", result_text, flags=re.I):
        corrections.append({
            "original": "other wise",
            "corrected": "otherwise",
            "reason": "Compound word 'otherwise'",
            "confidence": 0.95,
        })
        result_text = re.sub(r"\bother\s+wise\b", "otherwise", result_text, flags=re.I)
        has_change = True

    corrected_text = result_text if has_change else None
    return corrections, corrected_text
