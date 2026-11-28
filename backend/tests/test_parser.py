"""
tests/test_parser.py

25+ unit tests covering:
  - Numeral & fraction lexer (Hindi/Hinglish, special fractions, prefix fractions)
  - Self-correction collapse
  - Intent routing (GRADE, EDIT, UNDO, BULK_GRACE, STATUS, FINISH, IGNORE)
  - Self-talk / no-anchor filter → IGNORE
  - Anchor slicing (written Q-mode, oral rubric-mode)
  - Tone sanitizer
  - Guardrails: score bounds, unknown roll, duplicate-grade
  - Undo stack
  - Bulk-grace flow (queue → confirm / cancel)
  - Bilingual feedback generation
  - Weakness heatmap aggregation
  - Cloud adapter engine detection (key set vs not set)
  - FastAPI endpoint smoke tests
"""
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from app.parser import (
    build_weakness_heatmap,
    collapse_self_corrections,
    extract_number,
    generate_feedback,
    normalize_asr_transcript,
    route_intent,
    sanitize_tone,
    slice_by_anchors,
)
from app.state import (
    GradeSession,
    SessionConfig,
    _extract_tags,
    create_session,
    delete_session,
    get_session,
)
from app.cloud_adapter import get_engine_info
from app.main import app

import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def api_client():
    """Module-scoped sync TestClient using context manager (handles lifespan)."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ===========================================================================
# 1. Numeral Lexer — Hindi basics
# ===========================================================================

class TestNumeralLexer:

    def test_hindi_zero(self):
        assert extract_number("shunya") == 0.0

    def test_hindi_one(self):
        assert extract_number("ek") == 1.0

    def test_hindi_teen(self):
        assert extract_number("teen") == 3.0

    def test_hindi_bees(self):
        assert extract_number("bees") == 20.0

    def test_hindi_pachees(self):
        assert extract_number("pachees") == 25.0

    def test_english_digit(self):
        assert extract_number("7") == 7.0

    def test_decimal_digit(self):
        assert extract_number("8.5") == 8.5

    def test_mixed_phrase(self):
        # "roll 5 Q2 teen" → first valid number found is 5 (digit), but
        # extract_number on "teen" should return 3
        assert extract_number("teen") == 3.0


# ===========================================================================
# 2. Fraction Lexer — Indian fractions
# ===========================================================================

class TestFractionLexer:

    def test_aadha(self):
        assert extract_number("aadha") == 0.5

    def test_dedh(self):
        assert extract_number("dedh") == 1.5

    def test_dhai(self):
        assert extract_number("dhai") == 2.5

    def test_saadhe_teen(self):
        assert extract_number("saadhe teen") == 3.5

    def test_sava_char(self):
        assert extract_number("sava char") == 4.25

    def test_paune_char(self):
        assert extract_number("paune char") == 3.75

    def test_saadhe_paanch(self):
        assert extract_number("saadhe paanch") == 5.5


# ===========================================================================
# 3. Self-Correction Collapse
# ===========================================================================

class TestSelfCorrectionCollapse:

    def test_do_nahi_teen(self):
        """'do nahi teen' → token-level collapse → 3"""
        result = extract_number("do nahi teen")
        assert result == 3.0

    def test_five_sorry_seven(self):
        """'five sorry seven' → 7"""
        result = extract_number("five sorry seven")
        assert result == 7.0

    def test_collapse_tokens_directly(self):
        tokens = ["do", "nahi", "teen"]
        cleaned = collapse_self_corrections(tokens)
        # 'do' dropped, 'nahi' dropped, 'teen' remains
        assert cleaned == ["teen"]

    def test_sorry_collapse(self):
        tokens = ["five", "sorry", "seven"]
        cleaned = collapse_self_corrections(tokens)
        assert cleaned == ["seven"]

    def test_no_correction(self):
        tokens = ["teen"]
        cleaned = collapse_self_corrections(tokens)
        assert cleaned == ["teen"]


# ===========================================================================
# 4. Intent Router
# ===========================================================================

class TestIntentRouter:

    def test_grade_intent_written(self):
        p = route_intent("roll 5 Q3 teen", mode="written")
        assert p.intent == "GRADE"
        assert p.roll_no == 5
        assert p.question == "Q3"
        assert p.score == 3.0

    def test_grade_intent_oral(self):
        p = route_intent("roll 12 Clarity paanch", mode="oral")
        assert p.intent == "GRADE"
        assert p.roll_no == 12
        assert p.question == "Clarity"
        assert p.score == 5.0

    def test_edit_intent(self):
        p = route_intent("edit roll 5 Q3 to 8", mode="written")
        assert p.intent == "EDIT"
        assert p.score == 8.0

    def test_undo_intent(self):
        p = route_intent("undo last", mode="written")
        assert p.intent == "UNDO"

    def test_bulk_grace_intent(self):
        p = route_intent("sabko 2 grace marks dedo", mode="written")
        assert p.intent == "BULK_GRACE"
        assert p.grace_marks == 2.0
        assert p.question is None

    def test_bulk_grace_intent_with_target_question(self):
        p = route_intent("Sabko Q3 mein ek grace mark", mode="written")
        assert p.intent == "BULK_GRACE"
        assert p.question == "Q3"
        assert p.grace_marks == 1.0

    def test_bulk_grace_intent_oral(self):
        p = route_intent("Sabko Clarity mein ek grace mark", mode="oral")
        assert p.intent == "BULK_GRACE"
        assert p.question == "Clarity"
        assert p.grace_marks == 1.0

    def test_status_intent(self):
        p = route_intent("status kitne students graded", mode="written")
        assert p.intent == "STATUS"

    def test_finish_intent(self):
        p = route_intent("finish grading khatam", mode="written")
        assert p.intent == "FINISH"

    def test_confirm_intent(self):
        p = route_intent("confirm haan", mode="written")
        assert p.intent == "CONFIRM"

    def test_cancel_intent(self):
        p = route_intent("cancel nahi", mode="written")
        assert p.intent == "CANCEL"


# ===========================================================================
# 5. Self-Talk / IGNORE Filter
# ===========================================================================

class TestSelfTalkFilter:

    def test_ignore_no_anchor_no_roll(self):
        p = route_intent("Are ye kya diagram banaya hai", mode="written")
        assert p.intent == "IGNORE"

    def test_ignore_chai(self):
        p = route_intent("Ek cup chai dena", mode="written")
        assert p.intent == "IGNORE"

    def test_ignore_no_score_no_id(self):
        p = route_intent("bahut accha likh raha hai", mode="written")
        assert p.intent == "IGNORE"


# ===========================================================================
# 6. Tone Sanitizer
# ===========================================================================

class TestToneSanitizer:

    def test_strips_vent_word(self):
        result = sanitize_tone("are yaar ghatiya diagram")
        assert "yaar" not in result
        assert "are" not in result.lower()
        # 'ghatiya' rewritten
        assert "needs improvement" in result.lower() or "diagram" in result.lower()

    def test_bakwaas_rewrite(self):
        result = sanitize_tone("bakwaas answer diya")
        assert "unclear and incomplete" in result.lower()

    def test_clean_passthrough(self):
        result = sanitize_tone("diagram is missing labels")
        assert "diagram" in result.lower()
        assert "missing labels" in result.lower()

    def test_empty_comment(self):
        result = sanitize_tone("are yaar")
        # After stripping, should be empty or minimal
        assert isinstance(result, str)


# ===========================================================================
# 7. Anchor Slicing
# ===========================================================================

class TestAnchorSlicing:

    def test_written_multi_anchor(self):
        text = "roll 3 Q1 paanch Q2 aath Q3 teen"
        segs = slice_by_anchors(text, mode="written")
        assert len(segs) == 3
        scores = {s["anchor"]: s["score"] for s in segs}
        assert scores["Q1"] == 5.0
        assert scores["Q2"] == 8.0
        assert scores["Q3"] == 3.0

    def test_oral_multi_anchor(self):
        text = "Clarity saat Delivery paanch"
        segs = slice_by_anchors(text, mode="oral")
        assert len(segs) == 2
        scores = {s["anchor"]: s["score"] for s in segs}
        assert scores["Clarity"] == 7.0
        assert scores["Delivery"] == 5.0

    def test_no_anchors_returns_empty(self):
        segs = slice_by_anchors("kuch bhi text hai", mode="written")
        assert segs == []

    def test_roll_propagation_in_slice_by_anchors(self):
        text = "Roll 14: Q1 saadhe saat good structure, Q2 do are ye kya ghatiya diagram banaya hai, Q3 paanch"
        segs = slice_by_anchors(text, mode="written")
        assert len(segs) == 3
        assert all(s.get("roll_no") == 14 for s in segs)
        assert segs[0]["score"] == 7.5
        assert segs[1]["score"] == 2.0
        assert segs[2]["score"] == 5.0
        assert "ghatiya" not in segs[1]["comment"].lower()


# ===========================================================================
# 8. Guardrails — Score Bounds
# ===========================================================================

class TestScoreBounds:

    def _make_session(self, max_marks=10.0):
        config = SessionConfig(
            mode="written",
            questions=["Q1", "Q2"],
            max_marks=max_marks,
            known_rolls={1, 2, 3},
        )
        return GradeSession(config)

    def test_score_above_max_rejected(self):
        sess = self._make_session(max_marks=10.0)
        result = sess.apply_grade(1, "Q1", 11.0)
        assert result["ok"] is False
        assert "voice_error" in result
        assert "10" in result["voice_error"]

    def test_negative_score_rejected(self):
        sess = self._make_session()
        result = sess.apply_grade(1, "Q1", -1.0)
        assert result["ok"] is False

    def test_valid_score_accepted(self):
        sess = self._make_session()
        result = sess.apply_grade(1, "Q1", 7.0)
        assert result["ok"] is True

    def test_score_equal_to_max_accepted(self):
        sess = self._make_session(max_marks=10.0)
        result = sess.apply_grade(1, "Q1", 10.0)
        assert result["ok"] is True


# ===========================================================================
# 9. Guardrails — Unknown Roll Number
# ===========================================================================

class TestUnknownRoll:

    def test_unknown_roll_rejected(self):
        config = SessionConfig(
            mode="written",
            known_rolls={1, 2},
            allow_unknown_rolls=False,
        )
        sess = GradeSession(config)
        result = sess.apply_grade(99, "Q1", 5.0)
        assert result["ok"] is False
        assert "99" in result["voice_error"]

    def test_unknown_roll_allowed_flag(self):
        config = SessionConfig(
            mode="written",
            known_rolls={1, 2},
            allow_unknown_rolls=True,
        )
        sess = GradeSession(config)
        result = sess.apply_grade(99, "Q1", 5.0)
        assert result["ok"] is True


# ===========================================================================
# 10. Guardrails — Duplicate Grade
# ===========================================================================

class TestDuplicateGrade:

    def test_duplicate_without_edit_rejected(self):
        config = SessionConfig(mode="written", known_rolls={1}, allow_unknown_rolls=True)
        sess = GradeSession(config)
        sess.apply_grade(1, "Q1", 5.0)
        result = sess.apply_grade(1, "Q1", 7.0)   # no is_edit
        assert result["ok"] is False
        assert "already" in result["message"]

    def test_duplicate_with_edit_accepted(self):
        config = SessionConfig(mode="written", known_rolls={1}, allow_unknown_rolls=True)
        sess = GradeSession(config)
        sess.apply_grade(1, "Q1", 5.0)
        result = sess.apply_edit(1, "Q1", 7.0)
        assert result["ok"] is True
        assert sess.scores[1]["Q1"].score == 7.0


# ===========================================================================
# 11. Undo Stack
# ===========================================================================

class TestUndoStack:

    def test_undo_reverts_last_grade(self):
        config = SessionConfig(mode="written", allow_unknown_rolls=True)
        sess = GradeSession(config)
        sess.apply_grade(1, "Q1", 8.0)
        sess.apply_undo()
        assert 1 not in sess.scores

    def test_undo_on_empty_stack(self):
        config = SessionConfig(mode="written")
        sess = GradeSession(config)
        result = sess.apply_undo()
        assert result["ok"] is False

    def test_multiple_undos(self):
        config = SessionConfig(mode="written", allow_unknown_rolls=True)
        sess = GradeSession(config)
        sess.apply_grade(1, "Q1", 8.0)
        sess.apply_grade(2, "Q1", 6.0)
        sess.apply_undo()   # reverts roll 2
        sess.apply_undo()   # reverts roll 1
        assert sess.scores == {}


# ===========================================================================
# 12. Bulk Grace Flow
# ===========================================================================

class TestBulkGrace:

    def _populated_session(self):
        config = SessionConfig(mode="written", max_marks=10.0, allow_unknown_rolls=True)
        sess = GradeSession(config)
        sess.apply_grade(1, "Q1", 6.0)
        sess.apply_grade(2, "Q1", 7.0)
        return sess

    def test_grace_queued_before_confirm(self):
        sess = self._populated_session()
        result = sess.queue_bulk_grace(1.0, question="Q1")
        assert result["ok"] is True
        assert result["pending"] is True
        assert sess.pending_grace is not None
        assert sess.pending_grace["question"] == "Q1"

    def test_grace_confirm_applies(self):
        sess = self._populated_session()
        sess.queue_bulk_grace(1.0, question="Q1")
        result = sess.confirm_bulk_grace()
        assert result["ok"] is True
        assert "Grace of 1.0 applied to Q1 for 2 student(s)." in result["message"]
        assert sess.scores[1]["Q1"].score == 7.0
        assert sess.scores[2]["Q1"].score == 8.0

    def test_grace_cancel_no_change(self):
        sess = self._populated_session()
        sess.queue_bulk_grace(2.0, question="Q1")
        sess.cancel_bulk_grace()
        assert sess.scores[1]["Q1"].score == 6.0
        assert sess.pending_grace is None

    def test_grace_capped_at_max(self):
        sess = self._populated_session()
        sess.queue_bulk_grace(5.0, question="Q1")   # 7 + 5 = 12 > 10
        sess.confirm_bulk_grace()
        assert sess.scores[2]["Q1"].score == 10.0  # capped

    def test_grace_no_pending_confirm_fails(self):
        sess = self._populated_session()
        result = sess.confirm_bulk_grace()
        assert result["ok"] is False

    def test_grace_missing_question_rejected(self):
        sess = self._populated_session()
        result = sess.queue_bulk_grace(1.0)
        assert result["ok"] is False
        assert "specify" in result["message"].lower()

    def test_grace_invalid_question_rejected(self):
        config = SessionConfig(mode="written", questions=["Q1", "Q2"], max_marks=10.0, allow_unknown_rolls=True)
        sess = GradeSession(config)
        sess.apply_grade(1, "Q1", 6.0)
        result = sess.queue_bulk_grace(1.0, question="Q5")
        assert result["ok"] is False
        assert "not in the question list" in result["message"]

    def test_grace_initializes_missing_question_for_student(self):
        config = SessionConfig(mode="written", questions=["Q1", "Q2", "Q3"], max_marks=10.0, allow_unknown_rolls=True)
        sess = GradeSession(config)
        sess.apply_grade(12, "Q1", 7.5)
        sess.apply_grade(12, "Q2", 1.0)
        sess.queue_bulk_grace(1.0, question="Q3")
        res = sess.confirm_bulk_grace()
        assert res["ok"] is True
        assert res["message"] == "Grace of 1.0 applied to Q3 for 1 student(s)."
        assert sess.scores[12]["Q1"].score == 7.5
        assert sess.scores[12]["Q2"].score == 1.0
        assert sess.scores[12]["Q3"].score == 1.0
        assert "Grace mark applied" in sess.scores[12]["Q3"].tags


# ===========================================================================
# 13. Bilingual Feedback
# ===========================================================================

class TestBilingualFeedback:

    def test_strong_feedback_english(self):
        fb = generate_feedback({"Q1": 9.0, "Q2": 8.0}, max_marks=10.0, mode="written")
        assert "english" in fb
        assert "hindi" in fb
        assert "solid" in fb["english"].lower() or "consistent" in fb["english"].lower()

    def test_weak_feedback_english(self):
        fb = generate_feedback({"Q1": 2.0, "Q2": 1.0}, max_marks=10.0, mode="written")
        assert "revision" in fb["english"].lower() or "needs" in fb["english"].lower()

    def test_oral_feedback(self):
        fb = generate_feedback({"Clarity": 8.0, "Depth": 7.0}, max_marks=10.0, mode="oral")
        assert "english" in fb

    def test_transliteration_flag(self):
        fb = generate_feedback(
            {"Q1": 8.0}, max_marks=10.0, include_transliteration=True
        )
        assert "transliteration" in fb

    def test_empty_scores(self):
        fb = generate_feedback({}, max_marks=10.0)
        assert "No scores" in fb["english"]


# ===========================================================================
# 14. Weakness Heatmap
# ===========================================================================

class TestWeaknessHeatmap:

    def test_aggregation(self):
        tags = [
            {"anchor": "Q1", "tags": ["needs improvement", "incomplete"]},
            {"anchor": "Q1", "tags": ["needs improvement"]},
            {"anchor": "Q2", "tags": ["off-topic"]},
        ]
        hm = build_weakness_heatmap(tags)
        assert hm["Q1"]["needs improvement"] == 2
        assert hm["Q1"]["incomplete"] == 1
        assert hm["Q2"]["off-topic"] == 1

    def test_empty_input(self):
        assert build_weakness_heatmap([]) == {}


# ===========================================================================
# 15. Cloud Adapter
# ===========================================================================

class TestCloudAdapter:

    def test_no_keys_local_mode(self):
        info = get_engine_info(gemini_key="", openai_key="")
        assert info["engine_mode"] == "local"
        assert info["key_status"] == "key not set"

    def test_gemini_key_set(self):
        info = get_engine_info(gemini_key="AIza_fake_key")
        assert info["engine_mode"] == "gemini"
        assert info["key_status"] == "key set"

    def test_openai_key_set(self):
        info = get_engine_info(openai_key="sk-fake_key")
        assert info["engine_mode"] == "openai"
        assert info["key_status"] == "key set"

    def test_gemini_takes_precedence(self):
        info = get_engine_info(gemini_key="AIza_fake", openai_key="sk-fake")
        assert info["engine_mode"] == "gemini"


# ===========================================================================
# 16. FastAPI Endpoint Tests
# ===========================================================================

class TestAPIEndpoints:

    def _create_session(self, client, mode="written", max_marks=10.0, rolls=None):
        payload = {
            "mode": mode,
            "questions": ["Q1", "Q2", "Q3"] if mode == "written" else [],
            "rubric_items": ["Clarity", "Depth", "Delivery"] if mode == "oral" else [],
            "max_marks": max_marks,
            "known_rolls": rolls or [1, 2, 3, 4, 5],
            "allow_unknown_rolls": False,
        }
        resp = client.post("/api/session/init", json=payload)
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def test_health_endpoint(self, api_client):
        resp = api_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "engine" in data

    def test_health_local_engine(self, api_client):
        resp = api_client.get("/api/health")
        data = resp.json()
        assert data["engine"]["engine_mode"] == "local"

    def test_session_init(self, api_client):
        sid = self._create_session(api_client)
        assert sid  # non-empty string

    def test_voice_command_grade(self, api_client):
        sid = self._create_session(api_client, rolls=[5, 6, 7])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 5 Q1 paanch",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "grade"
        # May be multi-slice or single — either way first result must be ok
        if data.get("multi"):
            assert data["results"][0]["ok"] is True
        else:
            assert data["ok"] is True

    def test_voice_command_ignore(self, api_client):
        sid = self._create_session(api_client)
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Are ye kya diagram banaya hai",
        })
        assert resp.status_code == 200
        assert resp.json()["intent"] == "ignore"

    def test_voice_command_undo(self, api_client):
        sid = self._create_session(api_client, rolls=[1])
        api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 1 Q1 ek",
        })
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "undo",
        })
        assert resp.json()["intent"] == "undo"
        assert resp.json()["ok"] is True

    def test_voice_command_status(self, api_client):
        sid = self._create_session(api_client)
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "status",
        })
        assert resp.json()["intent"] == "status"
        assert "status" in resp.json()

    def test_voice_command_finish(self, api_client):
        sid = self._create_session(api_client)
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "finish khatam",
        })
        assert resp.json()["intent"] == "finish"
        assert resp.json()["ok"] is True

    def test_voice_command_bulk_grace_flow(self, api_client):
        sid = self._create_session(api_client, rolls=[1, 2])
        # Grade first
        api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 1 Q1 ek",
        })
        # Queue grace with target question
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "sabko Q1 mein 1 grace marks dedo",
        })
        assert resp.json()["intent"] == "bulk_grace"
        assert resp.json()["ok"] is True
        # Confirm
        resp2 = api_client.post("/api/session/confirm-grace", json={
            "session_id": sid,
            "action": "confirm",
        })
        assert resp2.json()["ok"] is True

    def test_voice_command_bulk_grace_without_question_rejected(self, api_client):
        sid = self._create_session(api_client, rolls=[1, 2])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "sabko 1 grace marks dedo",
        })
        data = resp.json()
        assert data["intent"] == "bulk_grace"
        assert data["ok"] is False
        assert "specify" in data["message"].lower()
        assert "voice_error" in data

    def test_manual_edit_endpoint(self, api_client):
        sid = self._create_session(api_client, rolls=[3])
        # Seed a grade first via voice
        api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 3 Q2 teen",
        })
        resp = api_client.post("/api/session/manual-edit", json={
            "session_id": sid,
            "roll_no": 3,
            "anchor": "Q2",
            "score": 9.0,
            "comment": "Corrected via manual edit",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_export_data_endpoint(self, api_client):
        sid = self._create_session(api_client, rolls=[1, 2])
        api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 1 Q1 paanch",
        })
        resp = api_client.get(f"/api/session/export-data?session_id={sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "scores" in data
        assert "student_summaries" in data
        assert "weakness_heatmap" in data

    def test_session_not_found_404(self, api_client):
        resp = api_client.get("/api/session/export-data?session_id=nonexistent-id")
        assert resp.status_code == 404

    def test_score_out_of_bounds_via_voice(self, api_client):
        sid = self._create_session(api_client, rolls=[1])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 1 Q1 bees",   # 20 > max 10
        })
        data = resp.json()
        # May be multi-slice (results list) or single response
        if data.get("multi"):
            # At least one result must be a rejection
            assert any(r.get("ok") is False for r in data["results"])
        else:
            assert data.get("ok") is False or data.get("voice_error") is not None

    def test_voice_command_multi_slice_propagation_and_sanitization(self, api_client):
        """
        Verify sending 'Roll 14: Q1 saadhe saat good structure, Q2 do are ye kya ghatiya diagram banaya hai, Q3 paanch'
        to /api/voice/command saves all three questions under roll_no: 14, computes total to 14.5,
        and sanitizes Q2's venting into a constructive tag.
        """
        sid = self._create_session(api_client, rolls=[14])
        transcript = (
            "Roll 14: Q1 saadhe saat good structure, "
            "Q2 do are ye kya ghatiya diagram banaya hai, "
            "Q3 paanch"
        )
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": transcript,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "grade"
        assert data.get("multi") is True
        assert data.get("roll_no") == 14
        assert data.get("total") == 14.5

        # Verify all 3 slices in results
        results = data["results"]
        assert len(results) == 3

        # Q1: 7.5
        assert results[0]["anchor"] == "Q1"
        assert results[0]["roll_no"] == 14
        assert results[0]["entry"]["score"] == 7.5
        assert results[0]["entry"]["roll_no"] == 14

        # Q2: 2.0 and venting sanitized
        assert results[1]["anchor"] == "Q2"
        assert results[1]["roll_no"] == 14
        assert results[1]["entry"]["score"] == 2.0
        assert results[1]["entry"]["roll_no"] == 14
        # Rude vent words stripped/rewritten
        assert "ghatiya" not in results[1]["entry"]["comment"].lower()
        assert "ghatiya" not in str(results[1]["entry"]["tags"]).lower()
        # Sanitized into constructive tag(s)
        constructive_tags = {"needs improvement", "diagram unclear"}
        assert any(t in constructive_tags for t in results[1]["entry"]["tags"])

        # Q3: 5.0
        assert results[2]["anchor"] == "Q3"
        assert results[2]["roll_no"] == 14
        assert results[2]["entry"]["score"] == 5.0
        assert results[2]["entry"]["roll_no"] == 14

        # Verify backend session state directly
        sess = get_session(sid)
        assert sess is not None
        assert 14 in sess.scores
        student_scores = sess.scores[14]
        assert len(student_scores) == 3
        assert student_scores["Q1"].score == 7.5
        assert student_scores["Q2"].score == 2.0
        assert student_scores["Q3"].score == 5.0
        assert sum(e.score for e in student_scores.values()) == 14.5
        for anchor, entry in student_scores.items():
            assert entry.roll_no == 14

    def test_hindi_spelling_variants_and_baarah_out_of_bounds(self, api_client):
        """
        Regression test:
        - 'baarah', 'bara', 'gyaarah', 'teerah', 'attharah', 'unees', 'bis', 'ath' parse cleanly.
        - 'Roll 15 Q1 baarah' parses score 12.0, triggers out-of-bounds (12 > 10),
          and returns voice_error (never ignore).
        """
        assert extract_number("baarah") == 12.0
        assert extract_number("bara") == 12.0
        assert extract_number("gyaarah") == 11.0
        assert extract_number("teerah") == 13.0
        assert extract_number("attharah") == 18.0
        assert extract_number("unees") == 19.0
        assert extract_number("bis") == 20.0
        assert extract_number("ath") == 8.0

        sid = self._create_session(api_client, rolls=[15])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Roll 15 Q1 baarah",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "grade"
        assert data["intent"] != "ignore"
        if data.get("multi"):
            assert data["results"][0]["ok"] is False
            assert data["results"][0].get("voice_error")
            assert "12" in data["results"][0]["voice_error"]
        else:
            assert data.get("ok") is False
            assert data.get("voice_error")

    def test_kar_do_edit_recalculates_full_student_total(self, api_client):
        """
        Regression test:
        - 'Roll 14 Q2 ko chaar kar do' must NOT mistake 'do' in 'kar do' for 2.
        - Must route as EDIT, set Q2=4.0, and return recalculated student total (16.5).
        """
        sid = self._create_session(api_client, rolls=[14])
        # Seed Roll 14 with Q1=7.5, Q2=2.0, Q3=5.0 -> Total 14.5
        r1 = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Roll 14: Q1 saadhe saat good structure, Q2 do are ye kya ghatiya diagram banaya hai, Q3 paanch",
        })
        assert r1.status_code == 200
        assert r1.json()["total"] == 14.5

        # Now edit Q2 to 4 using 'kar do'
        r2 = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Roll 14 Q2 ko chaar kar do",
        })
        assert r2.status_code == 200
        data = r2.json()
        assert data["intent"] == "edit"
        assert data["roll_no"] == 14
        assert data["total"] == 16.5
        assert data["results"][0]["ok"] is True
        assert data["results"][0]["entry"]["score"] == 4.0

    def test_clean_comment_strips_spoken_numerals(self, api_client):
        """
        Regression test:
        Spoken Hindi numeral/fraction tokens ('saadhe saat', 'do', 'paanch')
        must be stripped from saved feedback comments.
        """
        sid = self._create_session(api_client, rolls=[14])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": (
                "Roll 14: Q1 saadhe saat good structure, "
                "Q2 do are ye kya ghatiya diagram banaya hai, "
                "Q3 paanch"
            ),
        })
        assert resp.status_code == 200
        results = resp.json()["results"]
        q1_comment = results[0]["entry"]["comment"]
        q2_comment = results[1]["entry"]["comment"]
        q3_comment = results[2]["entry"]["comment"]

        assert q1_comment == "Good structure"
        assert "saadhe" not in q1_comment.lower()
        assert "saat" not in q1_comment.lower()

        assert not q2_comment.lower().startswith("do ")
        assert " do " not in f" {q2_comment.lower()} "
        assert "needs improvement" in q2_comment.lower()

        assert q3_comment == ""

    def test_bulk_grace_scoped_to_target_question_regression(self, api_client):
        """
        Regression test:
        - Grade Roll 12 (Q1=7.5, Q2=1.0), Roll 13 (Q1=7.5, Q2=3.0, Q3=5.0), Roll 14 (Q1=7.5, Q2=4.0, Q3=5.0).
        - Run 'Sabko Q3 mein ek grace mark' + confirm.
        - Assert Q1 and Q2 remain completely unchanged (7.5, 1.0/3.0/4.0) for all 3 students,
          while Q3 becomes 1.0, 6.0, and 6.0 respectively.
        """
        sid = self._create_session(api_client, rolls=[12, 13, 14])

        # Grade Roll 12: Q1=7.5, Q2=1.0
        r12 = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Roll 12: Q1 saadhe saat, Q2 ek",
        })
        assert r12.status_code == 200

        # Grade Roll 13: Q1=7.5, Q2=3.0, Q3=5.0
        r13 = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Roll 13: Q1 saadhe saat, Q2 teen, Q3 paanch",
        })
        assert r13.status_code == 200

        # Grade Roll 14: Q1=7.5, Q2=4.0, Q3=5.0
        r14 = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Roll 14: Q1 saadhe saat, Q2 chaar, Q3 paanch",
        })
        assert r14.status_code == 200

        # Run "Sabko Q3 mein ek grace mark"
        resp_grace = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "Sabko Q3 mein ek grace mark",
        })
        assert resp_grace.status_code == 200
        grace_data = resp_grace.json()
        assert grace_data["intent"] == "bulk_grace"
        assert grace_data["ok"] is True
        assert grace_data["pending"] is True
        assert grace_data["message"] == (
            "About to add 1.0 grace mark(s) to Q3 for all 3 graded student(s) (capped at max 10). "
            "Say 'confirm' to apply or 'cancel' to abort."
        )

        # Confirm grace
        resp_confirm = api_client.post("/api/session/confirm-grace", json={
            "session_id": sid,
            "action": "confirm",
        })
        assert resp_confirm.status_code == 200
        confirm_data = resp_confirm.json()
        assert confirm_data["ok"] is True
        assert confirm_data["message"] == "Grace of 1.0 applied to Q3 for 3 student(s)."

        # Verify state in backend directly
        sess = get_session(sid)
        assert sess is not None

        # Roll 12: Q1=7.5, Q2=1.0, Q3=1.0 (initialized)
        assert sess.scores[12]["Q1"].score == 7.5
        assert sess.scores[12]["Q2"].score == 1.0
        assert sess.scores[12]["Q3"].score == 1.0
        assert "Grace mark applied" in sess.scores[12]["Q3"].tags

        # Roll 13: Q1=7.5, Q2=3.0, Q3=6.0 (5.0 + 1.0)
        assert sess.scores[13]["Q1"].score == 7.5
        assert sess.scores[13]["Q2"].score == 3.0
        assert sess.scores[13]["Q3"].score == 6.0

        # Roll 14: Q1=7.5, Q2=4.0, Q3=6.0 (5.0 + 1.0)
        assert sess.scores[14]["Q1"].score == 7.5
        assert sess.scores[14]["Q2"].score == 4.0
        assert sess.scores[14]["Q3"].score == 6.0


# ===========================================================================
# 15. Real-World Chrome Web Speech API (en-IN / hi-IN) ASR Regression Tests
# ===========================================================================

class TestRealWorldASRNormalization:

    def _create_session(self, api_client, rolls=None):
        resp = api_client.post("/api/session/init", json={
            "mode": "written",
            "questions": ["Q1", "Q2", "Q3", "Q4"],
            "max_marks": 10.0,
            "known_rolls": rolls or [12, 14, 15],
        })
        assert resp.status_code == 200
        return resp.json()["session_id"]

    @pytest.mark.parametrize(
        "transcript,expected_roll,expected_q,expected_score",
        [
            ("रोल 12 Q4 7", 12, "Q4", 7.0),
            ("रोल 12 के 4 Q4 नो", 12, "Q4", 9.0),
            ("ट्रोल 12 Q4 7", 12, "Q4", 7.0),
            ("रोल 12 Q3 4:45", 12, "Q3", 4.75),
            ("roll 12 Q3 7:30", 12, "Q3", 7.5),
            ("रोल 12 के 3 7:30", 12, "Q3", 7.5),
            ("rolled 12 question 2 5", 12, "Q2", 5.0),
            ("रोल १२ क्यू ४ साढ़े सात", 12, "Q4", 7.5),
            ("role 12 Q1 4:15", 12, "Q1", 4.25),
            ("royal 12 Q1 5:00", 12, "Q1", 5.0),
        ],
    )
    def test_real_asr_grade_utterances(
        self, api_client, transcript, expected_roll, expected_q, expected_score
    ):
        sid = self._create_session(api_client, rolls=[expected_roll])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": transcript,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "grade"
        assert data["roll_no"] == expected_roll
        if data.get("multi"):
            assert data["results"][0]["ok"] is True
            assert data["results"][0]["entry"]["anchor"] == expected_q
            assert data["results"][0]["entry"]["score"] == expected_score
        else:
            assert data["ok"] is True
            assert data["entry"]["anchor"] == expected_q
            assert data["entry"]["score"] == expected_score

    def test_out_of_schema_question_returns_explicit_voice_error(self, api_client):
        sid = self._create_session(api_client, rolls=[12])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 12 Q7 5",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Q7 is not in this exam" in data["voice_error"]
        assert "Q1, Q2, Q3, Q4" in data["voice_error"]

    @pytest.mark.parametrize("transcript", ["रोल 12 Q4", "रोल नंबर 12"])
    def test_incomplete_roll_command_returns_helpful_prompt(self, api_client, transcript):
        sid = self._create_session(api_client, rolls=[12])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": transcript,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] != "ignore"
        assert data["ok"] is False
        assert "Heard Roll 12" in data["voice_error"]

    def test_devanagari_commands_and_self_talk_preserved(self):
        assert route_intent("रोल 12 Q4 7 कर दो").intent == "EDIT"
        assert route_intent("सबको Q3 में एक ग्रेस").intent == "BULK_GRACE"
        assert route_intent("कितने बाकी").intent == "STATUS"
        assert route_intent("कौनसे बाकी").intent == "STATUS"
        assert route_intent("अनडू").intent == "UNDO"
        assert route_intent("वापस").intent == "UNDO"
        assert route_intent("कन्फर्म").intent == "CONFIRM"
        assert route_intent("कैंसल").intent == "CANCEL"
        assert "candidate" in normalize_asr_transcript("कैंडिडेट 12")
        assert route_intent("Are ye kya diagram banaya hai").intent == "IGNORE"
        assert route_intent("Ek cup chai dena").intent == "IGNORE"


# ===========================================================================
# 16. Oral Rubric Case-Insensitivity, Homophones, Glued-Digit Rescue & Schema Rejection
# ===========================================================================

class TestRealWorldVoiceGradingRegressions:

    def _create_written_session(self, api_client, rolls=None):
        resp = api_client.post("/api/session/init", json={
            "mode": "written",
            "questions": ["Q1", "Q2", "Q3", "Q4"],
            "max_marks": 10.0,
            "known_rolls": rolls or [14, 15, 18],
        })
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def _create_oral_session(self, api_client, rolls=None):
        resp = api_client.post("/api/session/init", json={
            "mode": "oral",
            "rubric_items": ["Clarity", "Depth", "Ethics", "Composure"],
            "max_marks": 10.0,
            "known_rolls": rolls or [101, 102, 103],
        })
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def test_oral_lowercase_rubric_canonicalized(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[101])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 101 clarity 5",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["roll_no"] == 101
        assert data["total"] == 5.0
        entry = data["results"][0]["entry"] if data.get("multi") else data["entry"]
        assert entry["anchor"] == "Clarity"
        assert entry["score"] == 5.0

    def test_oral_multi_rubric_case_insensitive_panch_and_homophone(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[103])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 103 clarity aath depth Panch ethics 7:30 composer nau",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["multi"] is True
        assert data["roll_no"] == 103
        assert data["total"] == 29.5
        by_anchor = {r["entry"]["anchor"]: r["entry"]["score"] for r in data["results"]}
        assert by_anchor == {
            "Clarity": 8.0,
            "Depth": 5.0,
            "Ethics": 7.5,
            "Composure": 9.0,
        }

    def test_mixed_hinglish_fraction_with_ascii_digits(self):
        assert extract_number("saadhe 9") == 9.5
        assert extract_number("saadhe 7") == 7.5
        assert extract_number("sava 4") == 4.25
        assert extract_number("paune 5") == 4.75
        assert extract_number("saade 9") == 9.5
        assert extract_number("sade 7") == 7.5
        assert extract_number("sadhe 8") == 8.5
        assert extract_number("saadhey 6") == 6.5
        assert extract_number("saare 5") == 5.5
        assert extract_number("pone 5") == 4.75
        assert extract_number("pawne 4") == 3.75

    def test_glued_digit_rescue_q39(self, api_client):
        sid = self._create_written_session(api_client, rolls=[18])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 18 question 39",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        entry = data["results"][0]["entry"] if data.get("multi") else data["entry"]
        assert entry["anchor"] == "Q3"
        assert entry["score"] == 9.0

    def test_mixed_saadhe_9_and_glued_q39_30(self, api_client):
        sid1 = self._create_written_session(api_client, rolls=[18])
        r1 = api_client.post("/api/voice/command", json={
            "session_id": sid1,
            "transcript": "roll 18 question 3 saadhe 9",
        })
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["ok"] is True
        e1 = d1["results"][0]["entry"] if d1.get("multi") else d1["entry"]
        assert e1["anchor"] == "Q3"
        assert e1["score"] == 9.5

        sid2 = self._create_written_session(api_client, rolls=[18])
        r2 = api_client.post("/api/voice/command", json={
            "session_id": sid2,
            "transcript": "roll 18 question 39:30",
        })
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["ok"] is True
        e2 = d2["results"][0]["entry"] if d2.get("multi") else d2["entry"]
        assert e2["anchor"] == "Q3"
        assert e2["score"] == 9.5

    def test_out_of_schema_q69_not_split(self, api_client):
        sid = self._create_written_session(api_client, rolls=[15])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 15 question 69",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Q69 is not in this exam" in data["voice_error"]
        assert "Q1, Q2, Q3, Q4" in data["voice_error"]

    def test_out_of_schema_q5_7_30_rejected_never_total_0(self, api_client):
        sid = self._create_written_session(api_client, rolls=[14])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "roll 14 question 5 7:30",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Q5 is not in this exam" in data["voice_error"]
        assert "Q1, Q2, Q3, Q4" in data["voice_error"]
        assert "total" not in data or data.get("multi") is not True


# ===========================================================================
# 17. Devanagari Oral Rubric Transliterations, Homophones & Partial Multi-Slice
# ===========================================================================

class TestDevanagariOralRubricAndPartialSlice:

    def _create_oral_session(self, api_client, rolls=None):
        resp = api_client.post("/api/session/init", json={
            "mode": "oral",
            "rubric_items": ["Clarity", "Depth", "Ethics", "Composure"],
            "max_marks": 10.0,
            "known_rolls": rolls or [103, 105, 107, 108],
        })
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def test_devanagari_oral_rubric_transliterations(self):
        assert normalize_asr_transcript("क्लेरिटी 8") == "Clarity 8"
        assert normalize_asr_transcript("क्लैरिटी 8") == "Clarity 8"
        assert normalize_asr_transcript("क्लैरीटी 8") == "Clarity 8"
        assert normalize_asr_transcript("क्लेअरिटी 8") == "Clarity 8"
        assert normalize_asr_transcript("डेप्थ 6") == "Depth 6"
        assert normalize_asr_transcript("डेफ्थ 6") == "Depth 6"
        assert normalize_asr_transcript("देप्थ 6") == "Depth 6"
        assert normalize_asr_transcript("डेप्ट 6") == "Depth 6"
        assert normalize_asr_transcript("एथिक्स 7") == "Ethics 7"
        assert normalize_asr_transcript("ऐथिक्स 7") == "Ethics 7"
        assert normalize_asr_transcript("इथिक्स 7") == "Ethics 7"
        assert normalize_asr_transcript("एथिक 7") == "Ethics 7"
        assert normalize_asr_transcript("कंपोजर 9") == "Composure 9"
        assert normalize_asr_transcript("कम्पोजर 9") == "Composure 9"
        assert normalize_asr_transcript("कंपोज़र 9") == "Composure 9"
        assert normalize_asr_transcript("कंपोसर 9") == "Composure 9"
        assert normalize_asr_transcript("कंपोजचर 9") == "Composure 9"
        assert normalize_asr_transcript("कंपोज़र 9") == "Composure 9"
        assert normalize_asr_transcript("प्रेजेंटेशन 8") == "Presentation 8"
        assert normalize_asr_transcript("कंटेंट 7") == "Content 7"
        assert normalize_asr_transcript("कम्युनिकेशन 8") == "Communication 8"
        assert normalize_asr_transcript("कॉन्फिडेंस 9") == "Confidence 9"

    def test_anchor_scoped_devanagari_homophones_and_self_talk_safety(self):
        assert normalize_asr_transcript("क्लेरिटी आर्ट") == "Clarity 8"
        assert normalize_asr_transcript("कंपोजर ना") == "Composure 9"
        assert normalize_asr_transcript("साढ़े आर्ट") == "saadhe 8"
        # Standalone self-talk must never become a score or grade
        assert normalize_asr_transcript("आर्ट का पेपर") == "आर्ट का पेपर"
        assert route_intent("आर्ट का पेपर अच्छा था", mode="oral").intent == "IGNORE"
        assert route_intent("चाय देना ना", mode="oral").intent == "IGNORE"
        # Self-corrections with nahi remain intact
        parsed = route_intent("रोल 103 क्लेरिटी 7 nahi 8", mode="oral", rubric_items=["Clarity"])
        assert parsed.intent == "GRADE"
        assert parsed.score == 8.0

    def test_log_line_roll_107_composure_9_5(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[107])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "रोल 107 कंपोजर 9.5",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["roll_no"] == 107
        assert data["total"] == 9.5
        entry = data["results"][0]["entry"] if data.get("multi") else data["entry"]
        assert entry["anchor"] == "Composure"
        assert entry["score"] == 9.5

    def test_log_line_roll_108_composure_7_30_depth_6(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[108])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "रोल 108 कंपोजर 7:30 रिटर्न जो डेप्थ 6",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["multi"] is True
        assert data["roll_no"] == 108
        assert data["total"] == 13.5
        by_anchor = {r["entry"]["anchor"]: r["entry"]["score"] for r in data["results"]}
        assert by_anchor == {"Composure": 7.5, "Depth": 6.0}

    def test_log_line_roll_103_all_four_rubrics_with_homophones(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[103])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "रोल 103 क्लेरिटी आर्ट डेप्थ 5 एथिक्स 7:30 कंपोजर ना",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["multi"] is True
        assert data["roll_no"] == 103
        assert data["total"] == 29.5
        by_anchor = {r["entry"]["anchor"]: r["entry"]["score"] for r in data["results"]}
        assert by_anchor == {
            "Clarity": 8.0,
            "Depth": 5.0,
            "Ethics": 7.5,
            "Composure": 9.0,
        }

    def test_log_line_roll_105_partial_multi_slice_resilience(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[105])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "रोल 105 डेप्थ 7:30 क्लेरिटी",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["multi"] is True
        assert data["roll_no"] == 105
        assert data["total"] == 7.5
        assert len(data["results"]) == 1
        assert data["results"][0]["entry"]["anchor"] == "Depth"
        assert data["results"][0]["entry"]["score"] == 7.5
        assert "Clarity" in data.get("warning", "")
        assert "Clarity" in data.get("skipped_anchors", [])


# ===========================================================================
# 18. Grounded Bilingual Feedback, Devanagari Sanitizer & Missing ASR Variants
# ===========================================================================

class TestGroundedFeedbackAndDevanagariSanitizer:

    def _create_oral_session(self, api_client, rolls=None):
        resp = api_client.post("/api/session/init", json={
            "mode": "oral",
            "rubric_items": ["Clarity", "Depth", "Ethics", "Composure"],
            "max_marks": 10.0,
            "known_rolls": rolls or [103, 104, 106, 108],
        })
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def test_sava_devanagari_variants_and_deth(self):
        assert normalize_asr_transcript("डेथ 0") == "Depth 0"
        assert extract_number("सावा 6") == 6.25
        assert extract_number("सावा से 6") == 6.25

    def test_roll_106_deth_zero_and_half(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[106])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "रोल 106 क्लेरिटी 0 डेथ 0 एथिक्स 1 कंपोजर आधा",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["multi"] is True
        assert data["roll_no"] == 106
        assert data["total"] == 1.5
        by_anchor = {r["entry"]["anchor"]: r["entry"]["score"] for r in data["results"]}
        assert by_anchor == {
            "Clarity": 0.0,
            "Depth": 0.0,
            "Ethics": 1.0,
            "Composure": 0.5,
        }

    def test_roll_108_devanagari_sanitizer_and_ungraded_depth_omitted(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[108])
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": (
                "रोल 108 क्लेरिटी 9:30 पर यह क्या बोल रहा है दिमाग खराब कर रहा है "
                "ठीक से बोलते नहीं आता करंट अफेयर्स पर काम कर करंट अफेयर्स में बहुत "
                "इंप्रूवमेंट की जरूरत एथिक्स 9 कंपोजर 7:30"
            ),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["multi"] is True
        by_anchor = {r["entry"]["anchor"]: r["entry"] for r in data["results"]}
        assert set(by_anchor.keys()) == {"Clarity", "Ethics", "Composure"}
        clarity_comment = by_anchor["Clarity"]["comment"]
        assert "दिमाग खराब" not in clarity_comment
        assert "यह क्या बोल रहा है" not in clarity_comment
        assert "current affairs" in clarity_comment.lower()
        assert "speaking fluency" in clarity_comment.lower()

        export_resp = api_client.get(f"/api/session/export-data?session_id={sid}")
        assert export_resp.status_code == 200
        summaries = {s["roll_no"]: s["feedback"] for s in export_resp.json()["student_summaries"]}
        fb = summaries[108]
        assert "Depth" not in fb["english"]
        assert "Depth" not in fb["hindi"]
        assert "Clarity (9.5/10)" in fb["english"]
        assert "Ethics (9/10)" in fb["english"]
        assert "Current Affairs" in fb["english"]
        assert "speaking fluency" in fb["english"]
        assert "करंट अफेयर्स" in fb["hindi"]
        assert "बोलने के प्रवाह" in fb["hindi"]

    def test_roll_103_vs_104_distinct_grounded_feedback(self, api_client):
        sid = self._create_oral_session(api_client, rolls=[103, 104])
        r103 = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "रोल 103 क्लेरिटी 8 डेप्थ 5 एथिक्स 7:30 कंपोजर 9",
        })
        assert r103.status_code == 200 and r103.json()["ok"] is True

        r104 = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "रोल 104 क्लेरिटी 5 एथिक्स 6.75",
        })
        assert r104.status_code == 200 and r104.json()["ok"] is True

        export_resp = api_client.get(f"/api/session/export-data?session_id={sid}")
        assert export_resp.status_code == 200
        summaries = {s["roll_no"]: s["feedback"] for s in export_resp.json()["student_summaries"]}
        fb103 = summaries[103]
        fb104 = summaries[104]

        assert fb103["english"] != fb104["english"]
        assert fb103["hindi"] != fb104["hindi"]
        assert "Composure (9/10)" in fb103["english"]
        assert "Clarity (8/10)" in fb103["english"]
        assert "Depth (5/10)" in fb103["english"]
        assert "Depth" not in fb104["english"]
        assert "Clarity (5/10)" in fb104["english"]
        assert "Ethics (6.75/10)" in fb104["english"]

    def test_written_mode_grounded_feedback_and_devanagari_noise_strip(self):
        cleaned = sanitize_tone(
            "अरे यार दिमाग खराब कर रहा है डिटॉल भी क्या आ गया है क्या बकवास घटिया फालतू बेकार कॉन्सेप्ट कमजोर है"
        )
        assert "दिमाग खराब" not in cleaned
        assert "डिटॉल" not in cleaned
        assert "बकवास" not in cleaned
        assert "conceptual clarity" in cleaned.lower()

        fb = generate_feedback(
            {"Q1": 9.0, "Q2": 4.0},
            max_marks=10.0,
            mode="written",
            comments={"Q2": "फॉर्मूला गलत है"},
        )
        assert "Q1 (9/10)" in fb["english"]
        assert "Q2 (4/10)" in fb["english"]
        assert "formulas and calculations" in fb["english"]
        assert "सूत्रों और गणना" in fb["hindi"]
