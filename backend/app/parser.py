"""
parser.py — Deterministic Hinglish & Indian-English grading engine.

Supports:
- Numeral & Fraction Lexer (Hindi/Hinglish 0-25 + Indian fractions)
- Self-Correction Collapse ("do nahi teen" → 3)
- Intent Router & Self-Talk Filter
- Anchor Slicing & Tone Sanitizer
- Bilingual Feedback generation
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Pre-Normalization Pass for Real-World Web Speech API (en-IN / hi-IN)
# ---------------------------------------------------------------------------

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_CLOCK_FRACTION_SUFFIX = {
    "00": "",
    "15": ".25",
    "30": ".5",
    "45": ".75",
}

_ROLL_HOMOPHONE_RE = re.compile(
    r"(?<![\w\u0900-\u097F])"
    r"(?:रोल\s*नंबर|रोल\s*नं\.?|रोल|रौल|रोल्ड|ट्रोल|rolled|role|royal)"
    r"(?=\s*\d)",
    re.IGNORECASE,
)

_CANDIDATE_RE = re.compile(
    r"(?<![\w\u0900-\u097F])कैंडिडेट(?![\w\u0900-\u097F])"
)

_Q_HOMOPHONE_RE = re.compile(
    r"(?<![\w\u0900-\u097F])"
    r"(?:क्यू|क्यों|क्यु|किउ|के|क्वेश्चन|सवाल|प्रश्न)\s*(\d{1,2})\b"
)

_DUP_Q_ANCHOR_RE = re.compile(r"\b(Q\d{1,2})(?:\s+\1\b)+", re.IGNORECASE)

_DEVANAGARI_TOKEN_MAP: dict[str, str] = {
    # Multi-word commands (matched before single tokens)
    "कितने बाकी": "kitne baaki",
    "कौनसे बाकी": "kitne baaki",
    "कर दो": "kar do",
    # Commands
    "सबको": "sabko",
    "ग्रेस": "grace",
    "अनडू": "undo",
    "वापस": "undo",
    "कन्फर्म": "confirm",
    "कैंसल": "cancel",
    # Fractions
    "आधा": "aadha",
    "डेढ़": "dedh",
    "ढाई": "dhai",
    "साढ़े": "saadhe",
    "सावा से": "sava",
    "सावा": "sava",
    "सवा": "sava",
    "पौने": "paune",
    # Numbers 0-20
    "शून्य": "shunya",
    "जीरो": "zero",
    "एक": "ek",
    "दो": "do",
    "तीन": "teen",
    "चार": "char",
    "पांच": "paanch",
    "पाँच": "paanch",
    "छह": "chheh",
    "छे": "chheh",
    "छः": "chheh",
    "सात": "saat",
    "आठ": "aath",
    "नौ": "nau",
    "नो": "nau",
    "दस": "das",
    "ग्यारह": "gyarah",
    "बारह": "barah",
    "तेरह": "terah",
    "चौदह": "chaudah",
    "पंद्रह": "pandrah",
    "सोलह": "solah",
    "सत्रह": "satrah",
    "अठारह": "atharah",
    "उन्नीस": "unnis",
    "बीस": "bees",
}

_DEVANAGARI_TOKEN_RE = re.compile(
    r"(?<![\w\u0900-\u097F])("
    + "|".join(re.escape(k) for k in sorted(_DEVANAGARI_TOKEN_MAP, key=len, reverse=True))
    + r")(?![\w\u0900-\u097F])"
)

_DEVANAGARI_RUBRIC_MAP: dict[str, str] = {
    unicodedata.normalize("NFC", k): v
    for k, v in {
        # Clarity
        "क्लेरिटी": "Clarity",
        "क्लैरिटी": "Clarity",
        "क्लैरीटी": "Clarity",
        "क्लेअरिटी": "Clarity",
        # Depth
        "डेप्थ": "Depth",
        "डेफ्थ": "Depth",
        "देप्थ": "Depth",
        "डेप्ट": "Depth",
        "डेथ": "Depth",
        # Ethics
        "एथिक्स": "Ethics",
        "ऐथिक्स": "Ethics",
        "इथिक्स": "Ethics",
        "एथिक": "Ethics",
        # Composure
        "कंपोजर": "Composure",
        "कम्पोजर": "Composure",
        "कंपोज़र": "Composure",
        "कंपोसर": "Composure",
        "कंपोजचर": "Composure",
        "कंपोज़र": "Composure",
        # Other oral anchors
        "प्रेजेंटेशन": "Presentation",
        "प्रेज़ेंटेशन": "Presentation",
        "कंटेंट": "Content",
        "कॉन्टेंट": "Content",
        "कम्युनिकेशन": "Communication",
        "कॉन्फिडेंस": "Confidence",
    }.items()
}

_DEVANAGARI_RUBRIC_RE = re.compile(
    r"(?<![\w\u0900-\u097F])("
    + "|".join(re.escape(k) for k in sorted(_DEVANAGARI_RUBRIC_MAP, key=len, reverse=True))
    + r")(?![\w\u0900-\u097F])"
)

_SCORE_HOMOPHONE_MAP: dict[str, str] = {
    "आर्ट": "8",
    "आट": "8",
    "ना": "9",
    "नो": "9",
}

_SCORE_ANCHOR_OR_PREFIX_RE = re.compile(
    r"(?<![\w\u0900-\u097F])"
    r"(Q\d{1,2}|clarity|depth|ethics|composure|delivery|fluency|content|relevance|"
    r"communication|presentation|confidence|accuracy|composer|composers|ethic|claret|"
    r"saadhe|saade|sade|sadhe|saadhey|saare|sava|sawa|paune|pone|pawne)"
    r"(\s+)(आर्ट|आट|ना|नो)"
    r"(?![\w\u0900-\u097F])",
    re.IGNORECASE,
)


def _replace_clock_fraction(m: re.Match[str]) -> str:
    base = int(m.group(1))
    suffix = _CLOCK_FRACTION_SUFFIX[m.group(2)]
    return f"{base}{suffix}"


def normalize_asr_transcript(text: str) -> str:
    """
    Pre-normalize real-world Chrome Web Speech API (en-IN / hi-IN) transcripts
    before intent routing or anchor slicing.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFC", text)
    # 1. Devanagari digits -> ASCII digits
    out = out.translate(_DEVANAGARI_DIGITS)
    # 2. Clock-time Indian fractions -> decimals (e.g. 7:30 -> 7.5, 4:45 -> 4.75)
    out = re.sub(r"\b(\d{1,2}):(00|15|30|45)\b", _replace_clock_fraction, out)
    # 3. Devanagari & STT homophones for Roll / Candidate
    out = _CANDIDATE_RE.sub("candidate", out)
    out = _ROLL_HOMOPHONE_RE.sub("roll", out)
    # 4. Devanagari & STT homophones for Question Q<n>, collapse adjacent duplicates
    out = _Q_HOMOPHONE_RE.sub(r"Q\1", out)
    out = _DUP_Q_ANCHOR_RE.sub(lambda m: f"Q{m.group(1)[1:]}", out)
    # 5. Devanagari oral rubric anchors -> canonical English anchors
    out = _DEVANAGARI_RUBRIC_RE.sub(lambda m: _DEVANAGARI_RUBRIC_MAP[m.group(1)], out)
    # 6. Devanagari numbers, fractions & commands
    out = _DEVANAGARI_TOKEN_RE.sub(lambda m: _DEVANAGARI_TOKEN_MAP[m.group(1)], out)
    # 7. Anchor-scoped Devanagari numeral homophones (e.g. "Clarity आर्ट" -> "Clarity 8")
    out = _SCORE_ANCHOR_OR_PREFIX_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{_SCORE_HOMOPHONE_MAP[m.group(3)]}",
        out,
    )
    return re.sub(r"\s{2,}", " ", out).strip()


# ---------------------------------------------------------------------------
# Numeral & Fraction Lexer
# ---------------------------------------------------------------------------

HINDI_NUMERALS: dict[str, int] = {
    # zero
    "shunya": 0, "zero": 0,
    # 1-9
    "ek": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3,
    "char": 4, "chaar": 4, "four": 4, "paanch": 5, "panch": 5, "five": 5,
    "chheh": 6, "chhe": 6, "six": 6, "saat": 7, "sat": 7, "seven": 7,
    "aath": 8, "ath": 8, "eight": 8, "nau": 9, "nine": 9,
    # 10-19
    "das": 10, "ten": 10, "gyarah": 11, "gyaarah": 11, "eleven": 11,
    "barah": 12, "baarah": 12, "bara": 12, "twelve": 12,
    "terah": 13, "teerah": 13, "thirteen": 13,
    "chaudah": 14, "choda": 14, "fourteen": 14,
    "pandrah": 15, "fifteen": 15, "solah": 16, "sixteen": 16,
    "satrah": 17, "seventeen": 17, "atharah": 18, "attharah": 18, "eighteen": 18,
    "unnis": 19, "unees": 19, "nineteen": 19,
    # 20-25
    "bees": 20, "bis": 20, "twenty": 20,
    "ikkis": 21, "twenty one": 21, "twenty-one": 21,
    "baais": 22, "twenty two": 22, "twenty-two": 22,
    "teis": 23, "twenty three": 23, "twenty-three": 23,
    "chaubis": 24, "twenty four": 24, "twenty-four": 24,
    "pachees": 25, "twenty five": 25, "twenty-five": 25,
}

# Pattern: (fractional_add, multiplier) — applied as N*mult + add
# "saadhe N" → N + 0.5
# "sava N"  → N + 0.25
# "paune N" → N - 0.25
# "dedh"    → 1.5  (special, no following number)
# "dhai"    → 2.5  (special)
# "aadha"   → 0.5  (special)

SPECIAL_FRACTIONS: dict[str, float] = {
    "aadha": 0.5,
    "aadhe": 0.5,
    "dedh": 1.5,
    "dhai": 2.5,
}

FRACTION_PREFIX: dict[str, float] = {
    "saadhe": 0.5,
    "saade": 0.5,
    "sade": 0.5,
    "sadhe": 0.5,
    "saadhey": 0.5,
    "saare": 0.5,
    "sava": 0.25,
    "sawa": 0.25,
    "paune": -0.25,
    "pone": -0.25,
    "pawne": -0.25,
}

# Self-correction patterns — the token after the correction word is the final
SELF_CORRECTION_TOKENS = {
    "nahi", "nahi,", "sorry", "matlab", "means", "arey", "i mean",
    "correction", "correct", "wait", "actually", "arrey",
}

# Venting / tone words to strip
VENT_WORDS = {
    "are", "arey", "arrey", "yaar", "yar", "ye kya", "kya", "ghatiya",
    "bakwaas", "nonsense", "pagal", "stupid", "bura", "buri", "accha",
    "theek", "bahut", "bilkul", "ekdum", "absolutely",
}

# Polite rewrite map  word → educator tag
VENT_REWRITE: dict[str, str] = {
    "ghatiya": "needs improvement",
    "bakwaas": "unclear and incomplete",
    "nonsense": "off-topic",
    "pagal": "off-topic",
    "stupid": "needs improvement",
}

_DEVANAGARI_VENT_PHRASES: tuple[str, ...] = tuple(
    sorted(
        {
            unicodedata.normalize("NFC", p)
            for p in (
                "दिमाग खराब कर रहा है",
                "दिमाग खराब",
                "पर यह क्या बोल रहा है",
                "यह क्या बोल रहा है",
                "क्या बोल रहा है",
                "बकवास",
                "घटिया",
                "फालतू",
                "बेकार",
                "पता नहीं क्या",
                "अरे यार",
                "डिटॉल भी क्या आ गया है क्या",
            )
        },
        key=len,
        reverse=True,
    )
)

_CONSTRUCTIVE_REMARK_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"(?:करंट\s*अफेयर्स|current\s+affairs)", re.IGNORECASE),
        "needs improvement in Current Affairs",
        "करंट अफेयर्स में सुधार की आवश्यकता है",
    ),
    (
        re.compile(
            r"(?:ठीक\s*से\s*बोलते\s*नहीं\s*आता|बोल\s*नहीं\s*पा|speaking|articulation|fluency|hesitation)",
            re.IGNORECASE,
        ),
        "needs to work on speaking fluency and articulation",
        "बोलने के प्रवाह और स्पष्टता पर काम करने की आवश्यकता है",
    ),
    (
        re.compile(r"(?:डायग्राम|diagram)", re.IGNORECASE),
        "diagram clarity needs improvement",
        "डायग्राम की स्पष्टता में सुधार की आवश्यकता है",
    ),
    (
        re.compile(r"(?:कॉन्सेप्ट|concept|बेसिक|basics)", re.IGNORECASE),
        "conceptual clarity needs strengthening",
        "मूल अवधारणाओं को मजबूत करने की आवश्यकता है",
    ),
    (
        re.compile(r"(?:फॉर्मूला|formula|कैलकुलेशन|calculation)", re.IGNORECASE),
        "needs better accuracy in formulas and calculations",
        "सूत्रों और गणना में सटीकता की आवश्यकता है",
    ),
    (
        re.compile(r"(?:स्ट्रक्चर|good\s+structure)", re.IGNORECASE),
        "well-structured response",
        "उत्तर की संरचना अच्छी है",
    ),
)

# Roll-number patterns
ROLL_PATTERN = re.compile(
    r"\b(?:roll\s*(?:number|no|num)?\.?\s*|student\s+)(\d{1,5})\b",
    re.IGNORECASE,
)
# Written exam: Q1 … Q20, question 1 … question 20
Q_PATTERN = re.compile(
    r"\b(?:q(?:uestion)?\.?\s*)(\d{1,2})\b",
    re.IGNORECASE,
)
# Oral rubric items (case-insensitive anchors)
RUBRIC_PATTERN = re.compile(
    r"\b(clarity|depth|ethics|composure|delivery|fluency|content|relevance|communication|"
    r"presentation|confidence|accuracy)\b",
    re.IGNORECASE,
)

# Common en-IN STT homophones for oral rubric items
_ORAL_HOMOPHONE_MAP: dict[str, str] = {
    "composer": "Composure",
    "composers": "Composure",
    "ethic": "Ethics",
    "claret": "Clarity",
}

_GLUED_Q_RE = re.compile(
    r"\b(?:q(?:uestion)?\.?\s*)(\d{2,}(?:\.\d+)?)\b",
    re.IGNORECASE,
)

# Command verb patterns
EDIT_VERBS = re.compile(
    r"\b(edit|update(?:\s+to)?|change(?:\s+to)?|modify|correct|badlo|badal|sahi\s+karo|kar\s*do|kardo|bana\s*do|banado)\b",
    re.IGNORECASE,
)
UNDO_VERBS = re.compile(r"\b(undo|wapas|revert|cancel last|hatao)\b", re.IGNORECASE)
GRACE_VERBS = re.compile(
    r"\b(grace|bonus|extra marks?|add \d|sabko|sab ko|everyone|all students?)\b",
    re.IGNORECASE,
)
STATUS_VERBS = re.compile(
    r"\b(status|kitne|how many|progress|report|summary)\b",
    re.IGNORECASE,
)
FINISH_VERBS = re.compile(r"\b(finish|done|end|complete|khatam|submit)\b", re.IGNORECASE)
CONFIRM_VERBS = re.compile(r"\b(confirm|haan|yes|proceed|apply)\b", re.IGNORECASE)
CANCEL_VERBS = re.compile(r"\b(cancel|nahi|no|ruk|stop)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Numeral parsing helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lower-case, collapse whitespace, return word tokens."""
    return re.sub(r"\s+", " ", text.lower().strip()).split()


def _parse_number_tokens(tokens: list[str]) -> Optional[float]:
    """
    Try to parse a list of tokens as a single numeric value.
    Returns float or None.
    """
    text = " ".join(tokens)

    # Try direct digit
    try:
        return float(text)
    except ValueError:
        pass

    # Special fractions (no following number)
    if text in SPECIAL_FRACTIONS:
        return SPECIAL_FRACTIONS[text]

    # Fraction prefix + number  e.g. "saadhe teen" → 3.5, "saadhe 9" → 9.5
    for prefix, delta in FRACTION_PREFIX.items():
        if text.startswith(prefix + " "):
            rest = text[len(prefix) + 1 :].strip()
            base: Optional[float] = _lookup_hindi(rest)
            if base is None and re.fullmatch(r"\d+(?:\.\d+)?", rest):
                base = float(rest)
            if base is not None:
                return float(base) + delta

    # Direct Hindi numeral
    val = _lookup_hindi(text)
    if val is not None:
        return float(val)

    # Digit in text
    m = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if m:
        return float(m.group(1))

    return None


def _lookup_hindi(text: str) -> Optional[int]:
    """Single-token or multi-token Hindi lookup."""
    return HINDI_NUMERALS.get(text)


def collapse_self_corrections(tokens: list[str]) -> list[str]:
    """
    Remove self-corrections: if token[i] is a correction word,
    drop token[i-1] and token[i] (keep token[i+1] = the corrected value).
    Returns cleaned token list.
    """
    result = []
    i = 0
    while i < len(tokens):
        if tokens[i] in SELF_CORRECTION_TOKENS and i > 0:
            # Drop the previous token (incorrect value)
            if result:
                result.pop()
            # Also drop the correction word itself
            i += 1
        else:
            result.append(tokens[i])
            i += 1
    return result


def extract_number(text: str) -> Optional[float]:
    """
    Main entry point: extract a numeric score from a Hinglish phrase.
    Handles self-corrections, Hindi numerals, fractions, and plain digits.
    """
    normalized = normalize_asr_transcript(text)
    tokens = _tokenize(normalized)
    tokens = collapse_self_corrections(tokens)

    # Try multi-token windows from longest to shortest
    for length in range(min(len(tokens), 3), 0, -1):
        for start in range(len(tokens) - length + 1):
            window = tokens[start : start + length]
            val = _parse_number_tokens(window)
            if val is not None:
                return val
    return None


# ---------------------------------------------------------------------------
# Tone Sanitizer & Constructive Remark Extractor
# ---------------------------------------------------------------------------

def extract_constructive_remarks(text: str) -> list[dict[str, str]]:
    """
    Extract structured bilingual constructive remarks from Hinglish or Devanagari text.
    Returns deduplicated list of {"en": ..., "hi": ...} ordered by first appearance.
    """
    if not text:
        return []
    normalized = unicodedata.normalize("NFC", text)
    matches: list[tuple[int, str, str]] = []
    for pattern, en_phrase, hi_phrase in _CONSTRUCTIVE_REMARK_RULES:
        m = pattern.search(normalized)
        if m:
            matches.append((m.start(), en_phrase, hi_phrase))
    matches.sort(key=lambda item: item[0])

    seen: set[str] = set()
    remarks: list[dict[str, str]] = []
    for _, en_phrase, hi_phrase in matches:
        if en_phrase not in seen:
            seen.add(en_phrase)
            remarks.append({"en": en_phrase, "hi": hi_phrase})
    return remarks


def sanitize_tone(text: str) -> str:
    """
    Strip Devanagari/Hinglish vent words, filler, and ASR noise, and summarize
    constructive remarks into clean parent/candidate-ready phrasing.
    """
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFC", text)

    # 1. Strip Devanagari venting, filler, and ASR noise phrases
    for phrase in _DEVANAGARI_VENT_PHRASES:
        cleaned = cleaned.replace(phrase, " ")

    has_devanagari = bool(re.search(r"[\u0900-\u097F]", cleaned))
    lowered = cleaned.lower()

    had_vent_or_rewrite = any(rude in lowered for rude in VENT_REWRITE) or any(
        re.search(r"\b" + re.escape(word) + r"\b", lowered) for word in VENT_WORDS
    )

    # 2. Extract structured constructive remarks before stripping English tokens
    remarks = extract_constructive_remarks(cleaned)

    # 3. Apply English rewrites & strip simple vent words
    for rude, polite in VENT_REWRITE.items():
        lowered = lowered.replace(rude, polite)
    for word in sorted(VENT_WORDS, key=len, reverse=True):
        lowered = re.sub(r"\b" + re.escape(word) + r"\b", "", lowered)

    lowered = re.sub(r"\s{2,}", " ", lowered).strip(" ,-.")

    # 4. Prefer clean constructive summary when Devanagari speech or venting was present
    if remarks and (has_devanagari or had_vent_or_rewrite):
        summary = "; ".join(r["en"] for r in remarks)
        return summary[0].upper() + summary[1:] if summary else ""

    return lowered.capitalize() if lowered else ""


# ---------------------------------------------------------------------------
# Intent Router
# ---------------------------------------------------------------------------

@dataclass
class ParsedIntent:
    intent: str                    # GRADE | EDIT | UNDO | BULK_GRACE | STATUS | FINISH | IGNORE | CONFIRM | CANCEL
    roll_no: Optional[int] = None
    question: Optional[str] = None  # e.g. "Q3" or "Clarity"
    score: Optional[float] = None
    grace_marks: Optional[float] = None
    raw_text: str = ""
    sanitized_comment: str = ""
    mode: str = "written"           # "written" | "oral"
    extra: dict = field(default_factory=dict)


def _extract_roll(text: str) -> Optional[int]:
    m = ROLL_PATTERN.search(text)
    return int(m.group(1)) if m else None


def _canonicalize_oral_anchor(
    token: str,
    rubric_items: Optional[list[str]] = None,
) -> str:
    """Canonicalize an oral rubric token or homophone to its exact schema key."""
    low = token.lower()
    if rubric_items:
        schema_map = {r.lower(): r for r in rubric_items}
        if low in schema_map:
            return schema_map[low]
        if low in _ORAL_HOMOPHONE_MAP:
            target = _ORAL_HOMOPHONE_MAP[low].lower()
            if target in schema_map:
                return schema_map[target]
    if low in _ORAL_HOMOPHONE_MAP:
        return _ORAL_HOMOPHONE_MAP[low]
    return token.capitalize()


def _build_oral_anchor_pattern(
    rubric_items: Optional[list[str]] = None,
) -> re.Pattern[str]:
    """Build a case-insensitive regex matching active rubric items, homophones, and defaults."""
    default_rubric = [
        "clarity", "depth", "ethics", "composure", "delivery", "fluency",
        "content", "relevance", "communication", "presentation", "confidence", "accuracy",
    ]
    candidates: set[str] = set(default_rubric)
    if rubric_items:
        active_lower = {r.lower() for r in rubric_items}
        candidates.update(rubric_items)
        for alias, target in _ORAL_HOMOPHONE_MAP.items():
            if target.lower() in active_lower:
                candidates.add(alias)
    else:
        candidates.update(_ORAL_HOMOPHONE_MAP.keys())

    ordered = sorted(candidates, key=len, reverse=True)
    return re.compile(
        r"\b(" + "|".join(re.escape(c) for c in ordered) + r")\b",
        re.IGNORECASE,
    )


def rescue_glued_q_tokens(
    text: str,
    valid_anchors: Optional[list[str]] = None,
) -> str:
    """
    Schema-aware glued-digit rescue for written Q<digits> tokens.
    If Q<full> (e.g. Q39, Q39.5, Q17.5) is not in valid_anchors, split the first
    digit into Q<d> + <rest> when Q<d> is in valid_anchors, <rest> is numeric,
    and no separate score already follows that token.
    """
    if not valid_anchors:
        return text

    valid_set = {a.upper() for a in valid_anchors}
    matches = list(_GLUED_Q_RE.finditer(text))
    if not matches:
        return text

    # Also find all Q_PATTERN positions so we know where the next anchor starts
    all_q_starts = sorted({m.start() for m in Q_PATTERN.finditer(text)} | {m.start() for m in matches})

    parts: list[str] = []
    last_idx = 0
    for m in matches:
        full = m.group(1)
        full_anchor = f"Q{full}"
        if full_anchor.upper() in valid_set:
            continue

        first_digit = full[0]
        rest = full[1:]
        split_anchor = f"Q{first_digit}"
        if split_anchor.upper() not in valid_set:
            continue
        if not re.fullmatch(r"\d+(?:\.\d+)?", rest):
            continue

        # Find boundary before next Q-anchor
        next_starts = [pos for pos in all_q_starts if pos > m.start()]
        tail_end = next_starts[0] if next_starts else len(text)
        tail = text[m.end():tail_end]
        existing_score, _ = _extract_score_and_leftover(tail)
        if existing_score is not None:
            continue

        parts.append(text[last_idx:m.start()])
        parts.append(f"{split_anchor} {rest}")
        last_idx = m.end()

    if last_idx == 0:
        return text
    parts.append(text[last_idx:])
    return "".join(parts)


def _extract_anchor(
    text: str,
    mode: str = "written",
    questions: Optional[list[str]] = None,
    rubric_items: Optional[list[str]] = None,
) -> Optional[str]:
    """Return Q-anchor or rubric-anchor found in text, canonicalized to schema."""
    if mode == "written" and questions:
        for q in sorted(questions, key=len, reverse=True):
            if re.search(r"\b" + re.escape(q) + r"\b", text, re.IGNORECASE):
                return q
    elif mode == "oral":
        if rubric_items:
            for r in sorted(rubric_items, key=len, reverse=True):
                if re.search(r"\b" + re.escape(r) + r"\b", text, re.IGNORECASE):
                    return r
            active_lower = {r.lower(): r for r in rubric_items}
            for alias, target in _ORAL_HOMOPHONE_MAP.items():
                if target.lower() in active_lower and re.search(
                    r"\b" + re.escape(alias) + r"\b", text, re.IGNORECASE
                ):
                    return active_lower[target.lower()]

    m = Q_PATTERN.search(text)
    if m:
        return f"Q{m.group(1)}"
    oral_re = _build_oral_anchor_pattern(rubric_items if mode == "oral" else None)
    m = oral_re.search(text)
    if m:
        return _canonicalize_oral_anchor(m.group(1), rubric_items if mode == "oral" else None)
    return None


def _extract_score_and_leftover(
    text: str,
    rubric_items: Optional[list[str]] = None,
) -> tuple[Optional[float], str]:
    """
    Extract the first valid numeric score from a cleaned phrase and return
    (score, leftover_text) with the matched numeral/fraction tokens removed.
    """
    cleaned = ROLL_PATTERN.sub("", text)
    cleaned = Q_PATTERN.sub("", cleaned)
    cleaned = _build_oral_anchor_pattern(rubric_items).sub("", cleaned)
    for verb_re in (EDIT_VERBS, UNDO_VERBS, FINISH_VERBS, STATUS_VERBS):
        cleaned = verb_re.sub("", cleaned)

    raw_tokens = cleaned.split()
    if not raw_tokens:
        return None, ""

    # Track (normalized_token, original_index) and any collapsed correction indices
    collapsed: list[tuple[str, set[int]]] = []
    pending_dropped: set[int] = set()
    i = 0
    while i < len(raw_tokens):
        norm = raw_tokens[i].lower().strip(".,;:!?\"'()")
        if norm in SELF_CORRECTION_TOKENS and i > 0:
            if collapsed:
                _, prev_indices = collapsed.pop()
                pending_dropped.update(prev_indices)
            pending_dropped.add(i)
            i += 1
        else:
            indices = {i}
            if pending_dropped:
                indices.update(pending_dropped)
                pending_dropped.clear()
            collapsed.append((norm, indices))
            i += 1

    # Try multi-token windows from longest to shortest
    for length in range(min(len(collapsed), 3), 0, -1):
        for start in range(len(collapsed) - length + 1):
            window = collapsed[start : start + length]
            val = _parse_number_tokens([tok for tok, _ in window])
            if val is not None:
                matched_indices: set[int] = set()
                for _, idxs in window:
                    matched_indices.update(idxs)
                leftover_tokens = [
                    tok for idx, tok in enumerate(raw_tokens) if idx not in matched_indices
                ]
                leftover = " ".join(leftover_tokens)
                leftover = re.sub(r"\bko\b", "", leftover, flags=re.IGNORECASE)
                leftover = re.sub(r"\s{2,}", " ", leftover).strip(" ,-.")
                return val, leftover

    leftover = re.sub(r"\bko\b", "", cleaned, flags=re.IGNORECASE)
    leftover = re.sub(r"\s{2,}", " ", leftover).strip(" ,-.")
    return None, leftover


def _extract_score_from_residual(text: str, roll: Optional[int], anchor: Optional[str]) -> Optional[float]:
    """
    Extract score from text after removing roll-number and anchor tokens,
    so digits in "roll 5 Q3 teen" don't get mistaken for the score.
    """
    residual = text

    # Strip roll number context (e.g. "roll 5", "roll number 12")
    residual = ROLL_PATTERN.sub("", residual)

    # Strip anchor context (e.g. "Q3", "question 3", "Clarity")
    residual = Q_PATTERN.sub("", residual)
    residual = RUBRIC_PATTERN.sub("", residual)

    # Strip common filler that is NOT a score
    for verb_re in (EDIT_VERBS, UNDO_VERBS, FINISH_VERBS, STATUS_VERBS):
        residual = verb_re.sub("", residual)

    # Strip common preposition/filler around scores
    residual = re.sub(r"\b(to|ko|hai|diya|mila|dedo|marks?|score|out of|of)\b", "", residual, flags=re.IGNORECASE)

    return extract_number(residual.strip())


def route_intent(
    text: str,
    mode: str = "written",
    questions: Optional[list[str]] = None,
    rubric_items: Optional[list[str]] = None,
) -> ParsedIntent:
    """
    Route an utterance to the correct intent, extract roll/anchor/score.
    """
    raw_text = text
    text = normalize_asr_transcript(text)
    if mode == "written" and questions:
        text = rescue_glued_q_tokens(text, questions)
    lower = text.lower().strip()
    roll = _extract_roll(text)
    anchor = _extract_anchor(text, mode=mode, questions=questions, rubric_items=rubric_items)

    # --- CONFIRM / CANCEL (must come before GRADE checks) ---
    if CONFIRM_VERBS.search(lower):
        return ParsedIntent(intent="CONFIRM", raw_text=raw_text)
    if CANCEL_VERBS.search(lower) and not roll and not anchor:
        return ParsedIntent(intent="CANCEL", raw_text=raw_text)

    # --- UNDO ---
    if UNDO_VERBS.search(lower):
        return ParsedIntent(intent="UNDO", raw_text=raw_text)

    # --- FINISH ---
    if FINISH_VERBS.search(lower):
        return ParsedIntent(intent="FINISH", raw_text=raw_text)

    # --- STATUS ---
    if STATUS_VERBS.search(lower):
        return ParsedIntent(intent="STATUS", raw_text=raw_text)

    # --- BULK_GRACE ---
    if GRACE_VERBS.search(lower):
        # Strip anchor so question numbers like "Q3"'s 3 don't get mistaken for grace marks
        text_for_grace = text
        if anchor:
            text_for_grace = re.sub(r"\b" + re.escape(anchor) + r"\b", "", text_for_grace, flags=re.IGNORECASE)
        text_for_grace = Q_PATTERN.sub("", text_for_grace)
        text_for_grace = RUBRIC_PATTERN.sub("", text_for_grace)
        grace_val = extract_number(text_for_grace)
        return ParsedIntent(
            intent="BULK_GRACE",
            question=anchor,
            grace_marks=grace_val,
            raw_text=raw_text,
            mode=mode,
        )

    # --- EDIT ---
    if EDIT_VERBS.search(lower):
        score, leftover = _extract_score_and_leftover(text, rubric_items=rubric_items)
        comment = sanitize_tone(leftover) if leftover else ""
        return ParsedIntent(
            intent="EDIT",
            roll_no=roll,
            question=anchor,
            score=score,
            raw_text=raw_text,
            sanitized_comment=comment,
            mode=mode,
        )

    # --- GRADE or IGNORE ---
    # Score must be extracted from residual (after stripping roll/anchor/edit tokens)
    score, leftover = _extract_score_and_leftover(text, rubric_items=rubric_items)

    # Self-talk / no-anchor filter:
    # A valid GRADE requires BOTH a score AND an identity anchor (roll or rubric/question).
    # If a valid roll number is spoken without a score, preserve GRADE with score=None
    # so the API can return a helpful prompt instead of treating it as self-talk.
    has_identity = roll is not None or anchor is not None

    if not has_identity:
        return ParsedIntent(intent="IGNORE", raw_text=raw_text)

    if score is None:
        if roll is not None:
            return ParsedIntent(
                intent="GRADE",
                roll_no=roll,
                question=anchor,
                score=None,
                raw_text=raw_text,
                mode=mode,
            )
        return ParsedIntent(intent="IGNORE", raw_text=raw_text)

    comment = sanitize_tone(leftover) if leftover else ""
    return ParsedIntent(
        intent="GRADE",
        roll_no=roll,
        question=anchor,
        score=score,
        raw_text=raw_text,
        sanitized_comment=comment,
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Anchor Slicing
# ---------------------------------------------------------------------------

def slice_by_anchors(
    text: str,
    mode: str = "written",
    questions: Optional[list[str]] = None,
    rubric_items: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """
    Split a mid-dictation blob into per-question/rubric segments.
    Returns list of {anchor, score, comment, roll_no}.
    """
    text = normalize_asr_transcript(text)
    if mode == "written" and questions:
        text = rescue_glued_q_tokens(text, questions)
    results = []

    if mode == "written":
        pattern = Q_PATTERN
        q_schema_map = {q.upper(): q for q in questions} if questions else {}
    else:
        pattern = _build_oral_anchor_pattern(rubric_items)
        q_schema_map = {}

    matches = list(pattern.finditer(text))
    if not matches:
        return results

    # Propagate roll_no from utterance or individual segments
    current_roll = _extract_roll(text)

    for i, m in enumerate(matches):
        if mode == "oral":
            anchor = _canonicalize_oral_anchor(m.group(1), rubric_items)
        else:
            raw_q = f"Q{m.group(1)}"
            anchor = q_schema_map.get(raw_q.upper(), raw_q)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segment = text[start:end].strip()

        # Check if this segment sets a new roll number
        seg_roll = _extract_roll(segment)
        if seg_roll is not None:
            current_roll = seg_roll

        score, leftover = _extract_score_and_leftover(segment, rubric_items=rubric_items)
        comment = sanitize_tone(leftover) if leftover else ""

        item: dict[str, Any] = {
            "anchor": anchor,
            "score": score,
            "comment": comment,
        }
        if current_roll is not None:
            item["roll_no"] = current_roll
        results.append(item)

    return results


# ---------------------------------------------------------------------------
# Bilingual Feedback Generator
# ---------------------------------------------------------------------------

def _fmt_score(val: float) -> str:
    return str(int(val)) if val == int(val) else f"{val:g}"


def _join_en(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _join_hi(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} और {items[1]}"
    return ", ".join(items[:-1]) + f" और {items[-1]}"


def generate_bilingual_feedback(
    scores: dict[str, float],
    max_marks: float,
    mode: str = "written",
    include_transliteration: bool = False,
    comments: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """
    Generate grounded, category-specific + remark-aware 2-sentence summary
    in English + Hindi (Devanagari). Inspects ONLY actually graded items.
    """
    if not scores:
        return {
            "english": "No scores recorded yet.",
            "hindi": "अभी तक कोई अंक दर्ज नहीं।",
            "transliteration": "Abhi tak koi ank darj nahin.",
        }

    max_str = _fmt_score(max_marks)
    strengths: list[tuple[float, str]] = []
    moderate: list[tuple[float, str]] = []
    needs_focus: list[tuple[float, str]] = []

    for anchor, score in scores.items():
        pct = (score / max_marks) if max_marks > 0 else 0.0
        label = f"{anchor} ({_fmt_score(score)}/{max_str})"
        if pct >= 0.75:
            strengths.append((score, label))
        elif pct >= 0.55:
            moderate.append((score, label))
        else:
            needs_focus.append((score, label))

    strength_labels = [lbl for _, lbl in sorted(strengths, key=lambda x: -x[0])]
    moderate_labels = [lbl for _, lbl in sorted(moderate, key=lambda x: -x[0])]
    focus_labels = [lbl for _, lbl in sorted(needs_focus, key=lambda x: x[0])]

    # Sentence 1: Score-grounded category summary
    if strength_labels and focus_labels:
        if moderate_labels:
            s1_en = (
                f"Strong performance in {_join_en(strength_labels)}; "
                f"{_join_en(moderate_labels)} is solid, while {_join_en(focus_labels)} needs more focus."
            )
            s1_hi = (
                f"{_join_hi(strength_labels)} में उत्कृष्ट प्रदर्शन; "
                f"{_join_hi(moderate_labels)} संतोषजनक है, जबकि {_join_hi(focus_labels)} पर अधिक ध्यान देने की आवश्यकता है।"
            )
        else:
            s1_en = (
                f"Strong performance in {_join_en(strength_labels)}; "
                f"needs more focus on {_join_en(focus_labels)}."
            )
            s1_hi = (
                f"{_join_hi(strength_labels)} में उत्कृष्ट प्रदर्शन; "
                f"{_join_hi(focus_labels)} पर अधिक ध्यान देने की आवश्यकता है।"
            )
    elif strength_labels and moderate_labels:
        s1_en = (
            f"Strong performance in {_join_en(strength_labels)}; "
            f"{_join_en(moderate_labels)} is solid."
        )
        s1_hi = (
            f"{_join_hi(strength_labels)} में उत्कृष्ट प्रदर्शन; "
            f"{_join_hi(moderate_labels)} संतोषजनक है।"
        )
    elif moderate_labels and focus_labels:
        s1_en = (
            f"Solid effort in {_join_en(moderate_labels)}; "
            f"needs more focus on {_join_en(focus_labels)}."
        )
        s1_hi = (
            f"{_join_hi(moderate_labels)} में संतोषजनक प्रयास; "
            f"{_join_hi(focus_labels)} पर अधिक ध्यान देने की आवश्यकता है।"
        )
    elif strength_labels:
        prep = "in" if len(strength_labels) == 1 else "across"
        s1_en = f"Consistent strong performance {prep} {_join_en(strength_labels)}."
        s1_hi = f"{_join_hi(strength_labels)} में लगातार उत्कृष्ट प्रदर्शन।"
    elif moderate_labels:
        prep = "in" if len(moderate_labels) == 1 else "across"
        s1_en = f"Solid baseline performance {prep} {_join_en(moderate_labels)}; further polish can raise scores."
        s1_hi = f"{_join_hi(moderate_labels)} में संतोषजनक प्रदर्शन; अधिक अभ्यास से अंक और बेहतर हो सकते हैं।"
    else:
        prep = "in" if len(focus_labels) == 1 else "across"
        s1_en = f"Needs significant focus and revision {prep} {_join_en(focus_labels)}."
        s1_hi = f"{_join_hi(focus_labels)} में विशेष ध्यान और अभ्यास की आवश्यकता है।"

    # Sentence 2: Summarized spoken remarks (deduplicated across graded items)
    en_remarks: list[str] = []
    hi_remarks: list[str] = []
    seen_en: set[str] = set()
    seen_hi: set[str] = set()

    if comments:
        for anchor in scores:
            raw_comment = comments.get(anchor, "")
            if not raw_comment:
                continue
            extracted = extract_constructive_remarks(raw_comment)
            if extracted:
                for item in extracted:
                    if item["en"] not in seen_en:
                        seen_en.add(item["en"])
                        en_remarks.append(item["en"])
                    if item["hi"] not in seen_hi:
                        seen_hi.add(item["hi"])
                        hi_remarks.append(item["hi"])
            else:
                cleaned = sanitize_tone(raw_comment)
                if cleaned:
                    low_cleaned = cleaned[0].lower() + cleaned[1:]
                    if low_cleaned not in seen_en:
                        seen_en.add(low_cleaned)
                        en_remarks.append(low_cleaned)

    s2_en = f" Key remarks: {'; '.join(en_remarks)}." if en_remarks else ""
    s2_hi = f" मुख्य टिप्पणियाँ: {'; '.join(hi_remarks)}." if hi_remarks else ""

    result = {
        "english": s1_en + s2_en,
        "hindi": s1_hi + s2_hi,
    }
    if include_transliteration:
        result["transliteration"] = (
            "Pradarshan ka vishleshan darj ankon par aadharit hai."
        )
    return result


generate_feedback = generate_bilingual_feedback


# ---------------------------------------------------------------------------
# Weakness Heatmap
# ---------------------------------------------------------------------------

def build_weakness_heatmap(
    all_tags: list[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """
    Aggregate error tags per rubric/question item across all students.
    all_tags: list of {"anchor": str, "tags": list[str]}
    Returns: {anchor → {tag → count}}
    """
    heatmap: dict[str, dict[str, int]] = {}
    for entry in all_tags:
        anchor = entry.get("anchor", "unknown")
        if anchor not in heatmap:
            heatmap[anchor] = {}
        for tag in entry.get("tags", []):
            heatmap[anchor][tag] = heatmap[anchor].get(tag, 0) + 1
    return heatmap
