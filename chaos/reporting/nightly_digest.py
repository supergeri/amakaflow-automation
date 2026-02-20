# chaos/reporting/nightly_digest.py
"""Nightly digest formatter for the Chaos Engine."""

from typing import Any, Dict


class NightlyDigest:
    def format(self, report: Dict[str, Any]) -> str:
        date = report.get("date", "unknown")
        lines = [
            f"🤖 Chaos Engine — {date}",
            "",
            f"Personas run: {report['personas_run']}  |  "
            f"Actions: {report['actions_taken']}  |  "
            f"Bugs filed: {report['bugs_filed']}  |  "
            f"Duplicates suppressed: {report['duplicates_suppressed']}",
            "",
        ]

        bugs = report.get("new_bugs", [])
        lines.append("NEW BUGS" if bugs else "NEW BUGS\n  No new bugs 🎉")
        for bug in bugs:
            sev = "🔴 CRASH" if bug.get("severity") == 1 else "🟡 MEDIUM"
            lines.append(f"  • {sev} {bug['title']}")
        lines.append("")

        scores = report.get("ai_scores", {})
        if scores:
            lines.append("AI QUALITY (avg this session)")
            for feature, score in scores.items():
                icon = "✅" if score >= 3.5 else "⚠️"
                lines.append(f"  • {feature}: {score:.1f}/5 {icon}")
            lines.append("")

        hit = report.get("surfaces_hit", [])
        missed = report.get("surfaces_missed", [])
        lines.append(f"SURFACES HIT:    {', '.join(hit) if hit else 'none'}")
        lines.append(f"SURFACES MISSED: {', '.join(missed) if missed else 'none'}")

        return "\n".join(lines)
