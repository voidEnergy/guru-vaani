"""
main.py — FastAPI application entry point for Guru-Vaani backend.

Endpoints:
  GET  /api/health
  POST /api/session/init
  POST /api/voice/command
  POST /api/session/confirm-grace
  POST /api/session/manual-edit
  GET  /api/session/export-data
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.cloud_adapter import enhance_feedback_cloud, get_engine_info
from app.parser import (
    build_weakness_heatmap,
    extract_number,
    generate_feedback,
    route_intent,
    slice_by_anchors,
)
from app.state import (
    GradeSession,
    SessionConfig,
    create_session,
    delete_session,
    get_session,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Guru-Vaani Grading API",
    description="Deterministic Hinglish voice-grading engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SessionInitRequest(BaseModel):
    mode: str = Field("written", description="'written' or 'oral'")
    questions: list[str] = Field(default_factory=list, description="e.g. ['Q1','Q2']")
    rubric_items: list[str] = Field(default_factory=list, description="e.g. ['Clarity','Depth']")
    max_marks: float = Field(10.0, ge=0)
    known_rolls: list[int] = Field(default_factory=list)
    allow_unknown_rolls: bool = False


class VoiceCommandRequest(BaseModel):
    session_id: str
    transcript: str
    mode: Optional[str] = None  # override session mode if needed


class ManualEditRequest(BaseModel):
    session_id: str
    roll_no: int
    anchor: str
    score: float
    comment: Optional[str] = ""


class ConfirmGraceRequest(BaseModel):
    session_id: str
    action: str = Field("confirm", description="'confirm' or 'cancel'")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session_or_404(session_id: str) -> GradeSession:
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return sess


def _engine_info_from_headers(
    x_gemini_key: Optional[str],
    x_openai_key: Optional[str],
) -> dict:
    return get_engine_info(gemini_key=x_gemini_key, openai_key=x_openai_key)


def _schema_error(sess: GradeSession, mode: str, anchor: Optional[str]) -> Optional[str]:
    if not anchor:
        return None
    canonical = sess.canonicalize_anchor(anchor)
    if mode == "written" and sess.config.questions and canonical not in sess.config.questions:
        return f"{anchor} is not in this exam. Valid questions: {', '.join(sess.config.questions)}."
    if mode == "oral" and sess.config.rubric_items and canonical not in sess.config.rubric_items:
        return f"{anchor} is not in this exam. Valid rubric items: {', '.join(sess.config.rubric_items)}."
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health(
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
) -> dict:
    engine = _engine_info_from_headers(x_gemini_key, x_openai_key)
    return {
        "status": "ok",
        "service": "guru-vaani-backend",
        "version": "1.0.0",
        "engine": engine,
    }


@app.post("/api/session/init")
async def session_init(body: SessionInitRequest) -> dict:
    config = SessionConfig(
        mode=body.mode,
        questions=body.questions,
        rubric_items=body.rubric_items,
        max_marks=body.max_marks,
        known_rolls=set(body.known_rolls),
        allow_unknown_rolls=body.allow_unknown_rolls,
    )
    sess = create_session(config)
    return {
        "session_id": sess.session_id,
        "mode": config.mode,
        "max_marks": config.max_marks,
        "questions": config.questions,
        "rubric_items": config.rubric_items,
        "known_rolls": list(config.known_rolls),
    }


@app.post("/api/voice/command")
async def voice_command(
    body: VoiceCommandRequest,
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
) -> dict[str, Any]:
    sess = _get_session_or_404(body.session_id)
    mode = body.mode or sess.config.mode
    engine = _engine_info_from_headers(x_gemini_key, x_openai_key)

    parsed = route_intent(
        body.transcript,
        mode=mode,
        questions=sess.config.questions,
        rubric_items=sess.config.rubric_items,
    )
    intent = parsed.intent

    # --- IGNORE ---
    if intent == "IGNORE":
        return {
            "intent": "ignore",
            "message": "Utterance classified as self-talk; nothing saved.",
            "engine": engine,
        }

    # --- UNDO ---
    if intent == "UNDO":
        result = sess.apply_undo()
        return {"intent": "undo", **result, "engine": engine}

    # --- FINISH ---
    if intent == "FINISH":
        result = sess.finish()
        return {"intent": "finish", **result, "engine": engine}

    # --- STATUS ---
    if intent == "STATUS":
        return {"intent": "status", "status": sess.get_status(), "engine": engine}

    # --- CONFIRM ---
    if intent == "CONFIRM":
        result = sess.confirm_bulk_grace()
        return {"intent": "confirm_grace", **result, "engine": engine}

    # --- CANCEL ---
    if intent == "CANCEL":
        result = sess.cancel_bulk_grace()
        return {"intent": "cancel_grace", **result, "engine": engine}

    # --- BULK_GRACE ---
    if intent == "BULK_GRACE":
        if parsed.grace_marks is None:
            return {
                "intent": "bulk_grace",
                "ok": False,
                "message": "Could not parse grace marks amount from utterance.",
                "voice_error": "Please specify the grace mark amount.",
                "engine": engine,
            }
        if not parsed.question:
            target_type = "rubric item" if mode == "oral" else "question"
            msg = f"Please specify which {target_type} to apply grace marks to."
            return {
                "intent": "bulk_grace",
                "ok": False,
                "message": msg,
                "voice_error": msg,
                "engine": engine,
            }
        result = sess.queue_bulk_grace(parsed.grace_marks, question=parsed.question)
        return {"intent": "bulk_grace", **result, "engine": engine}

    # --- GRADE / EDIT ---
    if intent in ("GRADE", "EDIT"):
        is_edit = intent == "EDIT"

        # Try multi-anchor slicing first
        segments = slice_by_anchors(
            body.transcript,
            mode=mode,
            questions=sess.config.questions,
            rubric_items=sess.config.rubric_items,
        )
        scored_segments = [seg for seg in segments if seg["score"] is not None]

        roll_no = parsed.roll_no
        if roll_no is None and segments:
            for seg in segments:
                if seg.get("roll_no") is not None:
                    roll_no = seg["roll_no"]
                    break

        if scored_segments and roll_no is not None:
            results = []
            for seg in scored_segments:
                seg_roll = seg.get("roll_no") or roll_no
                schema_err = _schema_error(sess, mode, seg["anchor"])
                if schema_err:
                    r = {"ok": False, "message": schema_err, "voice_error": schema_err}
                else:
                    r = sess.apply_grade(
                        roll_no=seg_roll,
                        anchor=seg["anchor"],
                        score=seg["score"],
                        comment=seg["comment"],
                        is_edit=is_edit,
                    )
                results.append({**r, "anchor": seg["anchor"], "roll_no": seg_roll})

            if results and all(not r.get("ok") for r in results):
                err_msg = " | ".join(
                    r.get("voice_error") or r.get("message", "Command rejected.")
                    for r in results
                )
                return {
                    "intent": intent.lower(),
                    "ok": False,
                    "roll_no": roll_no,
                    "message": err_msg,
                    "voice_error": err_msg,
                    "results": results,
                    "engine": engine,
                }

            total = sum(
                entry.score
                for entry in sess.scores.get(roll_no, {}).values()
            )
            response: dict[str, Any] = {
                "intent": intent.lower(),
                "ok": True,
                "multi": True,
                "roll_no": roll_no,
                "total": round(total, 2),
                "results": results,
                "engine": engine,
            }
            unscored_anchors = list(
                dict.fromkeys(seg["anchor"] for seg in segments if seg["score"] is None)
            )
            if unscored_anchors:
                note = f"Missing score for {', '.join(unscored_anchors)} — skipped."
                response["warning"] = note
                response["message"] = note
                response["skipped_anchors"] = unscored_anchors
            return response

        # Single grade or incomplete command
        if parsed.roll_no is None:
            return {
                "intent": intent.lower(),
                "ok": False,
                "message": "Roll number not found in utterance.",
                "voice_error": "Please say the roll number before the score.",
                "engine": engine,
            }
        if parsed.score is None:
            roll_err = sess._validate_roll(parsed.roll_no)
            if roll_err:
                return {
                    "intent": intent.lower(),
                    "ok": False,
                    "roll_no": parsed.roll_no,
                    "message": roll_err,
                    "voice_error": roll_err,
                    "engine": engine,
                }
            schema_err = _schema_error(sess, mode, parsed.question)
            if schema_err:
                return {
                    "intent": intent.lower(),
                    "ok": False,
                    "roll_no": parsed.roll_no,
                    "message": schema_err,
                    "voice_error": schema_err,
                    "engine": engine,
                }
            if parsed.question:
                msg = f"Heard Roll {parsed.roll_no} {parsed.question} — please include the marks."
            else:
                target = "rubric item" if mode == "oral" else "question"
                msg = f"Heard Roll {parsed.roll_no} — please include the {target} and marks."
            return {
                "intent": intent.lower(),
                "ok": False,
                "roll_no": parsed.roll_no,
                "message": msg,
                "voice_error": msg,
                "engine": engine,
            }
        if parsed.question is None:
            return {
                "intent": intent.lower(),
                "ok": False,
                "message": "Question or rubric anchor not found.",
                "voice_error": "Please say the question or rubric item before the score.",
                "engine": engine,
            }
        schema_err = _schema_error(sess, mode, parsed.question)
        if schema_err:
            return {
                "intent": intent.lower(),
                "ok": False,
                "roll_no": parsed.roll_no,
                "message": schema_err,
                "voice_error": schema_err,
                "engine": engine,
            }

        result = sess.apply_grade(
            roll_no=parsed.roll_no,
            anchor=parsed.question,
            score=parsed.score,
            comment=parsed.sanitized_comment,
            is_edit=is_edit,
        )

        # Optionally enhance comment via cloud
        if result.get("ok") and engine["engine_mode"] != "local" and parsed.sanitized_comment:
            enhanced = await enhance_feedback_cloud(
                f"Rewrite this educator comment professionally in one sentence: {parsed.sanitized_comment}",
                engine,
            )
            if enhanced:
                result["enhanced_comment"] = enhanced

        student_total = round(
            sum(entry.score for entry in sess.scores.get(parsed.roll_no, {}).values()),
            2,
        )
        return {
            "intent": intent.lower(),
            "roll_no": parsed.roll_no,
            "total": student_total,
            **result,
            "engine": engine,
        }

    return {"intent": "unknown", "ok": False, "message": "Unrecognized intent.", "engine": engine}


@app.post("/api/session/confirm-grace")
async def confirm_grace_endpoint(body: ConfirmGraceRequest) -> dict:
    sess = _get_session_or_404(body.session_id)
    if body.action == "confirm":
        result = sess.confirm_bulk_grace()
    elif body.action == "cancel":
        result = sess.cancel_bulk_grace()
    else:
        raise HTTPException(status_code=400, detail="action must be 'confirm' or 'cancel'")
    return result


@app.post("/api/session/manual-edit")
async def manual_edit(body: ManualEditRequest) -> dict:
    sess = _get_session_or_404(body.session_id)
    result = sess.apply_edit(
        roll_no=body.roll_no,
        anchor=body.anchor,
        score=body.score,
        comment=body.comment or "",
    )
    return result


@app.get("/api/session/export-data")
async def export_data(session_id: str = Query(...)) -> dict:
    sess = _get_session_or_404(session_id)
    return sess.export_data()
