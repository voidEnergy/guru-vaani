"""
state.py — Session state, guardrails, undo stack, and bulk-grace flow.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScoreEntry:
    roll_no: int
    anchor: str              # "Q3" or "Clarity"
    score: float
    max_marks: float
    comment: str = ""
    tags: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class UndoFrame:
    """Snapshot of the score table before an operation."""
    description: str
    snapshot: dict[int, dict[str, ScoreEntry]]


@dataclass
class SessionConfig:
    mode: str = "written"            # "written" | "oral"
    questions: list[str] = field(default_factory=list)   # ["Q1","Q2",...]
    rubric_items: list[str] = field(default_factory=list)  # ["Clarity","Depth",...]
    max_marks: float = 10.0
    known_rolls: set[int] = field(default_factory=set)
    allow_unknown_rolls: bool = False


class GradeSession:
    """
    Manages a single grading session: scores, undo stack, bulk-grace queue.
    """

    def __init__(self, config: SessionConfig):
        self.session_id: str = str(uuid.uuid4())
        self.config = config
        # scores[roll_no][anchor] = ScoreEntry
        self.scores: dict[int, dict[str, ScoreEntry]] = {}
        self.undo_stack: list[UndoFrame] = []
        # Pending bulk-grace waiting for confirm/cancel
        self.pending_grace: Optional[dict[str, Any]] = None
        self.finished: bool = False
        # Error tags per roll+anchor for heatmap
        self.error_tags: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict[int, dict[str, ScoreEntry]]:
        return copy.deepcopy(self.scores)

    def _push_undo(self, description: str) -> None:
        self.undo_stack.append(UndoFrame(description=description, snapshot=self._snapshot()))

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_roll(self, roll_no: int) -> Optional[str]:
        if not self.config.allow_unknown_rolls and roll_no not in self.config.known_rolls:
            return (
                f"Roll number {roll_no} is not in the class list. "
                f"Please verify and try again."
            )
        return None

    def _validate_score(self, score: float) -> Optional[str]:
        if score < 0:
            return f"Score {score} is below 0. Scores cannot be negative."
        if score > self.config.max_marks:
            return (
                f"Score {score} exceeds maximum marks ({self.config.max_marks}). "
                f"Please use a valid score."
            )
        return None

    def _validate_anchor(self, anchor: str) -> Optional[str]:
        if self.config.mode == "written" and self.config.questions:
            if anchor not in self.config.questions:
                return f"Question '{anchor}' is not in the question list."
        if self.config.mode == "oral" and self.config.rubric_items:
            if anchor not in self.config.rubric_items:
                return f"Rubric item '{anchor}' is not in the rubric."
        return None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def apply_grade(
        self,
        roll_no: int,
        anchor: str,
        score: float,
        comment: str = "",
        is_edit: bool = False,
    ) -> dict[str, Any]:
        """
        Apply a grade. Returns {"ok": bool, "message": str, ...}
        """
        err = self._validate_roll(roll_no)
        if err:
            return {"ok": False, "message": err, "voice_error": err}

        err = self._validate_score(score)
        if err:
            return {"ok": False, "message": err, "voice_error": err}

        err = self._validate_anchor(anchor)
        if err:
            return {"ok": False, "message": err, "voice_error": err}

        # Duplicate-grade guard (without edit verb)
        existing = self.scores.get(roll_no, {}).get(anchor)
        if existing is not None and not is_edit:
            msg = (
                f"Roll {roll_no} {anchor} already has score {existing.score}. "
                f"Say 'edit' to update it."
            )
            return {"ok": False, "message": msg, "voice_error": msg}

        self._push_undo(f"grade roll={roll_no} {anchor}={score}")
        entry = ScoreEntry(
            roll_no=roll_no,
            anchor=anchor,
            score=score,
            max_marks=self.config.max_marks,
            comment=comment,
        )
        # Extract tags from comment
        if comment:
            entry.tags = _extract_tags(comment)
        if roll_no not in self.scores:
            self.scores[roll_no] = {}
        self.scores[roll_no][anchor] = entry

        # Accumulate for heatmap
        if entry.tags:
            self.error_tags.append({"anchor": anchor, "tags": entry.tags})

        return {
            "ok": True,
            "message": f"Saved: Roll {roll_no} {anchor} = {score}/{self.config.max_marks}",
            "entry": _entry_dict(entry),
        }

    def apply_edit(
        self,
        roll_no: int,
        anchor: str,
        score: float,
        comment: str = "",
    ) -> dict[str, Any]:
        return self.apply_grade(roll_no, anchor, score, comment, is_edit=True)

    def apply_undo(self) -> dict[str, Any]:
        if not self.undo_stack:
            return {"ok": False, "message": "Nothing to undo."}
        frame = self.undo_stack.pop()
        self.scores = frame.snapshot
        return {"ok": True, "message": f"Undone: {frame.description}"}

    # ------------------------------------------------------------------
    # Bulk Grace
    # ------------------------------------------------------------------

    def queue_bulk_grace(self, marks: float) -> dict[str, Any]:
        """Stage a bulk-grace operation waiting for confirmation."""
        err = self._validate_score(marks)
        if err:
            return {"ok": False, "message": err, "voice_error": err}
        self.pending_grace = {"marks": marks}
        affected = len(self.scores)
        return {
            "ok": True,
            "pending": True,
            "message": (
                f"About to add {marks} grace mark(s) to all {affected} student(s). "
                f"Say 'confirm' to apply or 'cancel' to abort."
            ),
        }

    def confirm_bulk_grace(self) -> dict[str, Any]:
        if not self.pending_grace:
            return {"ok": False, "message": "No pending grace operation."}
        marks = self.pending_grace["marks"]
        self._push_undo(f"bulk_grace +{marks}")
        count = 0
        for roll_scores in self.scores.values():
            for entry in roll_scores.values():
                new_score = min(entry.score + marks, self.config.max_marks)
                entry.score = new_score
                count += 1
        self.pending_grace = None
        return {"ok": True, "message": f"Grace of {marks} applied to {count} score(s)."}

    def cancel_bulk_grace(self) -> dict[str, Any]:
        if not self.pending_grace:
            return {"ok": False, "message": "No pending grace operation to cancel."}
        self.pending_grace = None
        return {"ok": True, "message": "Bulk grace cancelled."}

    # ------------------------------------------------------------------
    # Status & Export
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        total_students = len(self.scores)
        total_entries = sum(len(v) for v in self.scores.values())
        return {
            "session_id": self.session_id,
            "mode": self.config.mode,
            "students_graded": total_students,
            "total_entries": total_entries,
            "undo_depth": len(self.undo_stack),
            "pending_grace": self.pending_grace,
            "finished": self.finished,
        }

    def export_data(self) -> dict[str, Any]:
        """Full export: all scores, per-student averages."""
        from app.parser import generate_feedback, build_weakness_heatmap

        rows = []
        for roll_no, anchors in self.scores.items():
            for anchor, entry in anchors.items():
                rows.append(_entry_dict(entry))

        # Per-student averages & feedback
        student_summaries = []
        for roll_no, anchors in self.scores.items():
            score_map = {a: e.score for a, e in anchors.items()}
            avg = sum(score_map.values()) / len(score_map) if score_map else 0
            feedback = generate_feedback(
                score_map, self.config.max_marks, self.config.mode
            )
            student_summaries.append(
                {
                    "roll_no": roll_no,
                    "average": round(avg, 2),
                    "scores": score_map,
                    "feedback": feedback,
                }
            )

        heatmap = build_weakness_heatmap(self.error_tags)

        return {
            "session_id": self.session_id,
            "mode": self.config.mode,
            "max_marks": self.config.max_marks,
            "scores": rows,
            "student_summaries": student_summaries,
            "weakness_heatmap": heatmap,
        }

    def finish(self) -> dict[str, Any]:
        self.finished = True
        return {"ok": True, "message": "Session marked as finished.", "session_id": self.session_id}


# ---------------------------------------------------------------------------
# In-memory session store (single-process dev; replace with Redis for prod)
# ---------------------------------------------------------------------------

_sessions: dict[str, GradeSession] = {}


def create_session(config: SessionConfig) -> GradeSession:
    sess = GradeSession(config)
    _sessions[sess.session_id] = sess
    return sess


def get_session(session_id: str) -> Optional[GradeSession]:
    return _sessions.get(session_id)


def delete_session(session_id: str) -> bool:
    return _sessions.pop(session_id, None) is not None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _entry_dict(entry: ScoreEntry) -> dict[str, Any]:
    return {
        "roll_no": entry.roll_no,
        "anchor": entry.anchor,
        "score": entry.score,
        "max_marks": entry.max_marks,
        "comment": entry.comment,
        "tags": entry.tags,
        "timestamp": entry.timestamp,
    }


def _extract_tags(comment: str) -> list[str]:
    """Extract meaningful educator tags from a sanitized comment."""
    TAG_PATTERNS = [
        (r"diagram unclear|diagram.*needs improvement|needs improvement.*diagram", "diagram unclear"),
        (r"missing labels?", "missing labels"),
        (r"needs improvement", "needs improvement"),
        (r"unclear and incomplete", "unclear and incomplete"),
        (r"off.topic", "off-topic"),
        (r"incomplete", "incomplete"),
        (r"good", "good"),
        (r"excellent", "excellent"),
        (r"partial", "partial credit"),
        (r"wrong formula", "wrong formula"),
        (r"calculation error", "calculation error"),
        (r"good attempt", "good attempt"),
    ]
    tags = []
    low = comment.lower()
    for pattern, tag in TAG_PATTERNS:
        if re.search(pattern, low):
            tags.append(tag)
    return tags


import re


# ---------------------------------------------------------------------------
# Module-level aliases (used by main.py imports)
# ---------------------------------------------------------------------------

def confirm_bulk_grace(session: "GradeSession") -> dict:
    """Module-level wrapper for GradeSession.confirm_bulk_grace()."""
    return session.confirm_bulk_grace()


def cancel_bulk_grace(session: "GradeSession") -> dict:
    """Module-level wrapper for GradeSession.cancel_bulk_grace()."""
    return session.cancel_bulk_grace()
