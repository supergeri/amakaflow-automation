"""Shared utilities for analytics modules."""

from pathlib import Path
import json
from typing import Any, Optional


def find_capture_dirs(base_path: Path) -> list[Path]:
    """Find all capture directories under base_path.
    
    Args:
        base_path: Root directory to search
        
    Returns:
        List of Path objects for directories containing metadata.json
    """
    if not base_path.exists():
        return []
    if not base_path.is_dir():
        return []
    return [d for d in base_path.rglob("*") if d.is_dir() and (d / "metadata.json").exists()]


def load_metadata(metadata_path: Path) -> Optional[dict[str, Any]]:
    """Load metadata.json file.
    
    Args:
        metadata_path: Path to metadata.json file
        
    Returns:
        Parsed metadata dict or None if loading fails
    """
    try:
        return json.loads(metadata_path.read_text())
    except (json.JSONDecodeError, FileNotFoundError, OSError):
        return None
