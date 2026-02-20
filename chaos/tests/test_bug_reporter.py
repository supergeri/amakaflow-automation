# chaos/tests/test_bug_reporter.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from chaos.reporting.bug_reporter import BugReporter, BugSeverity


@pytest.fixture
def reporter(tmp_path):
    known_bugs_path = tmp_path / "known_bugs.json"
    known_bugs_path.write_text("{}")
    return BugReporter(
        known_bugs_path=str(known_bugs_path),
        linear_api_key="test-key",
        linear_team_id="test-team",
    )


class TestBugReporterDeduplication:
    def test_new_bug_not_duplicate(self, reporter):
        assert not reporter.is_duplicate("web/dashboard", "crash", ["tap Start", "tap Workout"])

    def test_same_bug_is_duplicate(self, reporter):
        reporter.record_known_bug("web/dashboard", "crash", ["tap Start", "tap Workout"])
        assert reporter.is_duplicate("web/dashboard", "crash", ["tap Start", "tap Workout"])

    def test_different_surface_not_duplicate(self, reporter):
        reporter.record_known_bug("web/dashboard", "crash", ["tap Start"])
        assert not reporter.is_duplicate("web/workout-builder", "crash", ["tap Start"])

    def test_known_bugs_persists_to_file(self, reporter, tmp_path):
        reporter.record_known_bug("web/dashboard", "crash", ["tap Start"])
        data = json.loads((tmp_path / "known_bugs.json").read_text())
        assert len(data) == 1


class TestBugReporterSeverity:
    def test_crash_is_urgent(self, reporter):
        assert reporter.classify_severity("app crashed", "crash") == BugSeverity.URGENT

    def test_data_loss_is_urgent(self, reporter):
        assert reporter.classify_severity("workout data lost", "data_loss") == BugSeverity.URGENT

    def test_visual_bug_is_medium(self, reporter):
        assert reporter.classify_severity("button misaligned", "visual") == BugSeverity.MEDIUM

    def test_ai_quality_is_medium(self, reporter):
        assert reporter.classify_severity("ai response off-topic", "ai_quality") == BugSeverity.MEDIUM


class TestBugReporterTitle:
    def test_title_format(self, reporter):
        title = reporter.build_title(
            persona="Complete Beginner / Explorer",
            surface="workout-builder",
            error_summary="crash on empty submit",
        )
        assert "[CHAOS]" in title
        assert "Complete Beginner" in title
        assert "workout-builder" in title
        assert "crash" in title.lower()
