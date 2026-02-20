# chaos/reporting/bug_reporter.py
"""Bug reporter for Phase 1 Chaos Engine.

Deduplicates bugs by signature hash and auto-files to Linear.
"""

import hashlib
import json
from enum import IntEnum
from pathlib import Path
from typing import List, Optional

import httpx


class BugSeverity(IntEnum):
    URGENT = 1   # crash, data loss
    HIGH = 2
    MEDIUM = 3   # visual, AI quality
    LOW = 4


_CRASH_KEYWORDS = {"crash", "fatal", "killed", "force close", "unhandled exception"}
_DATA_LOSS_KEYWORDS = {"data lost", "data loss", "deleted", "gone", "missing workout"}


class BugReporter:
    def __init__(
        self,
        known_bugs_path: str,
        linear_api_key: str,
        linear_team_id: str,
    ) -> None:
        self._known_path = Path(known_bugs_path)
        self._api_key = linear_api_key
        self._team_id = linear_team_id

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _signature(self, surface: str, error_type: str, last_actions: List[str]) -> str:
        key = f"{surface}|{error_type}|{'|'.join(last_actions[-3:])}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def is_duplicate(self, surface: str, error_type: str, last_actions: List[str]) -> bool:
        sig = self._signature(surface, error_type, last_actions)
        known = json.loads(self._known_path.read_text())
        return sig in known

    def record_known_bug(self, surface: str, error_type: str, last_actions: List[str]) -> str:
        sig = self._signature(surface, error_type, last_actions)
        known = json.loads(self._known_path.read_text())
        known[sig] = known.get(sig, 0) + 1
        self._known_path.write_text(json.dumps(known, indent=2))
        return sig

    # ── Classification ────────────────────────────────────────────────────────

    def classify_severity(self, error_summary: str, error_type: str) -> BugSeverity:
        lower = error_summary.lower()
        if error_type in ("crash", "data_loss") or any(k in lower for k in _CRASH_KEYWORDS):
            return BugSeverity.URGENT
        if any(k in lower for k in _DATA_LOSS_KEYWORDS):
            return BugSeverity.URGENT
        return BugSeverity.MEDIUM

    def build_title(self, persona: str, surface: str, error_summary: str) -> str:
        persona_short = persona.split("/")[0].strip()
        summary_short = error_summary[:60].strip()
        return f"[CHAOS] {persona_short} on {surface}: {summary_short}"

    # ── Linear filing ─────────────────────────────────────────────────────────

    def file_bug(
        self,
        persona: str,
        surface: str,
        error_type: str,
        error_summary: str,
        replay_log: List[str],
        screenshot_path: Optional[str] = None,
    ) -> Optional[str]:
        """File a bug to Linear. Returns issue URL or None if duplicate/failed."""
        if self.is_duplicate(surface, error_type, replay_log):
            self.record_known_bug(surface, error_type, replay_log)
            return None

        severity = self.classify_severity(error_summary, error_type)
        title = self.build_title(persona, surface, error_summary)

        replay_md = "\n".join(f"  {i+1}. {action}" for i, action in enumerate(replay_log[-20:]))
        screenshot_note = f"\n**Screenshot:** `{screenshot_path}`" if screenshot_path else ""
        description = (
            f"## Chaos Engine Bug Report\n\n"
            f"**Persona:** {persona}\n"
            f"**Surface:** {surface}\n"
            f"**Error type:** {error_type}\n"
            f"**Summary:** {error_summary}\n"
            f"{screenshot_note}\n\n"
            f"## Replay (last {min(20, len(replay_log))} actions)\n\n{replay_md}\n\n"
            f"*Auto-filed by Chaos Engine Phase 1*"
        )

        try:
            resp = httpx.post(
                "https://api.linear.app/graphql",
                headers={"Authorization": self._api_key, "Content-Type": "application/json"},
                json={"query": """
                    mutation CreateIssue($input: IssueCreateInput!) {
                        issueCreate(input: $input) { issue { id url } }
                    }
                """, "variables": {"input": {
                    "teamId": self._team_id,
                    "title": title,
                    "description": description,
                    "priority": int(severity),
                    "labelIds": [],
                }}},
                timeout=15.0,
            )
            data = resp.json()
            url = data.get("data", {}).get("issueCreate", {}).get("issue", {}).get("url")
            if url:
                self.record_known_bug(surface, error_type, replay_log)
            return url
        except Exception:
            return None
