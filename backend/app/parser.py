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
from dataclasses import dataclass, field
from typing import Any, Optional


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
    "aath": 8, "eight": 8, "nau": 9, "nine": 9,
    # 10-19
    "das": 10, "ten": 10, "gyarah": 11, "eleven": 11,
    "barah": 12, "twelve": 12, "terah": 13, "thirteen": 13,
    "chaudah": 14, "choda": 14, "fourteen": 14,
    "pandrah": 15, "fifteen": 15, "solah": 16, "sixteen": 16,
    "satrah": 17, "seventeen": 17, "atharah": 18, "eighteen": 18,
    "unnis": 19, "nineteen": 19,
    # 20-25
    "bees": 20, "twenty": 20,
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
    "sava": 0.25,
    "paune": -0.25,
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
    r"\b(clarity|depth|delivery|fluency|content|relevance|communication|"
    r"presentation|confidence|accuracy)\b",
    re.IGNORECASE,
)

# Command verb patterns
EDIT_VERBS = re.compile(
    r"\b(edit|update|change|modify|correct|badlo|badal|sahi karo)\b",
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

    # Fraction prefix + number  e.g. "saadhe teen" → 3.5
    for prefix, delta in FRACTION_PREFIX.items():
        if text.startswith(prefix + " "):
            rest = text[len(prefix) + 1 :]
            base = _lookup_hindi(rest)
            if base is not None:
                return base + delta

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
    tokens = _tokenize(text)
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
# Tone Sanitizer
# ---------------------------------------------------------------------------

def sanitize_tone(text: str) -> str:
    """
    Strip vent words and rewrite rude phrases into polite educator tags.
    """
    lowered = text.lower()

    # Apply rewrites first
    for rude, polite in VENT_REWRITE.items():
        lowered = lowered.replace(rude, polite)

    # Strip simple vent words
    for word in sorted(VENT_WORDS, key=len, reverse=True):
        lowered = re.sub(r"\b" + re.escape(word) + r"\b", "", lowered)

    # Clean up spacing/punctuation artifacts
    lowered = re.sub(r"\s{2,}", " ", lowered).strip(" ,-.")
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


def _extract_anchor(text: str) -> Optional[str]:
    """Return Q-anchor or rubric-anchor found in text."""
    m = Q_PATTERN.search(text)
    if m:
        return f"Q{m.group(1)}"
    m = RUBRIC_PATTERN.search(text)
    if m:
        return m.group(1).capitalize()
    return None


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


def route_intent(text: str, mode: str = "written") -> ParsedIntent:
    """
    Route an utterance to the correct intent, extract roll/anchor/score.
    """
    lower = text.lower().strip()
    roll = _extract_roll(text)
    anchor = _extract_anchor(text)

    # --- CONFIRM / CANCEL (must come before GRADE checks) ---
    if CONFIRM_VERBS.search(lower):
        return ParsedIntent(intent="CONFIRM", raw_text=text)
    if CANCEL_VERBS.search(lower) and not roll and not anchor:
        return ParsedIntent(intent="CANCEL", raw_text=text)

    # --- UNDO ---
    if UNDO_VERBS.search(lower):
        return ParsedIntent(intent="UNDO", raw_text=text)

    # --- FINISH ---
    if FINISH_VERBS.search(lower):
        return ParsedIntent(intent="FINISH", raw_text=text)

    # --- STATUS ---
    if STATUS_VERBS.search(lower):
        return ParsedIntent(intent="STATUS", raw_text=text)

    # --- BULK_GRACE ---
    if GRACE_VERBS.search(lower):
        # For grace, extract digits from the full text
        grace_val = extract_number(text)
        return ParsedIntent(
            intent="BULK_GRACE",
            grace_marks=grace_val,
            raw_text=text,
        )

    # --- EDIT ---
    if EDIT_VERBS.search(lower):
        score = _extract_score_from_residual(text, roll, anchor)
        return ParsedIntent(
            intent="EDIT",
            roll_no=roll,
            question=anchor,
            score=score,
            raw_text=text,
            mode=mode,
        )

    # --- GRADE or IGNORE ---
    # Score must be extracted from residual (after stripping roll/anchor tokens)
    score = _extract_score_from_residual(text, roll, anchor)

    # Self-talk / no-anchor filter:
    # A valid GRADE requires BOTH a score AND an identity anchor (roll or rubric/question).
    # If either is missing, treat as self-talk → IGNORE.
    has_identity = roll is not None or anchor is not None

    if not has_identity:
        return ParsedIntent(intent="IGNORE", raw_text=text)

    if score is None:
        # Has identity but no score — might be a partial utterance or status check
        return ParsedIntent(intent="IGNORE", raw_text=text)

    comment = sanitize_tone(text)
    return ParsedIntent(
        intent="GRADE",
        roll_no=roll,
        question=anchor,
        score=score,
        raw_text=text,
        sanitized_comment=comment,
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Anchor Slicing
# ---------------------------------------------------------------------------

def slice_by_anchors(text: str, mode: str = "written") -> list[dict[str, Any]]:
    """
    Split a mid-dictation blob into per-question/rubric segments.
    Returns list of {anchor, score, comment, roll_no}.
    """
    results = []

    if mode == "written":
        pattern = Q_PATTERN
    else:
        pattern = RUBRIC_PATTERN

    matches = list(pattern.finditer(text))
    if not matches:
        return results

    # Propagate roll_no from utterance or individual segments
    current_roll = _extract_roll(text)

    for i, m in enumerate(matches):
        anchor = m.group(1) if mode == "oral" else f"Q{m.group(1)}"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segment = text[start:end].strip()

        # Check if this segment sets a new roll number
        seg_roll = _extract_roll(segment)
        if seg_roll is not None:
            current_roll = seg_roll

        score = extract_number(segment)
        comment = sanitize_tone(segment)

        # If comment is only a lone numeral/fraction matching the score, drop it
        if score is not None and len(comment.split()) <= 2 and extract_number(comment) == score:
            comment = ""

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

FEEDBACK_TEMPLATES_EN = {
    "strong":   "Student demonstrated solid understanding with consistent performance.",
    "average":  "Student showed partial understanding; focus on improving weaker areas.",
    "weak":     "Student needs significant revision; multiple core areas require attention.",
    "oral_strong":   "Candidate communicated ideas clearly with good depth and delivery.",
    "oral_average":  "Candidate showed reasonable communication; some areas need polish.",
    "oral_weak":     "Candidate struggled with clarity and depth; more practice recommended.",
}

FEEDBACK_TEMPLATES_HI = {
    "strong":   "छात्र ने ठोस समझ और सुसंगत प्रदर्शन दिखाया।",
    "average":  "छात्र ने आंशिक समझ दिखाई; कमज़ोर क्षेत्रों पर ध्यान दें।",
    "weak":     "छात्र को महत्वपूर्ण संशोधन की आवश्यकता है; कई मूल क्षेत्रों पर काम करें।",
    "oral_strong":   "उम्मीदवार ने स्पष्टता और गहराई के साथ विचार व्यक्त किए।",
    "oral_average":  "उम्मीदवार ने उचित संचार दिखाया; कुछ क्षेत्रों में सुधार की आवश्यकता है।",
    "oral_weak":     "उम्मीदवार को स्पष्टता और गहराई में सुधार की आवश्यकता है।",
}

FEEDBACK_TEMPLATES_HI_TRANSLIT = {
    "strong":   "Chhatr ne thos samajh aur susangat pradarshan dikhaaya.",
    "average":  "Chhatr ne aanshik samajh dikhaai; kamzor kshetron par dhyan den.",
    "weak":     "Chhatr ko mahatvapurn sanshodhan ki aavashyakta hai.",
    "oral_strong":   "Ummeedvar ne spashtta aur gahraayi se vichar vyakt kiye.",
    "oral_average":  "Ummeedvar ne uchit sanchaar dikhaaya; kuch kshetron mein sudhaar chahiye.",
    "oral_weak":     "Ummeedvar ko spashtta aur gahraayi mein sudhaar ki zaroorat hai.",
}


def _score_tier(avg: float, max_marks: float, mode: str) -> str:
    pct = avg / max_marks if max_marks else 0
    prefix = "oral_" if mode == "oral" else ""
    if pct >= 0.75:
        return prefix + "strong"
    if pct >= 0.45:
        return prefix + "average"
    return prefix + "weak"


def generate_feedback(
    scores: dict[str, float],
    max_marks: float,
    mode: str = "written",
    include_transliteration: bool = False,
) -> dict[str, str]:
    """
    Generate 2-line PTM/candidate summary in English + Hindi.
    scores: {anchor → score}
    """
    if not scores:
        return {
            "english": "No scores recorded yet.",
            "hindi": "अभी तक कोई अंक दर्ज नहीं।",
            "transliteration": "Abhi tak koi ank darj nahin.",
        }

    avg = sum(scores.values()) / len(scores)
    tier = _score_tier(avg, max_marks, mode)

    result = {
        "english": FEEDBACK_TEMPLATES_EN[tier],
        "hindi": FEEDBACK_TEMPLATES_HI[tier],
    }
    if include_transliteration:
        result["transliteration"] = FEEDBACK_TEMPLATES_HI_TRANSLIT[tier]
    return result


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
