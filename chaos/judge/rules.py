# chaos/judge/rules.py
"""Rule-based Judge for Phase 1 Chaos Engine.

Evaluates AI outputs from Driver sessions using fast heuristics.
No LLM calls — pure Python. Phase 2 will add Haiku scoring on top.
"""

import re
from typing import Any, Dict, List

_VALID_TAG_TYPES = {
    "topic", "muscle_group", "equipment", "methodology",
    "sport", "movement_pattern", "goal",
}

_EXTREME_NUMBER_PATTERN = re.compile(
    r"\b([4-9]\d{2,}|[1-9]\d{3,})\s*(kg|lbs|reps|sets|weeks?|days?)\b",
    re.IGNORECASE,
)


class JudgeRules:
    """Fast heuristic evaluation of AI outputs. Returns list of flag strings.
    Empty list means pass. Non-empty means warn/fail."""

    def evaluate_workout(self, output: Dict[str, Any]) -> List[str]:
        flags = []
        sets = output.get("sets", 0)
        reps = output.get("reps", 0)
        exercises = output.get("exercises", [])

        if isinstance(sets, (int, float)) and sets > 10:
            flags.append(f"SUSPECT: sets={sets} exceeds reasonable max (10)")
        if isinstance(reps, (int, float)) and reps > 100:
            flags.append(f"SUSPECT: reps={reps} exceeds reasonable max (100)")
        if isinstance(exercises, list) and len(exercises) > 15:
            flags.append(f"SUSPECT: {len(exercises)} exercises in one workout (max 15)")

        return flags

    def evaluate_micro_summary(self, text: str) -> List[str]:
        flags = []
        if not text:
            flags.append("FAIL: micro_summary is empty")
            return flags
        if len(text) > 100:
            flags.append(f"FAIL: micro_summary is {len(text)} chars (max 100)")
        if len(text) == 100 and not text[-1] in ".!? ":
            flags.append("WARN: micro_summary likely truncated mid-word at 100 chars")
        return flags

    def evaluate_tags(self, tags: List[Dict[str, Any]]) -> List[str]:
        flags = []
        if len(tags) < 3:
            flags.append(f"WARN: too few tags ({len(tags)}, expect 3-8)")
        if len(tags) > 8:
            flags.append(f"WARN: too many tags ({len(tags)}, expect 3-8)")
        for tag in tags:
            if tag.get("tag_type") not in _VALID_TAG_TYPES:
                flags.append(f"FAIL: invalid tag_type '{tag.get('tag_type')}'")
            conf = tag.get("confidence", 0)
            if isinstance(conf, (int, float)) and conf < 0.5:
                flags.append(f"WARN: low confidence ({conf}) for tag '{tag.get('name')}'")
        return flags

    def evaluate_chat_response(self, text: str) -> List[str]:
        flags = []
        if not text:
            flags.append("FAIL: chat response is empty")
            return flags
        if len(text.split()) < 5:
            flags.append(f"WARN: chat response too short ({len(text.split())} words)")
        if _EXTREME_NUMBER_PATTERN.search(text):
            flags.append("WARN: response contains extreme numeric claim — possible hallucination")
        return flags

    def evaluate_session_ai_outputs(self, session_log: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run all evaluations against AI outputs captured in a Driver session log.

        Returns list of findings, each with: feature, output_snippet, flags.
        """
        findings = []
        for entry in session_log.get("ai_outputs", []):
            feature = entry.get("feature")
            output = entry.get("output", {})
            flags = []

            if feature == "workout-generation":
                flags = self.evaluate_workout(output)
                ms = output.get("micro_summary", "")
                flags += self.evaluate_micro_summary(ms)
            elif feature == "kb-tag-discover":
                flags = self.evaluate_tags(output if isinstance(output, list) else [])
            elif feature == "chat-response-quality":
                flags = self.evaluate_chat_response(str(output.get("text", "")))
            elif feature == "kb-summarise":
                ms = output.get("micro_summary", "")
                flags = self.evaluate_micro_summary(ms)

            if flags:
                findings.append({
                    "feature": feature,
                    "output_snippet": str(output)[:200],
                    "flags": flags,
                })
        return findings
