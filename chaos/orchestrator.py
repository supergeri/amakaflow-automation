# chaos/orchestrator.py
"""Nightly orchestrator for Phase 1 Chaos Engine.

Ties together: Strategist → (write directive) → OpenClaw chaos-driver
→ (read session log) → Judge → Bug Reporter → Nightly Digest.

Usage:
    python3 -m chaos.orchestrator                    # run one session
    python3 -m chaos.orchestrator --platform web     # explicit platform
    python3 -m chaos.orchestrator --dry-run          # strategist only, no driver
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from chaos.judge.rules import JudgeRules
from chaos.reporting.bug_reporter import BugReporter
from chaos.reporting.nightly_digest import NightlyDigest
from chaos.strategist.strategist import Strategist

_REPO_ROOT = Path(__file__).parent.parent
_CHAOS_DIR = Path(__file__).parent


def _load_personas():
    identities = yaml.safe_load((_CHAOS_DIR / "personas/fitness_identities.yaml").read_text())
    profiles = yaml.safe_load((_CHAOS_DIR / "personas/behaviour_profiles.yaml").read_text())
    return {"identities": identities["identities"], "profiles": profiles["profiles"]}


def run_session(platform: str = "web", dry_run: bool = False) -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifacts = _CHAOS_DIR / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "screenshots").mkdir(exist_ok=True)
    (artifacts / "logs").mkdir(exist_ok=True)
    (artifacts / "reports").mkdir(exist_ok=True)

    # 1. Strategist: pick next directive
    strategist = Strategist(
        state_graph_path=str(_CHAOS_DIR / "strategist/state_graph.json"),
        directives_path=str(_CHAOS_DIR / "strategist/directives.json"),
        personas=_load_personas(),
        platform=platform,
    )
    directive = strategist.get_next_directive()
    directive_path = artifacts / "current_directive.json"
    directive_path.write_text(json.dumps(directive, indent=2))
    print(f"[Strategist] Directive: {directive['persona_name']} on {directive['surface']} "
          f"({directive['chaos_directive']})")

    if dry_run:
        print("[Orchestrator] Dry run — skipping Driver and reporting")
        return {"directive": directive, "dry_run": True}

    # 2. Driver: run OpenClaw chaos-driver session
    session_log_path = artifacts / "current_session_log.jsonl"
    session_log_path.write_text("")  # clear previous
    print(f"[Driver] Starting OpenClaw chaos-driver session...")
    result = subprocess.run(
        ["openclaw", "--config", str(_REPO_ROOT / "openclaw.chaos.json"),
         "--skill", "chaos/skills/chaos-driver"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        print(f"[Driver] OpenClaw exited with code {result.returncode}", file=sys.stderr)

    # 3. Parse session log
    session_entries = []
    bugs_in_session = []
    ai_outputs = []
    if session_log_path.exists():
        for line in session_log_path.read_text().strip().splitlines():
            try:
                entry = json.loads(line)
                session_entries.append(entry)
                if entry.get("bug_flag"):
                    bugs_in_session.append(entry)
                if entry.get("ai_output"):
                    ai_outputs.append(entry)
            except json.JSONDecodeError:
                pass

    # 4. Judge: evaluate AI outputs
    judge = JudgeRules()
    judge_findings = judge.evaluate_session_ai_outputs({"ai_outputs": [
        {"feature": e.get("feature"), "output": e.get("output", {})}
        for e in ai_outputs
    ]})

    # 5. Bug Reporter: deduplicate and file
    reporter = BugReporter(
        known_bugs_path=str(_CHAOS_DIR / "memory/known_bugs.json"),
        linear_api_key=os.environ.get("LINEAR_API_KEY", ""),
        linear_team_id=os.environ.get("LINEAR_TEAM_ID", ""),
    )

    filed_bugs = []
    for bug in bugs_in_session:
        url = reporter.file_bug(
            persona=directive["persona_name"],
            surface=directive["surface"],
            error_type=bug.get("bug_flag", "unknown"),
            error_summary=bug.get("result", ""),
            replay_log=[e.get("action", "") for e in session_entries],
            screenshot_path=bug.get("screen"),
        )
        if url:
            filed_bugs.append(url)

    # Also file AI quality bugs
    for finding in judge_findings:
        url = reporter.file_bug(
            persona=directive["persona_name"],
            surface=f"ai/{finding['feature']}",
            error_type="ai_quality",
            error_summary=" | ".join(finding["flags"]),
            replay_log=[e.get("action", "") for e in session_entries],
        )
        if url:
            filed_bugs.append(url)

    # 6. Update Strategist state graph
    strategist.record_visit(
        f"{platform}/{directive['surface']}",
        bugs_found=len(filed_bugs),
    )

    # 7. Save session archive
    archive_path = artifacts / "logs" / f"session-{timestamp}.jsonl"
    archive_path.write_text(session_log_path.read_text())

    summary = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "personas_run": 1,
        "actions_taken": len([e for e in session_entries if e.get("step")]),
        "bugs_filed": len(filed_bugs),
        "duplicates_suppressed": len(bugs_in_session) - len(filed_bugs),
        "new_bugs": [{"title": url, "severity": 3} for url in filed_bugs],
        "ai_scores": {},
        "surfaces_hit": [directive["surface"]],
        "surfaces_missed": [],
    }

    # 8. Nightly digest
    digest = NightlyDigest().format(summary)
    digest_path = artifacts / "reports" / f"digest-{timestamp}.txt"
    digest_path.write_text(digest)
    print(digest)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chaos Engine Orchestrator")
    parser.add_argument("--platform", default="web")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_session(platform=args.platform, dry_run=args.dry_run)
