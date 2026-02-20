"""Replay engine for testing workout data integrity.

Loads captured snapshots and replays them through pipeline stages
to identify where data divergence occurs.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union
import json
from deepdiff import DeepDiff


# Pipeline stages in order
DEFAULT_PIPELINE_STAGES = [
    "web-ingest",        # Initial workout data from web UI
    "phone-sync-request", # Request to sync from phone
    "completion-received", # Workout completion event
    "backend-stored",    # Final storage in backend
]


@dataclass
class SnapshotData:
    """A single captured snapshot."""
    capture_point: str
    session: str
    timestamp: float
    endpoint: str
    method: str
    request_payload: Any
    request_headers: Optional[dict]
    response_status: Optional[int]
    response_payload: Any
    streaming: bool
    chat_context: Optional[dict]


@dataclass
class HopDiff:
    """Diff between two hops in the pipeline."""
    hop_name: str
    path: str
    old_value: Any
    new_value: Any
    diff_type: str  # type of change


@dataclass
class ReplayResult:
    """Result of replaying a captured session."""
    session_name: str
    snapshots: list[SnapshotData] = field(default_factory=list)
    diffs: list[HopDiff] = field(default_factory=list)
    first_corruption_hop: Optional[str] = None
    is_clean: bool = True


def load_session(capture_dir: Path, session_name: str) -> list[SnapshotData]:
    """Load all snapshots for a session.
    
    Args:
        capture_dir: Root directory containing capture sessions
        session_name: Name of the session to load
        
    Returns:
        List of SnapshotData sorted by timestamp
    """
    session_dir = capture_dir / session_name
    if not session_dir.exists():
        return []
    
    snapshots = []
    for json_file in sorted(session_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text())
            snapshots.append(SnapshotData(
                capture_point=data.get("capture_point", ""),
                session=data.get("session", ""),
                timestamp=data.get("timestamp", 0),
                endpoint=data.get("endpoint", ""),
                method=data.get("method", ""),
                request_payload=data.get("request_payload"),
                request_headers=data.get("request_headers"),
                response_status=data.get("response_status"),
                response_payload=data.get("response_payload"),
                streaming=data.get("streaming", False),
                chat_context=data.get("chat_context"),
            ))
        except (json.JSONDecodeError, OSError):
            continue
    
    return sorted(snapshots, key=lambda s: s.timestamp)


def compute_diff(before: Any, after: Any, path: str = "") -> list[HopDiff]:
    """Compute diff between two data structures.
    
    Args:
        before: Earlier snapshot data
        after: Later snapshot data  
        path: Current path in the data structure
        
    Returns:
        List of HopDiff objects
    """
    diffs = []
    
    if before is None or after is None:
        return diffs
    
    deep_diff = DeepDiff(before, after, verbose_level=1)
    
    # Process added items (deepdiff returns a set of paths)
    added = deep_diff.get("dictionary_item_added", set())
    for item in added:
        diffs.append(HopDiff(
            hop_name=str(item),
            path=str(item),
            old_value=None,
            new_value=None,
            diff_type="added"
        ))
    
    # Process removed items (deepdiff returns a set of paths)
    removed = deep_diff.get("dictionary_item_removed", set())
    for item in removed:
        diffs.append(HopDiff(
            hop_name=str(item),
            path=str(item),
            old_value=None,
            new_value=None,
            diff_type="removed"
        ))
    
    # Process changed values (deepdiff returns dict with old/new values)
    for path_key, values in deep_diff.get("values_changed", {}).items():
        old_val = values.get("old_value")
        new_val = values.get("new_value")
        diffs.append(HopDiff(
            hop_name=path_key,
            path=path_key,
            old_value=old_val,
            new_value=new_val,
            diff_type="changed"
        ))
    
    # Process type changes
    for path_key, values in deep_diff.get("type_changes", {}).items():
        old_val = values.get("old_value")
        new_val = values.get("new_value")
        diffs.append(HopDiff(
            hop_name=path_key,
            path=path_key,
            old_value=old_val,
            new_value=new_val,
            diff_type="type_changed"
        ))
    
    return diffs


def replay_session(
    capture_dir: Path,
    session_name: str,
    pipeline_stages: Optional[list[str]] = None,
) -> ReplayResult:
    """Replay a captured session through pipeline stages.
    
    Args:
        capture_dir: Root directory containing capture sessions
        session_name: Name of the session to replay
        pipeline_stages: Ordered list of capture point names to compare
        
    Returns:
        ReplayResult with diffs and corruption analysis
    """
    stages = pipeline_stages or DEFAULT_PIPELINE_STAGES
    snapshots = load_session(capture_dir, session_name)
    
    if not snapshots:
        return ReplayResult(session_name=session_name)
    
    # Group snapshots by capture point, keep first of each type
    by_point: dict[str, SnapshotData] = {}
    for snap in snapshots:
        if snap.capture_point not in by_point:
            by_point[snap.capture_point] = snap
    
    # Compare consecutive stages
    all_diffs = []
    first_corruption = None
    
    prev_snap: Optional[SnapshotData] = None
    for stage in stages:
        curr_snap = by_point.get(stage)
        if curr_snap is None:
            continue
            
        if prev_snap is not None:
            # Compare response payloads between stages
            diffs = compute_diff(
                prev_snap.response_payload,
                curr_snap.response_payload,
                path=f"{prev_snap.capture_point} -> {curr_snap.capture_point}"
            )
            all_diffs.extend(diffs)
            
            if diffs and first_corruption is None:
                first_corruption = curr_snap.capture_point
        
        prev_snap = curr_snap
    
    return ReplayResult(
        session_name=session_name,
        snapshots=snapshots,
        diffs=all_diffs,
        first_corruption_hop=first_corruption,
        is_clean=len(all_diffs) == 0
    )


def get_device_path_diffs(
    capture_dir: Path,
    session_name: str,
    device: str,
) -> ReplayResult:
    """Replay a session filtered by device export path.
    
    Args:
        capture_dir: Root directory containing capture sessions
        session_name: Name of the session to replay
        device: Device type (garmin, apple, strava)
        
    Returns:
        ReplayResult with device-specific diffs
    """
    stages = {
        "garmin": ["web-ingest", "backend-stored"],
        "apple": ["web-ingest", "phone-sync-request", "backend-stored"],
        "strava": ["web-ingest", "completion-received", "backend-stored"],
    }.get(device.lower(), DEFAULT_PIPELINE_STAGES)
    
    return replay_session(capture_dir, session_name, stages)
