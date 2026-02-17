"""Pipeline health aggregation.

Shows per-hop clean rate and average latency.
"""

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
from typing import Union, List

from .utils import load_metadata


@dataclass
class HopHealth:
    """Health metrics for a single hop."""

    name: str
    total_runs: int
    clean_runs: int
    avg_latency_ms: float

    @property
    def clean_rate(self) -> float:
        """Percentage of clean (no diff) runs."""
        if self.total_runs == 0:
            return 0.0
        return (self.clean_runs / self.total_runs) * 100


def health_report(capture_dir: Union[str, Path]) -> List[HopHealth]:
    """Generate per-hop health report.

    Args:
        capture_dir: Root directory containing capture sessions

    Returns:
        List of HopHealth objects sorted by hop name
    """
    base_path = Path(capture_dir)
    
    # Validate input
    if not base_path.exists():
        return []
    if not base_path.is_dir():
        return []
    
    hop_data: dict[str, dict] = defaultdict(lambda: {"total": 0, "clean": 0, "latencies": []})

    try:
        metadata_files = base_path.rglob("metadata.json")
    except OSError:
        return []

    for metadata_file in metadata_files:
        metadata = load_metadata(metadata_file)
        if not metadata:
            continue

        timing = metadata.get("timing", {})
        diff_summary = metadata.get("diff_summary", {})

        for hop_name, hop_info in timing.items():
            # Validate hop_info is a dict before accessing
            if not isinstance(hop_info, dict):
                continue
            latency_ms = hop_info.get("latency_ms", 0)
            hop_data[hop_name]["total"] += 1
            hop_data[hop_name]["latencies"].append(latency_ms)

        # Check if run was clean (no diffs)
        has_diffs = any(diff_summary.get(hop, {}).get("diff_count", 0) > 0 for hop in diff_summary)
        if not has_diffs:
            for hop_name in timing.keys():
                hop_data[hop_name]["clean"] += 1

    results = []
    for hop_name, data in hop_data.items():
        latencies = data["latencies"]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        results.append(HopHealth(
            name=hop_name,
            total_runs=data["total"],
            clean_runs=data["clean"],
            avg_latency_ms=avg_latency,
        ))

    return sorted(results, key=lambda h: h.name)


def print_health_table(hop_health: list[HopHealth]) -> str:
    """Format health report as a rich table string."""
    if not hop_health:
        return "No capture data found."

    lines = ["=== Pipeline Health ===", ""]
    lines.append(f"{'Hop':<20} {'Runs':>8} {'Clean':>8} {'Clean %':>10} {'Avg Latency':>12}")
    lines.append("-" * 60)

    for hop in hop_health:
        lines.append(
            f"{hop.name:<20} {hop.total_runs:>8} {hop.clean_runs:>8} "
            f"{hop.clean_rate:>9.1f}% {hop.avg_latency_ms:>11.1f}ms"
        )

    return "\n".join(lines)
