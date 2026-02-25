"""Unit tests for workout_import_qa — pure functions only, no network/browser."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from workout_import_qa import (
    STATUS_FETCH_ERROR,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_OK,
    STATUS_PARSE_ERROR,
    STATUS_UNSUPPORTED,
    build_report,
    check_expected,
    classify_api_response,
    extract_fields,
    parse_kimi_response,
    set_has_issues_output,
)


# ---------------------------------------------------------------------------
# classify_api_response
# ---------------------------------------------------------------------------

class TestClassifyApiResponse:
    def test_200_clean(self):
        assert classify_api_response(200, {"needs_clarification": False}) == STATUS_OK

    def test_200_needs_clarification(self):
        assert classify_api_response(200, {"needs_clarification": True}) == STATUS_NEEDS_CLARIFICATION

    def test_400_unsupported_url(self):
        assert classify_api_response(400, {"detail": "Unsupported URL — no adapter registered"}) == STATUS_UNSUPPORTED

    def test_400_no_adapter(self):
        assert classify_api_response(400, {"detail": "No adapter registered for platform: xxx"}) == STATUS_UNSUPPORTED

    def test_400_other(self):
        assert classify_api_response(400, {"detail": "No extractable text found"}) == STATUS_PARSE_ERROR

    def test_422_parse_error(self):
        assert classify_api_response(422, {"detail": "Failed to extract workout"}) == STATUS_PARSE_ERROR

    def test_502_fetch_error(self):
        assert classify_api_response(502, {"detail": "Platform fetch failed"}) == STATUS_FETCH_ERROR


# ---------------------------------------------------------------------------
# extract_fields
# ---------------------------------------------------------------------------

class TestExtractFields:
    def _make_body(self, structure, rounds=None, rest=None, exercises=None, confidence=None):
        block = {"structure": structure}
        if rounds:
            block["rounds"] = rounds
        if rest:
            block["rest_between_seconds"] = rest
        if exercises:
            block["exercises"] = [{"name": ex} for ex in exercises]
        if confidence is not None:
            block["structure_confidence"] = confidence
        return {"blocks": [block], "needs_clarification": confidence is not None and confidence < 0.8}

    def test_basic_fields(self):
        body = self._make_body("circuit", rounds=4, rest=90, exercises=["burpee", "squat"])
        fields = extract_fields(body)
        assert fields["structures"] == ["circuit"]
        assert fields["rounds"] == [4]
        assert fields["rest_between_seconds"] == [90]
        assert fields["exercise_count"] == 2
        assert "burpee" in fields["exercise_names"]

    def test_empty_body(self):
        fields = extract_fields({})
        assert fields["structures"] == []
        assert fields["exercise_count"] == 0
        assert fields["needs_clarification"] is False

    def test_low_confidence_flagged(self):
        body = self._make_body("circuit", confidence=0.5)
        fields = extract_fields(body)
        assert fields["min_confidence"] == 0.5
        assert fields["needs_clarification"] is True

    def test_exercise_names_capped_at_10(self):
        exercises = [f"exercise_{i}" for i in range(20)]
        body = self._make_body("circuit", exercises=exercises)
        fields = extract_fields(body)
        assert len(fields["exercise_names"]) == 10
        assert fields["exercise_count"] == 20


# ---------------------------------------------------------------------------
# check_expected
# ---------------------------------------------------------------------------

class TestCheckExpected:
    def test_matching_structure(self):
        fields = {"structures": ["circuit"], "rounds": [4], "rest_between_seconds": []}
        mismatches = check_expected(fields, {"structure": "circuit"})
        assert mismatches == []

    def test_wrong_structure(self):
        fields = {"structures": ["straight_sets"], "rounds": [], "rest_between_seconds": []}
        mismatches = check_expected(fields, {"structure": "circuit"})
        assert len(mismatches) == 1
        assert "circuit" in mismatches[0]
        assert "straight_sets" in mismatches[0]

    def test_ambiguous_expected_skipped(self):
        # ambiguous and multi_block don't have a single expected structure
        fields = {"structures": ["circuit"], "rounds": [], "rest_between_seconds": []}
        mismatches = check_expected(fields, {"structure": "ambiguous"})
        assert mismatches == []

    def test_no_expected_returns_empty(self):
        fields = {"structures": ["emom"], "rounds": [3], "rest_between_seconds": []}
        assert check_expected(fields, {}) == []

    def test_wrong_rounds(self):
        fields = {"structures": ["circuit"], "rounds": [3], "rest_between_seconds": []}
        mismatches = check_expected(fields, {"structure": "circuit", "rounds": 4})
        assert any("rounds" in m for m in mismatches)


# ---------------------------------------------------------------------------
# parse_kimi_response
# ---------------------------------------------------------------------------

class TestParseKimiResponse:
    def test_ok_status(self):
        result = parse_kimi_response('{"status": "ok", "findings": []}')
        assert result["status"] == "ok"
        assert result["findings"] == []

    def test_issues_found(self):
        result = parse_kimi_response('{"status": "issues_found", "findings": ["EMOM showing as Circuit"]}')
        assert result["status"] == "issues_found"
        assert len(result["findings"]) == 1

    def test_invalid_json(self):
        result = parse_kimi_response("not json at all")
        assert result["status"] == "parse_error"
        assert len(result["findings"]) == 1

    def test_missing_findings_key(self):
        result = parse_kimi_response('{"status": "ok"}')
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

class TestBuildReport:
    def _result(self, status, workout_type="circuit", platform="youtube", mismatches=None, findings=None):
        return {
            "url": f"https://{platform}.com/test",
            "platform": platform,
            "workout_type": workout_type,
            "description": f"Test {workout_type} workout",
            "status": status,
            "fields": {"structures": ["circuit"], "rounds": [4], "rest_between_seconds": [], "exercise_count": 3, "exercise_names": ["a", "b", "c"], "needs_clarification": False, "min_confidence": None},
            "mismatches": mismatches or [],
            "error": None,
            "findings": findings or [],
            "latency_ms": 1234,
        }

    def test_summary_counts(self):
        results = [
            self._result(STATUS_OK),
            self._result(STATUS_NEEDS_CLARIFICATION),
            self._result(STATUS_FETCH_ERROR),
        ]
        report = build_report(results, "2026-02-24 06:00 UTC")
        assert "✅ OK: 1" in report
        assert "Needs clarification: 1" in report
        assert "Failed: 1" in report

    def test_all_ok(self):
        results = [self._result(STATUS_OK)]
        report = build_report(results, "2026-02-24 06:00 UTC")
        assert "✅" in report
        assert "# Workout Import QA" in report
        assert "2026-02-24" in report

    def test_mismatch_appears_in_report(self):
        r = self._result(STATUS_OK, mismatches=["Expected structure='circuit', got ['emom']"])
        report = build_report([r], "2026-02-24 06:00 UTC")
        assert "Expected structure" in report

    def test_parse_error_in_patterns_section(self):
        results = [self._result(STATUS_PARSE_ERROR)]
        report = build_report(results, "2026-02-24 06:00 UTC")
        assert "parse failure" in report

    def test_unsupported_in_patterns_section(self):
        results = [self._result(STATUS_UNSUPPORTED)]
        report = build_report(results, "2026-02-24 06:00 UTC")
        assert "AMA-750" in report

    def test_platform_breakdown(self):
        results = [
            self._result(STATUS_OK, platform="youtube"),
            self._result(STATUS_FETCH_ERROR, platform="instagram"),
        ]
        report = build_report(results, "2026-02-24")
        assert "youtube" in report
        assert "instagram" in report


# ---------------------------------------------------------------------------
# set_has_issues_output
# ---------------------------------------------------------------------------

class TestSetHasIssuesOutput:
    def test_writes_true_when_issues(self, tmp_path):
        env_file = tmp_path / "github_output"
        results = [{"status": STATUS_FETCH_ERROR}]
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(env_file)}):
            set_has_issues_output(results)
        assert "has_issues=true" in env_file.read_text()

    def test_writes_false_when_all_ok(self, tmp_path):
        env_file = tmp_path / "github_output"
        results = [{"status": STATUS_OK}]
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(env_file)}):
            set_has_issues_output(results)
        assert "has_issues=false" in env_file.read_text()

    def test_no_crash_without_github_output(self):
        results = [{"status": STATUS_OK}]
        with patch.dict(os.environ, {}, clear=True):
            set_has_issues_output(results)  # must not raise
