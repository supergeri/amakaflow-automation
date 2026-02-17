"""Breakdown analysis by type, source, and device.

Shows corruption rates grouped by different dimensions.
"""

from dataclasses import dataclass
from pathlib import Path
import json
from collections import defaultdict


@dataclass
class TypeBreakdown:
    """Corruption breakdown by workout type."""

    workout_type: str
    total_runs: int
    corrupt_runs: int

    @property
    def corruption_rate(self) -> float:
        """Percentage of runs with corruption."""
        if self.total_runs == 0:
            return 0.0
        return (self.corrupt_runs / self.total_runs) * 100


@dataclass
class SourceBreakdown:
    """Corruption breakdown by source."""

    source: str
    total_runs: int
    corrupt_runs: int

    @property
    def corruption_rate(self) -> float:
        """Percentage of runs with corruption."""
        if self.total_runs == 0:
            return 0.0
        return (self.corrupt_runs / self.total_runs) * 100


@dataclass
class DeviceBreakdown:
    """Corruption breakdown by device type."""

    device_type: str
    total_runs: int
    corrupt_runs: int

    @property
    def corruption_rate(self) -> float:
        """Percentage of runs with corruption."""
        if self.total_runs == 0:
            return 0.0
        return (self.corrupt_runs / self.total_runs) * 100


def find_capture_dirs(base_path: Path) -> list[Path]:
    """Find all capture directories under base_path."""
    if not base_path.exists():
        return []
    return [d for d in base_path.rglob("*") if d.is_dir() and (d / "metadata.json").exists()]


def load_metadata(metadata_path: Path) -> dict | None:
    """Load metadata.json file."""
    try:
        return json.loads(metadata_path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def breakdown_report(capture_dir: str | Path) -> dict:
    """Generate breakdown reports by type, source, and device.

    Args:
        capture_dir: Root directory containing capture sessions

    Returns:
        Dictionary with 'by_type', 'by_source', 'by_device' keys
    """
    base_path = Path(capture_dir)

    type_data: dict[str, dict] = defaultdict(lambda: {"total": 0, "corrupt": 0})
    source_data: dict[str, dict] = defaultdict(lambda: {"total": 0, "corrupt": 0})
    device_data: dict[str, dict] = defaultdict(lambda: {"total": 0, "corrupt": 0})

    for metadata_file in base_path.rglob("metadata.json"):
        metadata = load_metadata(metadata_file)
        if not metadata:
            continue

        # Check if run has corruption
        diff_summary = metadata.get("diff_summary", {})
        has_corruption = any(
            diff_summary.get(hop, {}).get("diff_count", 0) > 0
            for hop in diff_summary
        )

        # Extract tags
        tags = metadata.get("tags", {})
        workout_type = tags.get("workout_type", "unknown")
        source = tags.get("source", "unknown")
        device_type = tags.get("device_type", "unknown")

        # Update type breakdown
        type_data[workout_type]["total"] += 1
        if has_corruption:
            type_data[workout_type]["corrupt"] += 1

        # Update source breakdown
        source_data[source]["total"] += 1
        if has_corruption:
            source_data[source]["corrupt"] += 1

        # Update device breakdown
        device_data[device_type]["total"] += 1
        if has_corruption:
            device_data[device_type]["corrupt"] += 1

    # Build result objects
    by_type = [
        TypeBreakdown(workout_type=k, total_runs=v["total"], corrupt_runs=v["corrupt"])
        for k, v in type_data.items()
    ]
    by_type.sort(key=lambda x: x.corruption_rate, reverse=True)

    by_source = [
        SourceBreakdown(source=k, total_runs=v["total"], corrupt_runs=v["corrupt"])
        for k, v in source_data.items()
    ]
    by_source.sort(key=lambda x: x.corruption_rate, reverse=True)

    by_device = [
        DeviceBreakdown(device_type=k, total_runs=v["total"], corrupt_runs=v["corrupt"])
        for k, v in device_data.items()
    ]
    by_device.sort(key=lambda x: x.corruption_rate, reverse=True)

    return {
        "by_type": by_type,
        "by_source": by_source,
        "by_device": by_device,
    }


def print_breakdown_tables(breakdowns: dict) -> str:
    """Format breakdown reports as rich table strings."""
    lines = []

    # By Type
    lines.append("=== Corruption by Workout Type ===")
    by_type = breakdowns.get("by_type", [])
    if by_type:
        lines.append(f"{'Type':<20} {'Total':>8} {'Corrupt':>10} {'Rate':>10}")
        lines.append("-" * 50)
        for b in by_type:
            lines.append(f"{b.workout_type:<20} {b.total_runs:>8} {b.corrupt_runs:>10} {b.corruption_rate:>9.1f}%")
    else:
        lines.append("No data")
    lines.append("")

    # By Source
    lines.append("=== Corruption by Source ===")
    by_source = breakdowns.get("by_source", [])
    if by_source:
        lines.append(f"{'Source':<20} {'Total':>8} {'Corrupt':>10} {'Rate':>10}")
        lines.append("-" * 50)
        for b in by_source:
            lines.append(f"{b.source:<20} {b.total_runs:>8} {b.corrupt_runs:>10} {b.corruption_rate:>9.1f}%")
    else:
        lines.append("No data")
    lines.append("")

    # By Device
    lines.append("=== Corruption by Device ===")
    by_device = breakdowns.get("by_device", [])
    if by_device:
        lines.append(f"{'Device':<20} {'Total':>8} {'Corrupt':>10} {'Rate':>10}")
        lines.append("-" * 50)
        for b in by_device:
            lines.append(f"{b.device_type:<20} {b.total_runs:>8} {b.corrupt_runs:>10} {b.corruption_rate:>9.1f}%")
    else:
        lines.append("No data")

    return "\n".join(lines)
