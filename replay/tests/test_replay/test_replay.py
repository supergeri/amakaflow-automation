"""Tests for replay engine."""

import json
from pathlib import Path

import pytest

from replay.replay import (
    load_session,
    compute_diff,
    replay_session,
    get_device_path_diffs,
    SnapshotData,
)


@pytest.fixture
def capture_dir(tmp_path: Path) -> Path:
    """Create a capture directory with test data."""
    session_dir = tmp_path / "test-session"
    session_dir.mkdir(parents=True)
    
    # Create test snapshots
    snapshots = [
        {
            "capture_point": "web-ingest",
            "session": "test-session",
            "timestamp": 1000.0,
            "endpoint": "/api/workouts/import/stream",
            "method": "POST",
            "request_payload": {"url": "https://youtube.com/watch?v=abc"},
            "request_headers": {},
            "response_status": 200,
            "response_payload": {"id": "123", "title": "Morning Run"},
            "streaming": True,
            "chat_context": None,
        },
        {
            "capture_point": "backend-stored",
            "session": "test-session",
            "timestamp": 1001.0,
            "endpoint": "/api/workouts/save/stream",
            "method": "POST",
            "request_payload": {"id": "123"},
            "request_headers": {},
            "response_status": 200,
            "response_payload": {"id": "123", "title": "Morning Run", "source": "youtube"},
            "streaming": True,
            "chat_context": None,
        },
    ]
    
    for i, snap in enumerate(snapshots):
        filepath = session_dir / f"00{i+1:02d}_{snap['capture_point']}.json"
        filepath.write_text(json.dumps(snap))
    
    return tmp_path


class TestLoadSession:
    def test_load_session(self, capture_dir: Path):
        """Test loading snapshots from a session."""
        snapshots = load_session(capture_dir, "test-session")
        
        assert len(snapshots) == 2
        assert snapshots[0].capture_point == "web-ingest"
        assert snapshots[1].capture_point == "backend-stored"

    def test_load_nonexistent_session(self, capture_dir: Path):
        """Test loading a session that doesn't exist."""
        snapshots = load_session(capture_dir, "nonexistent")
        assert snapshots == []


class TestComputeDiff:
    def test_detects_added_field(self):
        """Test that added fields are detected."""
        before = {"id": "123", "title": "Run"}
        after = {"id": "123", "title": "Run", "source": "youtube"}
        
        diffs = compute_diff(before, after)
        
        assert len(diffs) > 0

    def test_detects_changed_value(self):
        """Test that changed values are detected."""
        before = {"id": "123", "title": "Run"}
        after = {"id": "123", "title": "Morning Run"}
        
        diffs = compute_diff(before, after)
        
        assert len(diffs) > 0
        assert any(d.diff_type == "changed" for d in diffs)

    def test_detects_removed_field(self):
        """Test that removed fields are detected."""
        before = {"id": "123", "title": "Run", "source": "youtube"}
        after = {"id": "123", "title": "Run"}
        
        diffs = compute_diff(before, after)
        
        assert len(diffs) > 0


class TestReplaySession:
    def test_replay_clean_session(self, capture_dir: Path):
        """Test replaying a session with no corruption."""
        result = replay_session(capture_dir, "test-session")
        
        assert result.session_name == "test-session"
        assert len(result.snapshots) == 2
        # The test data has a diff (added "source" field)
        assert not result.is_clean
        assert result.first_corruption_hop == "backend-stored"

    def test_get_device_path_garmin(self, capture_dir: Path):
        """Test Garmin device path analysis."""
        result = get_device_path_diffs(capture_dir, "test-session", "garmin")
        
        assert result.session_name == "test-session"
        # Should have diffs between web-ingest and backend-stored
        assert len(result.diffs) > 0
