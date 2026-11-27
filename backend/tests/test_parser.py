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
        result = sess.queue_bulk_grace(1.0)
        assert result["ok"] is True
        assert result["pending"] is True
        assert sess.pending_grace is not None

    def test_grace_confirm_applies(self):
        sess = self._populated_session()
        sess.queue_bulk_grace(1.0)
        result = sess.confirm_bulk_grace()
        assert result["ok"] is True
        assert sess.scores[1]["Q1"].score == 7.0
        assert sess.scores[2]["Q1"].score == 8.0

    def test_grace_cancel_no_change(self):
        sess = self._populated_session()
        sess.queue_bulk_grace(2.0)
        sess.cancel_bulk_grace()
        assert sess.scores[1]["Q1"].score == 6.0
        assert sess.pending_grace is None

    def test_grace_capped_at_max(self):
        sess = self._populated_session()
        sess.queue_bulk_grace(5.0)   # 7 + 5 = 12 > 10
        sess.confirm_bulk_grace()
        assert sess.scores[2]["Q1"].score == 10.0  # capped

    def test_grace_no_pending_confirm_fails(self):
        sess = self._populated_session()
        result = sess.confirm_bulk_grace()
        assert result["ok"] is False


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
        # Queue grace
        resp = api_client.post("/api/voice/command", json={
            "session_id": sid,
            "transcript": "sabko 1 grace marks dedo",
        })
        assert resp.json()["intent"] == "bulk_grace"
        # Confirm
        resp2 = api_client.post("/api/session/confirm-grace", json={
            "session_id": sid,
            "action": "confirm",
        })
        assert resp2.json()["ok"] is True

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
