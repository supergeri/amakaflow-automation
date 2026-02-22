"""Unit tests for workout import QA pure functions."""
import json
import os
import pytest
from unittest.mock import patch, mock_open

# Import the functions we'll test
import sys
sys.path.insert(0, os.path.dirname(__file__))


class TestParseKimiResponse:
    """Tests for parse_kimi_response function."""
    
    def test_valid_json_returns_dict(self):
        """Valid JSON with status and findings returns correct dict."""
        from workout_import_qa import parse_kimi_response
        
        raw = '{"status": "ok", "findings": []}'
        result = parse_kimi_response(raw)
        
        assert result == {"status": "ok", "findings": []}
    
    def test_valid_json_with_findings(self):
        """Valid JSON with findings returns them correctly."""
        from workout_import_qa import parse_kimi_response
        
        raw = '{"status": "issues_found", "findings": ["Finding 1", "Finding 2"]}'
        result = parse_kimi_response(raw)
        
        assert result == {"status": "issues_found", "findings": ["Finding 1", "Finding 2"]}
    
    def test_invalid_json_returns_parse_error(self):
        """Invalid JSON returns parse_error status."""
        from workout_import_qa import parse_kimi_response
        
        raw = 'not valid json at all'
        result = parse_kimi_response(raw)
        
        assert result["status"] == "parse_error"
        assert result["findings"] == []
    
    def test_missing_findings_key_returns_empty_list(self):
        """Missing findings key returns empty list."""
        from workout_import_qa import parse_kimi_response
        
        raw = '{"status": "ok"}'
        result = parse_kimi_response(raw)
        
        assert result["status"] == "ok"
        assert result["findings"] == []


class TestBuildReport:
    """Tests for build_report function."""
    
    def test_summary_counts_correct(self):
        """Summary table has correct counts."""
        from workout_import_qa import build_report
        
        results = [
            {"url": "url1", "status": "ok", "findings": []},
            {"url": "url2", "status": "issues_found", "findings": ["Bad thing"]},
            {"url": "url3", "status": "error", "error": "timeout"},
        ]
        
        report = build_report(results, "2026-02-22")
        
        # Check table format
        assert "| 3 | 1 | 1 | 1 |" in report  # Total | OK | Issues | Failed
        assert "## Summary" in report
    
    def test_findings_appear_in_output(self):
        """Findings from results appear in the report."""
        from workout_import_qa import build_report
        
        results = [
            {
                "url": "https://example.com/workout1",
                "status": "issues_found",
                "findings": ["EMOM shown as Circuit", "Wrong exercise name"]
            },
        ]
        
        report = build_report(results, "2026-02-22")
        
        assert "EMOM shown as Circuit" in report
        assert "Wrong exercise name" in report
    
    def test_failed_imports_shown(self):
        """Failed imports show error info."""
        from workout_import_qa import build_report
        
        results = [
            {
                "url": "https://example.com/fail",
                "status": "error",
                "error": "Network timeout"
            },
        ]
        
        report = build_report(results, "2026-02-22")
        
        assert "Failed" in report
        assert "Network timeout" in report


class TestSetHasIssuesOutput:
    """Tests for set_has_issues_output function."""
    
    @patch.dict(os.environ, {"GITHUB_OUTPUT": "/tmp/test_output"})
    def test_writes_true_when_issues_found(self):
        """Writes has_issues=true when any result has non-ok status."""
        from workout_import_qa import set_has_issues_output
        
        results = [
            {"status": "ok"},
            {"status": "issues_found"},
        ]
        
        m = mock_open()
        with patch("builtins.open", m):
            set_has_issues_output(results)
        
        m().write.assert_called_with("has_issues=true\n")
    
    @patch.dict(os.environ, {"GITHUB_OUTPUT": "/tmp/test_output"})
    def test_writes_false_when_all_ok(self):
        """Writes has_issues=false when all results are ok."""
        from workout_import_qa import set_has_issues_output
        
        results = [
            {"status": "ok"},
            {"status": "ok"},
        ]
        
        m = mock_open()
        with patch("builtins.open", m):
            set_has_issues_output(results)
        
        m().write.assert_called_with("has_issues=false\n")
    
    @patch.dict(os.environ, {"GITHUB_OUTPUT": "/tmp/test_output"})
    def test_writes_true_when_error_status(self):
        """Writes has_issues=true when any result has error status."""
        from workout_import_qa import set_has_issues_output
        
        results = [
            {"status": "ok"},
            {"status": "error", "error": "timeout"},
        ]
        
        m = mock_open()
        with patch("builtins.open", m):
            set_has_issues_output(results)
        
        m().write.assert_called_with("has_issues=true\n")
    
    def test_no_crash_when_github_output_not_set(self):
        """Does not crash when GITHUB_OUTPUT is not set."""
        from workout_import_qa import set_has_issues_output
        
        env_without_github_output = os.environ.copy()
        env_without_github_output.pop("GITHUB_OUTPUT", None)
        
        with patch.dict(os.environ, env_without_github_output, clear=True):
            # Should not raise
            set_has_issues_output([{"status": "ok"}])
