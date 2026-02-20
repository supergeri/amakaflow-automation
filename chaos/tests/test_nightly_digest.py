# chaos/tests/test_nightly_digest.py
from chaos.reporting.nightly_digest import NightlyDigest


def test_digest_has_all_sections():
    report = {
        "date": "2026-02-20",
        "personas_run": 8,
        "actions_taken": 847,
        "bugs_filed": 3,
        "duplicates_suppressed": 12,
        "new_bugs": [
            {"title": "[CHAOS] Rage Tapper on iOS: crash", "severity": 1},
        ],
        "ai_scores": {"workout-generation": 4.2, "chat-response-quality": 2.9},
        "surfaces_hit": ["dashboard", "workout-builder"],
        "surfaces_missed": ["settings"],
    }
    digest = NightlyDigest().format(report)
    assert "Chaos Engine" in digest
    assert "2026-02-20" in digest
    assert "8" in digest          # personas_run
    assert "847" in digest        # actions_taken
    assert "Rage Tapper" in digest
    assert "2.9" in digest        # low AI score
    assert "⚠️" in digest         # warning for low score
    assert "settings" in digest   # missed surfaces


def test_digest_empty_bugs():
    report = {
        "date": "2026-02-20",
        "personas_run": 4,
        "actions_taken": 200,
        "bugs_filed": 0,
        "duplicates_suppressed": 3,
        "new_bugs": [],
        "ai_scores": {},
        "surfaces_hit": ["dashboard"],
        "surfaces_missed": [],
    }
    digest = NightlyDigest().format(report)
    assert "0" in digest
    assert "No new bugs" in digest or "bugs_filed: 0" in digest or "Bugs filed: 0" in digest
