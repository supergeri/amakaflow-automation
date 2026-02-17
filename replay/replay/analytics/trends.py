"""Time-series trend analysis.

Shows weekly corruption rate over specified time period.
"""

from dataclasses import dataclass
from pathlib import Path
import json
from collections import defaultdict
from datetime import datetime, timedelta


@dataclass
class WeeklyTrend:
    """Weekly corruption trend."""

    week_start: str  # ISO format date
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


def get_week_key(timestamp: float) -> str:
    """Get ISO week start date for a timestamp."""
    dt = datetime.fromtimestamp(timestamp)
    # Get Monday of the week
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def trend_report(
    capture_dir: str | Path,
    weeks: int = 8,
) -> list[WeeklyTrend]:
    """Generate weekly corruption trend report.

    Args:
        capture_dir: Root directory containing capture sessions
        weeks: Number of weeks to include (default: 8)

    Returns:
        List of WeeklyTrend objects sorted by week
    """
    base_path = Path(capture_dir)
    week_data: dict[str, dict] = defaultdict(lambda: {"total": 0, "corrupt": 0})

    for metadata_file in base_path.rglob("metadata.json"):
        metadata = load_metadata(metadata_file)
        if not metadata:
            continue

        timestamp = metadata.get("timestamp", 0)
        if timestamp == 0:
            continue

        week_key = get_week_key(timestamp)
        week_data[week_key]["total"] += 1

        # Check if run has corruption
        diff_summary = metadata.get("diff_summary", {})
        has_corruption = any(
            diff_summary.get(hop, {}).get("diff_count", 0) > 0
            for hop in diff_summary
        )
        if has_corruption:
            week_data[week_key]["corrupt"] += 1

    # Filter to most recent N weeks
    if week_data:
        sorted_weeks = sorted(week_data.keys(), reverse=True)
        recent_weeks = sorted_weeks[:weeks]
        week_data = {w: week_data[w] for w in recent_weeks}

    results = []
    for week_start, data in week_data.items():
        results.append(WeeklyTrend(
            week_start=week_start,
            total_runs=data["total"],
            corrupt_runs=data["corrupt"],
        ))

    return sorted(results, key=lambda t: t.week_start)


def print_trend_table(trends: list[WeeklyTrend]) -> str:
    """Format trend report as a rich table string."""
    if not trends:
        return "No capture data found."

    lines = ["=== Weekly Corruption Trends ===", ""]
    lines.append(f"{'Week Starting':<12} {'Total Runs':>12} {'Corrupt':>10} {'Corruption %':>14}")
    lines.append("-" * 52)

    for trend in trends:
        lines.append(
            f"{trend.week_start:<12} {trend.total_runs:>12} {trend.corrupt_runs:>10} "
            f"{trend.corruption_rate:>13.1f}%"
        )

    return "\n".join(lines)
