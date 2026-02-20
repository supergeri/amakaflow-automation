# AMA-677 Chaos Engine — Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Phase 1 of the Chaos Engine — a nightly human-like E2E testing system that drives the web app using a vision-action loop, 20 personas, rule-based AI quality evaluation, and automatic Linear bug filing.

**Architecture:** Strategist (Python script, reads/writes state_graph.json, scores surfaces, outputs directive JSON) → OpenClaw chaos-driver skill (receives directive, runs vision-action loop using browser tool + Claude Haiku, outputs structured session log) → Judge (Python heuristics evaluate AI outputs from log) → Bug Reporter (deduplicates, auto-files to Linear). All wired by a nightly orchestrator script.

**Tech Stack:** Python 3.11+, httpx, pytest, PyYAML, OpenClaw (existing), Claude Haiku (`claude-haiku-4-5-20251001`) for vision-action loop, Linear REST API for bug filing.

**Repo:** `supergeri/amakaflow-automation`

**Design doc:** `2026-02-19-ama-677-chaos-engine-design.md` (in this repo root)

**Phase 1 scope:** Web platform only, sequential execution, Haiku everywhere, nightly 11pm cron, Garmin data emitter (no UI simulator), Judge = rule-based heuristics, 20 fitness identities × 8 behaviour profiles defined (but Strategist rotates through them one per night).

---

## Task 1: Directory Scaffold

**Files:**
- Create: `chaos/__init__.py`
- Create: `chaos/strategist/__init__.py`
- Create: `chaos/drivers/__init__.py`
- Create: `chaos/judge/__init__.py`
- Create: `chaos/reporting/__init__.py`
- Create: `chaos/tests/__init__.py`
- Create: `chaos/memory/known_bugs.json`
- Create: `.gitignore` additions

**Step 1: Create directory tree**

```bash
cd /path/to/amakaflow-automation
mkdir -p chaos/{strategist,personas,drivers,judge,reporting,memory/personas,artifacts/{screenshots,logs,reports},skills,tests}
touch chaos/__init__.py
touch chaos/strategist/__init__.py
touch chaos/drivers/__init__.py
touch chaos/judge/__init__.py
touch chaos/reporting/__init__.py
touch chaos/tests/__init__.py
echo '{}' > chaos/memory/known_bugs.json
```

**Step 2: Seed .gitignore** (append to repo root `.gitignore`)

```
# Chaos Engine runtime artifacts
chaos/artifacts/screenshots/
chaos/artifacts/logs/
chaos/artifacts/reports/
chaos/memory/personas/
# Keep known_bugs.json tracked (dedup store persists across sessions)
!chaos/memory/known_bugs.json
```

**Step 3: Verify structure**

```bash
find chaos/ -type f | sort
```
Expected: all `__init__.py` files and `memory/known_bugs.json` listed.

**Step 4: Commit**

```bash
git add chaos/ .gitignore
git commit -m "feat(AMA-677): scaffold chaos engine directory structure"
```

---

## Task 2: openclaw.chaos.json

**Files:**
- Create: `openclaw.chaos.json`

**Step 1: Create the config**

```json
{
  "name": "amakaflow-chaos-engine",
  "description": "Chaos Engine — human-like E2E testing for AmakaFlow (Phase 1: web, nightly, Haiku)",
  "version": "1.0.0",
  "models": {
    "default": {
      "provider": "anthropic",
      "model": "claude-haiku-4-5-20251001",
      "apiKeyEnv": "ANTHROPIC_API_KEY",
      "maxTokens": 4096,
      "temperature": 0.7
    }
  },
  "routing": {
    "default": "default"
  },
  "tools": {
    "browser": {
      "enabled": true,
      "headless": true,
      "timeout": 30000,
      "viewport": { "width": 1280, "height": 720 }
    },
    "exec": {
      "enabled": true,
      "timeout": 120000,
      "shell": "/bin/bash"
    },
    "read": {
      "enabled": true,
      "allowedPaths": [
        "chaos/**",
        "*.md",
        "*.json"
      ]
    },
    "write": {
      "enabled": true,
      "allowedPaths": [
        "chaos/artifacts/**",
        "chaos/memory/**"
      ]
    }
  },
  "environment": {
    "UI_URL": "http://localhost:3000",
    "CHAT_API_URL": "http://localhost:8005",
    "MAPPER_API_URL": "http://localhost:8001",
    "CALENDAR_API_URL": "http://localhost:8003",
    "INGESTOR_API_URL": "http://localhost:8004"
  },
  "skills": ["chaos/skills/chaos-driver"],
  "artifacts": {
    "directory": "chaos/artifacts",
    "screenshots": "chaos/artifacts/screenshots",
    "logs": "chaos/artifacts/logs",
    "reports": "chaos/artifacts/reports"
  },
  "mode": "B",
  "phase": 1,
  "defaults": {
    "platform": "web",
    "parallel": false,
    "max_steps_per_session": 50,
    "schedule": "0 23 * * *"
  }
}
```

**Step 2: Verify JSON is valid**

```bash
python3 -c "import json; json.load(open('openclaw.chaos.json')); print('valid')"
```
Expected: `valid`

**Step 3: Commit**

```bash
git add openclaw.chaos.json
git commit -m "feat(AMA-677): add openclaw.chaos.json — Haiku-based chaos engine config"
```

---

## Task 3: State Graph Seed

**Files:**
- Create: `chaos/strategist/state_graph.json`
- Create: `chaos/strategist/directives.json`

**Step 1: Create state_graph.json**

```json
{
  "version": "1.0",
  "surfaces": {
    "web": {
      "screens": [
        "dashboard",
        "workout-builder",
        "workout-detail",
        "workout-log-active",
        "kb-cards-list",
        "kb-card-detail",
        "kb-card-create",
        "kb-card-edit",
        "chat",
        "settings",
        "instagram-import",
        "instagram-import-settings",
        "profile",
        "auth-login",
        "auth-signup",
        "empty-state-no-workouts",
        "empty-state-no-kb-cards"
      ],
      "ai_features": [
        "workout-generation",
        "kb-summarise",
        "kb-tag-discover",
        "kb-relationships",
        "chat-response-quality"
      ],
      "edge_states": [
        "session-expiry-mid-flow",
        "loading-timeout",
        "concurrent-edit",
        "empty-form-submit",
        "error-state-api-down"
      ]
    },
    "ios": {
      "screens": [],
      "ai_features": [],
      "edge_states": [],
      "note": "Phase 2"
    },
    "android": {
      "screens": [],
      "ai_features": [],
      "edge_states": [],
      "note": "Phase 2"
    },
    "garmin": {
      "data_events": [
        "sync-workout-complete",
        "sync-mid-workout-disconnect",
        "sync-duplicate-workout",
        "sync-zero-duration",
        "sync-future-timestamp",
        "sync-corrupt-gps",
        "sync-extreme-heart-rate",
        "sync-partial-payload"
      ],
      "note": "Phase 1: data emitter only"
    }
  },
  "explored": {},
  "last_updated": null
}
```

**Step 2: Create directives.json**

```json
{
  "version": "1.0",
  "directives": [
    {
      "id": "submit-empty-fields",
      "description": "Navigate to a form and attempt to submit it with all fields empty",
      "weight": 0.8,
      "applicable_surfaces": ["workout-builder", "kb-card-create", "auth-signup"]
    },
    {
      "id": "rapid-tap-before-load",
      "description": "Click buttons repeatedly before the page has finished loading",
      "weight": 0.7,
      "applicable_surfaces": ["all"]
    },
    {
      "id": "background-foreground-mid-flow",
      "description": "Navigate away to another browser tab mid-flow, then return",
      "weight": 0.9,
      "applicable_surfaces": ["workout-log-active", "kb-card-edit", "instagram-import"]
    },
    {
      "id": "kill-network-during-ai-request",
      "description": "Trigger an AI feature then immediately navigate away before it completes",
      "weight": 0.9,
      "applicable_surfaces": ["workout-builder", "kb-card-create", "chat"]
    },
    {
      "id": "spam-chat",
      "description": "Send 5+ rapid messages to the chat without waiting for responses",
      "weight": 0.7,
      "applicable_surfaces": ["chat"]
    },
    {
      "id": "exceed-content-length",
      "description": "Paste extremely long content (5000+ characters) into a text field",
      "weight": 0.8,
      "applicable_surfaces": ["kb-card-create", "kb-card-edit", "chat"]
    },
    {
      "id": "log-zero-reps",
      "description": "Attempt to log a workout set with zero reps or zero weight",
      "weight": 0.9,
      "applicable_surfaces": ["workout-log-active"]
    },
    {
      "id": "log-extreme-values",
      "description": "Enter extreme values: 9999 reps, 9999kg weight, -5 sets",
      "weight": 0.8,
      "applicable_surfaces": ["workout-log-active", "workout-builder"]
    },
    {
      "id": "abandon-and-return",
      "description": "Start a flow, navigate away entirely, then return via back button or direct URL",
      "weight": 0.9,
      "applicable_surfaces": ["workout-log-active", "kb-card-create", "instagram-import"]
    },
    {
      "id": "concurrent-edits",
      "description": "Open the same item in two browser tabs and edit both simultaneously",
      "weight": 0.7,
      "applicable_surfaces": ["kb-card-edit", "workout-builder"]
    },
    {
      "id": "explore-freely",
      "description": "No specific chaos — explore the app naturally as the persona would",
      "weight": 0.5,
      "applicable_surfaces": ["all"]
    },
    {
      "id": "break-auth",
      "description": "Let session expire naturally by waiting, then attempt an action",
      "weight": 0.6,
      "applicable_surfaces": ["all"]
    }
  ]
}
```

**Step 3: Validate both files**

```bash
python3 -c "
import json
sg = json.load(open('chaos/strategist/state_graph.json'))
d = json.load(open('chaos/strategist/directives.json'))
print(f'Surfaces: {list(sg[\"surfaces\"].keys())}')
print(f'Web screens: {len(sg[\"surfaces\"][\"web\"][\"screens\"])}')
print(f'Directives: {len(d[\"directives\"])}')
"
```
Expected: `Surfaces: ['web', 'ios', 'android', 'garmin']`, `Web screens: 17`, `Directives: 12`

**Step 4: Commit**

```bash
git add chaos/strategist/
git commit -m "feat(AMA-677): seed state graph and chaos directives library"
```

---

## Task 4: Persona Library

**Files:**
- Create: `chaos/personas/fitness_identities.yaml`
- Create: `chaos/personas/behaviour_profiles.yaml`

**Step 1: Create fitness_identities.yaml**

```yaml
# 20 fitness identity personas
# Each defines WHO the user is — their goals, device, and knowledge level.
# These compose with behaviour_profiles.yaml to produce 160 distinct driver sessions.

identities:
  - id: complete-beginner
    name: "Complete Beginner"
    primary_device: iphone
    goals: ["lose weight", "build basic fitness"]
    tech_savvy: none
    workout_types: ["bodyweight", "machines"]
    typical_hr: 140
    description: "Never worked out before. Doesn't understand fitness terminology. Likely to misread instructions."

  - id: casual-gym-goer
    name: "Casual Gym-Goer"
    primary_device: iphone_apple_watch
    goals: ["consistency", "feel better"]
    tech_savvy: low
    workout_types: ["strength", "cardio"]
    typical_hr: 135
    description: "Goes to the gym 2x/week. Follows basic programs. Knows the fundamentals but not advanced features."

  - id: serious-powerlifter
    name: "Serious Powerlifter"
    primary_device: android_garmin
    goals: ["PRs", "periodisation", "strength numbers"]
    tech_savvy: high
    workout_types: ["powerlifting", "strength"]
    typical_hr: 120
    description: "Tracks every set/rep. Cares deeply about data accuracy. Will notice if numbers are wrong."

  - id: marathon-runner
    name: "Marathon Runner"
    primary_device: garmin
    goals: ["zone 2 training", "weekly mileage", "race time"]
    tech_savvy: high
    workout_types: ["running", "cardio"]
    typical_hr: 145
    description: "Primarily uses Garmin. Expects seamless sync. Focused on pace, HR zones, and distance."

  - id: hyrox-competitor
    name: "HYROX Competitor"
    primary_device: garmin_apple_watch
    goals: ["race prep", "functional fitness", "benchmark times"]
    tech_savvy: high
    workout_types: ["functional", "strength", "cardio"]
    typical_hr: 155
    description: "High-intensity training. Mixes strength and cardio. Expects the app to handle hybrid workouts."

  - id: triathlete
    name: "Triathlete"
    primary_device: garmin
    goals: ["multi-sport logging", "transition tracking"]
    tech_savvy: expert
    workout_types: ["swimming", "cycling", "running"]
    typical_hr: 150
    description: "Logs swim/bike/run. Expects multi-sport session support. Very data-focused."

  - id: cyclist
    name: "Cyclist"
    primary_device: garmin_android
    goals: ["FTP improvement", "watts/kg", "distance"]
    tech_savvy: expert
    workout_types: ["cycling"]
    typical_hr: 148
    description: "Power-meter user. Expects watts, cadence, FTP calculations. Will test edge cases in metrics."

  - id: crossfitter
    name: "CrossFitter"
    primary_device: iphone
    goals: ["WOD completion", "benchmark times", "gymnastics skills"]
    tech_savvy: medium
    workout_types: ["crossfit", "functional", "strength"]
    typical_hr: 160
    description: "Follows WOD format. Expects AMRAP/EMOM/For Time workout types. Fast-paced interactions."

  - id: bodybuilder
    name: "Bodybuilder"
    primary_device: android
    goals: ["hypertrophy", "macro tracking", "muscle isolation"]
    tech_savvy: medium
    workout_types: ["bodybuilding", "strength"]
    typical_hr: 125
    description: "High volume training. Tracks every muscle group. Cares about exercise taxonomy."

  - id: yoga-mobility
    name: "Yoga / Mobility Focused"
    primary_device: iphone
    goals: ["flexibility", "recovery", "HRV improvement", "stress reduction"]
    tech_savvy: low
    workout_types: ["yoga", "mobility", "stretching"]
    typical_hr: 95
    description: "Minimal tech interest. Uses app mostly for logging and recovery insights."

  - id: elderly-user
    name: "Elderly User (65+)"
    primary_device: iphone_large_text
    goals: ["health maintenance", "step counting", "doctor recommendations"]
    tech_savvy: very_low
    workout_types: ["walking", "light-resistance"]
    typical_hr: 110
    accessibility: ["large_text", "reduce_motion"]
    description: "Very low tech literacy. Easily confused by UI. Likely to misread buttons. Critical for accessibility testing."

  - id: rehab-recovery
    name: "Rehab / Injury Recovery"
    primary_device: iphone
    goals: ["physio exercises", "pain-free movement", "gradual progression"]
    tech_savvy: low
    workout_types: ["rehab", "bodyweight", "stretching"]
    typical_hr: 100
    description: "Follows specific physio program. Very cautious about overloading. Tests low-weight/low-rep inputs."

  - id: personal-trainer
    name: "Personal Trainer"
    primary_device: web_iphone
    goals: ["client management", "program creation", "progress tracking"]
    tech_savvy: expert
    workout_types: ["all"]
    typical_hr: 130
    description: "Power user. Creates programs for clients. Will explore every feature. Most likely to hit edge cases."

  - id: group-fitness-coach
    name: "Group Fitness Coach"
    primary_device: ipad_web
    goals: ["class planning", "participant tracking", "timer management"]
    tech_savvy: medium
    workout_types: ["group-fitness", "hiit", "circuits"]
    typical_hr: 145
    description: "Needs the app to work during live classes. Low tolerance for latency or bugs."

  - id: weight-loss-journey
    name: "Weight Loss Journey"
    primary_device: android
    goals: ["calorie tracking", "progress photos", "consistent logging"]
    tech_savvy: low
    workout_types: ["cardio", "light-strength"]
    typical_hr: 138
    description: "Motivated but easily discouraged. Will abandon app if frustrated. High churn risk."

  - id: teen-athlete
    name: "Teen Athlete"
    primary_device: iphone
    goals: ["sport performance", "speed", "agility"]
    tech_savvy: low
    workout_types: ["sport-specific", "strength", "plyometrics"]
    typical_hr: 155
    description: "Fast interactions. Minimal patience. Will try to break things out of curiosity."

  - id: nutrition-obsessed
    name: "Nutrition-Obsessed User"
    primary_device: web
    goals: ["macro tracking", "meal logging", "body composition"]
    tech_savvy: high
    workout_types: ["strength", "cardio"]
    typical_hr: 128
    description: "Highly analytical. Will test edge cases in nutrition data. Expects precise numbers."

  - id: data-hoarder
    name: "Data Hoarder"
    primary_device: garmin_all
    goals: ["export everything", "complete history", "data portability"]
    tech_savvy: expert
    workout_types: ["all"]
    typical_hr: 135
    description: "Connects every device. Tries to export all data. Tests API limits and data integrity."

  - id: wearable-skeptic
    name: "Wearable Skeptic"
    primary_device: web_only
    goals: ["manual logging", "simple tracking", "no device dependency"]
    tech_savvy: low
    workout_types: ["strength", "cardio"]
    typical_hr: null
    description: "No wearable device. Tests the manual-only path through the app. Many users are in this category."

  - id: privacy-paranoid
    name: "Privacy Paranoid User"
    primary_device: iphone
    goals: ["fitness tracking with minimal data sharing"]
    tech_savvy: medium
    workout_types: ["strength", "cardio"]
    typical_hr: 130
    description: "Denies all optional permissions. Tests the app's behaviour when data access is restricted."
```

**Step 2: Create behaviour_profiles.yaml**

```yaml
# 8 behaviour profiles
# Each defines HOW the user interacts — their patience, error rate, and chaos factor.
# Compose with fitness_identities.yaml: 20 × 8 = 160 distinct personas.

profiles:
  - id: rage-tapper
    name: "Rage Tapper"
    patience: 0.1          # gives up after ~3s of no response
    error_rate: 0.4        # 40% chance of mistyping or tapping wrong element
    chaos_factor: 0.6      # 60% chance of doing something unexpected when frustrated
    abandonment_rate: 0.5  # 50% chance of quitting a flow mid-way
    habits:
      - rapid_multi_tap    # taps same button 3-5 times rapidly
      - force_close        # closes and reopens when frustrated
      - back_button_spam   # hammers back button
    description: "Frustrated user. Doesn't wait. Taps everything multiple times."

  - id: completionist
    name: "Completionist"
    patience: 0.95
    error_rate: 0.05
    chaos_factor: 0.1
    abandonment_rate: 0.02
    habits:
      - reads_all_text
      - fills_all_optional_fields
      - explores_every_menu
      - checks_settings
    description: "Methodical user. Reads everything. Fills every field. Explores all menus. Best for coverage."

  - id: skipper
    name: "Skipper"
    patience: 0.7
    error_rate: 0.15
    chaos_factor: 0.3
    abandonment_rate: 0.2
    habits:
      - skips_onboarding
      - dismisses_all_modals
      - reads_nothing
      - jumps_to_core_feature
    description: "Skips everything. Never reads tooltips or onboarding. Goes straight to core actions."

  - id: explorer
    name: "Explorer"
    patience: 0.85
    error_rate: 0.2
    chaos_factor: 0.8
    abandonment_rate: 0.15
    habits:
      - taps_every_visible_element
      - tries_unexpected_inputs
      - navigates_non_linearly
      - opens_all_dropdowns
    description: "Curiosity-driven. Taps anything tappable. Finds unexpected UI states nobody thought to test."

  - id: abandoner
    name: "Abandoner"
    patience: 0.6
    error_rate: 0.2
    chaos_factor: 0.4
    abandonment_rate: 0.7  # 70% chance of quitting mid-flow
    habits:
      - quits_mid_form
      - returns_via_back_button
      - reopens_after_abandoning
    description: "High abandonment. Creates partial state everywhere. Critical for testing draft/recovery flows."

  - id: accessibility-user
    name: "Accessibility User"
    patience: 0.8
    error_rate: 0.1
    chaos_factor: 0.1
    abandonment_rate: 0.1
    accessibility_settings:
      large_text: true
      reduce_motion: true
      high_contrast: false
    habits:
      - uses_tab_navigation
      - relies_on_labels
    description: "Uses accessibility features. Tests that the app works with large text and reduced motion."

  - id: bad-network
    name: "Bad Network User"
    patience: 0.5
    error_rate: 0.15
    chaos_factor: 0.3
    abandonment_rate: 0.4
    network_throttle: "3G"   # applies via browser devtools
    habits:
      - retries_on_timeout
      - refreshes_page
      - abandons_on_slow_load
    description: "Poor connectivity. Triggers timeout and retry paths. High abandonment when loads are slow."

  - id: multi-tasker
    name: "Multi-Tasker"
    patience: 0.7
    error_rate: 0.25
    chaos_factor: 0.5
    abandonment_rate: 0.3
    background_frequency: 0.3   # backgrounds/switches away every ~3 actions
    habits:
      - switches_tabs_mid_flow
      - returns_to_different_state
      - opens_multiple_tabs
    description: "Never focuses on one thing. Switches away and returns mid-flow. Destroys session state."
```

**Step 3: Validate YAML**

```bash
python3 -c "
import yaml
ids = yaml.safe_load(open('chaos/personas/fitness_identities.yaml'))
profs = yaml.safe_load(open('chaos/personas/behaviour_profiles.yaml'))
print(f'Identities: {len(ids[\"identities\"])}')
print(f'Profiles: {len(profs[\"profiles\"])}')
print(f'Total personas: {len(ids[\"identities\"]) * len(profs[\"profiles\"])}')
"
```
Expected: `Identities: 20`, `Profiles: 8`, `Total personas: 160`

**Step 4: Commit**

```bash
git add chaos/personas/
git commit -m "feat(AMA-677): add 160-persona library (20 identities × 8 behaviour profiles)"
```

---

## Task 5: Rule-Based Judge

**Files:**
- Create: `chaos/judge/rules.py`
- Create: `chaos/tests/test_judge_rules.py`

**Step 1: Write the failing tests**

```python
# chaos/tests/test_judge_rules.py
import pytest
from chaos.judge.rules import JudgeRules

@pytest.fixture
def judge():
    return JudgeRules()

class TestJudgeWorkout:
    def test_valid_workout_passes(self, judge):
        output = {"sets": 4, "reps": 8, "exercises": ["squat", "bench"], "micro_summary": "Leg day"}
        flags = judge.evaluate_workout(output)
        assert flags == []

    def test_too_many_sets_flagged(self, judge):
        output = {"sets": 15, "reps": 8, "exercises": ["squat"]}
        flags = judge.evaluate_workout(output)
        assert any("sets" in f for f in flags)

    def test_too_many_reps_flagged(self, judge):
        output = {"sets": 3, "reps": 999, "exercises": ["squat"]}
        flags = judge.evaluate_workout(output)
        assert any("reps" in f for f in flags)

    def test_too_many_exercises_flagged(self, judge):
        output = {"sets": 3, "reps": 10, "exercises": [f"ex{i}" for i in range(20)]}
        flags = judge.evaluate_workout(output)
        assert any("exercises" in f for f in flags)

class TestJudgeMicroSummary:
    def test_valid_micro_summary_passes(self, judge):
        flags = judge.evaluate_micro_summary("Short summary under 100 chars")
        assert flags == []

    def test_too_long_micro_summary_fails(self, judge):
        flags = judge.evaluate_micro_summary("x" * 101)
        assert any("micro_summary" in f for f in flags)

    def test_empty_micro_summary_flagged(self, judge):
        flags = judge.evaluate_micro_summary("")
        assert any("empty" in f.lower() for f in flags)

    def test_truncated_mid_word_flagged(self, judge):
        # Ends abruptly without punctuation or space, likely truncated
        flags = judge.evaluate_micro_summary("x" * 100)
        assert any("truncated" in f.lower() for f in flags)

class TestJudgeTagDiscovery:
    def test_valid_tags_pass(self, judge):
        tags = [
            {"name": "squat", "tag_type": "movement_pattern", "confidence": 0.9},
            {"name": "legs", "tag_type": "muscle_group", "confidence": 0.85},
        ]
        flags = judge.evaluate_tags(tags)
        assert flags == []

    def test_invalid_tag_type_flagged(self, judge):
        tags = [{"name": "squat", "tag_type": "invented_type", "confidence": 0.9}]
        flags = judge.evaluate_tags(tags)
        assert any("tag_type" in f for f in flags)

    def test_too_few_tags_flagged(self, judge):
        tags = [{"name": "squat", "tag_type": "movement_pattern", "confidence": 0.9}]
        flags = judge.evaluate_tags(tags)
        assert any("few" in f.lower() for f in flags)

    def test_too_many_tags_flagged(self, judge):
        tags = [{"name": f"tag{i}", "tag_type": "topic", "confidence": 0.8} for i in range(10)]
        flags = judge.evaluate_tags(tags)
        assert any("many" in f.lower() for f in flags)

    def test_low_confidence_flagged(self, judge):
        tags = [{"name": "squat", "tag_type": "movement_pattern", "confidence": 0.2}]
        flags = judge.evaluate_tags(tags)
        assert any("confidence" in f.lower() for f in flags)

class TestJudgeChatResponse:
    def test_on_topic_response_passes(self, judge):
        flags = judge.evaluate_chat_response("Squats are a compound lower-body exercise targeting quads.")
        assert flags == []

    def test_empty_response_flagged(self, judge):
        flags = judge.evaluate_chat_response("")
        assert any("empty" in f.lower() for f in flags)

    def test_very_short_response_flagged(self, judge):
        flags = judge.evaluate_chat_response("Yes.")
        assert any("short" in f.lower() for f in flags)

    def test_hallucinated_extreme_number_flagged(self, judge):
        flags = judge.evaluate_chat_response("You can bench press 500kg in just 3 weeks!")
        assert any("extreme" in f.lower() or "number" in f.lower() for f in flags)
```

**Step 2: Run tests to verify they fail**

```bash
cd /path/to/amakaflow-automation
python3 -m pytest chaos/tests/test_judge_rules.py -v 2>&1 | head -20
```
Expected: `ImportError` or `ModuleNotFoundError` — `chaos.judge.rules` does not exist yet.

**Step 3: Implement rules.py**

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
python3 -m pytest chaos/tests/test_judge_rules.py -v
```
Expected: All tests pass.

**Step 5: Commit**

```bash
git add chaos/judge/rules.py chaos/tests/test_judge_rules.py
git commit -m "feat(AMA-677): add rule-based Judge with full test coverage"
```

---

## Task 6: Garmin Data Emulator

**Files:**
- Create: `chaos/drivers/garmin_emulator.py`
- Create: `chaos/tests/test_garmin_emulator.py`

**Step 1: Write failing tests**

```python
# chaos/tests/test_garmin_emulator.py
import pytest
from unittest.mock import patch, MagicMock
from chaos.drivers.garmin_emulator import GarminEmulator

@pytest.fixture
def emulator():
    return GarminEmulator(ingestor_url="http://localhost:8004")

class TestGarminEmulatorPayloads:
    def test_workout_complete_payload_has_required_fields(self, emulator):
        payload = emulator.build_workout_payload(
            device="fenix_7",
            activity_type="strength",
            duration_seconds=3600,
            heart_rate_avg=130,
        )
        assert "device" in payload
        assert "activity_type" in payload
        assert "duration_seconds" in payload
        assert "heart_rate_avg" in payload
        assert "timestamp" in payload

    def test_zero_duration_payload(self, emulator):
        payload = emulator.build_workout_payload(
            device="fenix_7",
            activity_type="strength",
            duration_seconds=0,
            heart_rate_avg=0,
        )
        assert payload["duration_seconds"] == 0

    def test_extreme_heart_rate_payload(self, emulator):
        payload = emulator.build_workout_payload(
            device="fenix_7",
            activity_type="running",
            duration_seconds=1800,
            heart_rate_avg=240,
        )
        assert payload["heart_rate_avg"] == 240

    def test_corrupt_gps_payload(self, emulator):
        payload = emulator.build_corrupt_gps_payload()
        # GPS in the ocean (not near any gym)
        assert payload["gps_lat"] < -60 or payload["gps_lat"] > 80 \
            or payload["gps_lng"] < -160 or payload["gps_lng"] > 160

    def test_future_timestamp_payload(self, emulator):
        from datetime import datetime, timezone
        payload = emulator.build_future_timestamp_payload()
        ts = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
        assert ts > datetime.now(timezone.utc)

    def test_partial_payload_missing_fields(self, emulator):
        payload = emulator.build_partial_payload()
        # Must be missing at least one normally-required field
        required = {"device", "activity_type", "duration_seconds", "heart_rate_avg"}
        assert len(required - set(payload.keys())) > 0

class TestGarminEmulatorPost:
    @patch("chaos.drivers.garmin_emulator.httpx.post")
    def test_emit_sends_post_request(self, mock_post, emulator):
        mock_post.return_value = MagicMock(status_code=200)
        result = emulator.emit_workout_complete(
            device="fenix_7",
            activity_type="strength",
            duration_seconds=3600,
            heart_rate_avg=130,
        )
        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert "garmin" in call_url

    @patch("chaos.drivers.garmin_emulator.httpx.post")
    def test_emit_chaos_scenario(self, mock_post, emulator):
        mock_post.return_value = MagicMock(status_code=200)
        # All chaos scenarios should not raise
        emulator.emit_zero_duration_workout()
        emulator.emit_duplicate_workout()
        emulator.emit_future_timestamp()
        emulator.emit_extreme_heart_rate()
        emulator.emit_corrupt_gps()
        emulator.emit_partial_payload()
        assert mock_post.call_count == 6
```

**Step 2: Run to verify failure**

```bash
python3 -m pytest chaos/tests/test_garmin_emulator.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError`

**Step 3: Implement garmin_emulator.py**

```python
# chaos/drivers/garmin_emulator.py
"""Garmin data emitter for Phase 1 Chaos Engine.

Mimics the exact JSON payloads the real Garmin companion SDK sends
to the AmakaFlow ingestor API after a workout. No UI automation —
this is a pure data-layer emulator.

Phase 2: Drive the actual Connect IQ simulator via AppleScript.
"""

import httpx
import random
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional


_DEVICES = ["fenix_7", "forerunner_955", "epix_2", "vivoactive_5", "instinct_2"]


class GarminEmulator:
    def __init__(self, ingestor_url: str) -> None:
        self._url = ingestor_url.rstrip("/") + "/garmin/webhook"

    # ── Payload builders ──────────────────────────────────────────────────────

    def build_workout_payload(
        self,
        device: str,
        activity_type: str,
        duration_seconds: int,
        heart_rate_avg: int,
        gps_lat: Optional[float] = None,
        gps_lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        return {
            "device": device,
            "activity_type": activity_type,
            "duration_seconds": duration_seconds,
            "heart_rate_avg": heart_rate_avg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gps_lat": gps_lat,
            "gps_lng": gps_lng,
            "calories": max(0, int(duration_seconds / 60 * 7)),
        }

    def build_corrupt_gps_payload(self) -> Dict[str, Any]:
        payload = self.build_workout_payload(
            device=random.choice(_DEVICES),
            activity_type="running",
            duration_seconds=3600,
            heart_rate_avg=145,
        )
        # Coordinates in the middle of the Pacific Ocean
        payload["gps_lat"] = random.uniform(-80, -60)
        payload["gps_lng"] = random.uniform(-180, -150)
        return payload

    def build_future_timestamp_payload(self) -> Dict[str, Any]:
        payload = self.build_workout_payload(
            device=random.choice(_DEVICES),
            activity_type="strength",
            duration_seconds=3600,
            heart_rate_avg=130,
        )
        payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        return payload

    def build_partial_payload(self) -> Dict[str, Any]:
        full = self.build_workout_payload(
            device=random.choice(_DEVICES),
            activity_type="strength",
            duration_seconds=1800,
            heart_rate_avg=130,
        )
        # Remove a random required field
        key_to_remove = random.choice(["activity_type", "duration_seconds", "heart_rate_avg"])
        del full[key_to_remove]
        return full

    # ── Emit methods ──────────────────────────────────────────────────────────

    def _post(self, payload: Dict[str, Any]) -> httpx.Response:
        return httpx.post(self._url, json=payload, timeout=10.0)

    def emit_workout_complete(
        self,
        device: Optional[str] = None,
        activity_type: str = "strength",
        duration_seconds: int = 3600,
        heart_rate_avg: int = 130,
    ) -> httpx.Response:
        payload = self.build_workout_payload(
            device=device or random.choice(_DEVICES),
            activity_type=activity_type,
            duration_seconds=duration_seconds,
            heart_rate_avg=heart_rate_avg,
        )
        return self._post(payload)

    # ── Chaos scenarios ───────────────────────────────────────────────────────

    def emit_zero_duration_workout(self) -> httpx.Response:
        return self.emit_workout_complete(duration_seconds=0, heart_rate_avg=0)

    def emit_duplicate_workout(self) -> httpx.Response:
        payload = self.build_workout_payload(
            device="fenix_7", activity_type="strength",
            duration_seconds=3600, heart_rate_avg=130,
        )
        self._post(payload)
        return self._post(payload)  # send identical payload twice

    def emit_future_timestamp(self) -> httpx.Response:
        return self._post(self.build_future_timestamp_payload())

    def emit_extreme_heart_rate(self) -> httpx.Response:
        return self.emit_workout_complete(heart_rate_avg=240)

    def emit_corrupt_gps(self) -> httpx.Response:
        return self._post(self.build_corrupt_gps_payload())

    def emit_partial_payload(self) -> httpx.Response:
        return self._post(self.build_partial_payload())
```

**Step 4: Run tests**

```bash
python3 -m pytest chaos/tests/test_garmin_emulator.py -v
```
Expected: All pass.

**Step 5: Commit**

```bash
git add chaos/drivers/garmin_emulator.py chaos/tests/test_garmin_emulator.py
git commit -m "feat(AMA-677): add Garmin data emulator with chaos scenarios"
```

---

## Task 7: Strategist

**Files:**
- Create: `chaos/strategist/strategist.py`
- Create: `chaos/tests/test_strategist.py`

**Step 1: Write failing tests**

```python
# chaos/tests/test_strategist.py
import json
import pytest
import tempfile
from pathlib import Path
from chaos.strategist.strategist import Strategist

@pytest.fixture
def strategist(tmp_path):
    # Minimal state graph for testing
    state_graph = {
        "version": "1.0",
        "surfaces": {
            "web": {
                "screens": ["dashboard", "workout-builder", "kb-cards-list"],
                "ai_features": ["workout-generation"],
                "edge_states": ["empty-form-submit"],
            }
        },
        "explored": {},
        "last_updated": None,
    }
    directives = {
        "version": "1.0",
        "directives": [
            {"id": "explore-freely", "description": "Explore", "weight": 0.5, "applicable_surfaces": ["all"]},
            {"id": "submit-empty-fields", "description": "Submit empty", "weight": 0.8, "applicable_surfaces": ["workout-builder"]},
        ]
    }
    personas = {
        "identities": [{"id": "complete-beginner", "name": "Complete Beginner"}],
        "profiles": [{"id": "explorer", "name": "Explorer", "chaos_factor": 0.8}],
    }
    sg_path = tmp_path / "state_graph.json"
    d_path = tmp_path / "directives.json"
    sg_path.write_text(json.dumps(state_graph))
    d_path.write_text(json.dumps(directives))
    return Strategist(
        state_graph_path=str(sg_path),
        directives_path=str(d_path),
        personas=personas,
    )

class TestStrategistDirective:
    def test_get_directive_returns_dict(self, strategist):
        directive = strategist.get_next_directive()
        assert isinstance(directive, dict)

    def test_directive_has_required_keys(self, strategist):
        directive = strategist.get_next_directive()
        for key in ["platform", "persona_id", "goal", "surface", "chaos_directive", "max_steps"]:
            assert key in directive, f"Missing key: {key}"

    def test_directive_platform_is_web_phase1(self, strategist):
        directive = strategist.get_next_directive()
        assert directive["platform"] == "web"

    def test_directive_surface_is_known_surface(self, strategist):
        directive = strategist.get_next_directive()
        assert directive["surface"] in ["dashboard", "workout-builder", "kb-cards-list",
                                         "workout-generation", "empty-form-submit"]

    def test_unvisited_surface_scores_higher(self, strategist):
        # After marking dashboard as visited, workout-builder should be picked more
        strategist.record_visit("web/dashboard", bugs_found=0)
        # Run many times — workout-builder should appear since it's unvisited
        surfaces = [strategist.get_next_directive()["surface"] for _ in range(20)]
        assert "workout-builder" in surfaces or "kb-cards-list" in surfaces

class TestStrategistMemory:
    def test_record_visit_updates_state_graph(self, strategist):
        strategist.record_visit("web/dashboard", bugs_found=0)
        graph = strategist._load_state_graph()
        assert "web/dashboard" in graph["explored"]
        assert graph["explored"]["web/dashboard"]["visits"] == 1

    def test_record_visit_increments_on_repeat(self, strategist):
        strategist.record_visit("web/dashboard", bugs_found=0)
        strategist.record_visit("web/dashboard", bugs_found=1)
        graph = strategist._load_state_graph()
        assert graph["explored"]["web/dashboard"]["visits"] == 2
        assert graph["explored"]["web/dashboard"]["bugs"] == 1
```

**Step 2: Run to verify failure**

```bash
python3 -m pytest chaos/tests/test_strategist.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError`

**Step 3: Implement strategist.py**

```python
# chaos/strategist/strategist.py
"""Strategist brain for Phase 1 Chaos Engine.

Reads the state graph, scores unexplored surfaces, and outputs
a directive for the Driver. Records visit results back to the graph.
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class Strategist:
    def __init__(
        self,
        state_graph_path: str,
        directives_path: str,
        personas: Dict[str, Any],
        platform: str = "web",
    ) -> None:
        self._sg_path = Path(state_graph_path)
        self._dir_path = Path(directives_path)
        self._personas = personas
        self._platform = platform

    # ── Public API ────────────────────────────────────────────────────────────

    def get_next_directive(self) -> Dict[str, Any]:
        graph = self._load_state_graph()
        surface = self._pick_surface(graph)
        directive = self._pick_chaos_directive(surface)
        persona = self._pick_persona()

        return {
            "platform": self._platform,
            "persona_id": persona["id"],
            "persona_name": persona.get("name", persona["id"]),
            "goal": f"Use the app as {persona.get('name', persona['id'])} would",
            "surface": surface.split("/")[-1] if "/" in surface else surface,
            "chaos_directive": directive["id"],
            "chaos_description": directive["description"],
            "max_steps": 50,
            "frustration_threshold": 5,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def record_visit(self, surface_key: str, bugs_found: int) -> None:
        graph = self._load_state_graph()
        explored = graph.setdefault("explored", {})
        entry = explored.setdefault(surface_key, {"visits": 0, "bugs": 0, "last": None})
        entry["visits"] += 1
        entry["bugs"] += bugs_found
        entry["last"] = datetime.now(timezone.utc).date().isoformat()
        graph["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save_state_graph(graph)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_state_graph(self) -> Dict[str, Any]:
        return json.loads(self._sg_path.read_text())

    def _save_state_graph(self, graph: Dict[str, Any]) -> None:
        self._sg_path.write_text(json.dumps(graph, indent=2))

    def _all_surfaces(self, graph: Dict[str, Any]) -> List[str]:
        platform_data = graph["surfaces"].get(self._platform, {})
        surfaces = []
        for category in ("screens", "ai_features", "edge_states"):
            for name in platform_data.get(category, []):
                surfaces.append(f"{self._platform}/{name}")
        return surfaces

    def _score_surface(self, surface: str, graph: Dict[str, Any]) -> float:
        explored = graph.get("explored", {})
        entry = explored.get(surface, {})
        visits = entry.get("visits", 0)
        bugs = entry.get("bugs", 0)
        last = entry.get("last")

        days_since = 999 if last is None else max(0, (
            datetime.now(timezone.utc).date() -
            datetime.fromisoformat(last).date()
        ).days)

        score = (
            min(days_since, 30) / 30 * 0.4
            + min(bugs, 5) / 5 * 0.3
            + (1.0 if visits == 0 else 0.0) * 0.2
            + random.random() * 0.1
        )
        return score

    def _pick_surface(self, graph: Dict[str, Any]) -> str:
        surfaces = self._all_surfaces(graph)
        if not surfaces:
            return f"{self._platform}/dashboard"
        scored = [(s, self._score_surface(s, graph)) for s in surfaces]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _pick_chaos_directive(self, surface: str) -> Dict[str, Any]:
        directives = json.loads(self._dir_path.read_text())["directives"]
        surface_name = surface.split("/")[-1]
        applicable = [
            d for d in directives
            if "all" in d.get("applicable_surfaces", [])
            or surface_name in d.get("applicable_surfaces", [])
        ]
        if not applicable:
            applicable = directives
        # Weighted random selection
        weights = [d.get("weight", 0.5) for d in applicable]
        return random.choices(applicable, weights=weights, k=1)[0]

    def _pick_persona(self) -> Dict[str, Any]:
        identities = self._personas.get("identities", [])
        profiles = self._personas.get("profiles", [])
        identity = random.choice(identities) if identities else {"id": "default"}
        profile = random.choice(profiles) if profiles else {"id": "explorer"}
        return {
            "id": f"{identity['id']}+{profile['id']}",
            "name": f"{identity.get('name', identity['id'])} / {profile.get('name', profile['id'])}",
            "identity": identity,
            "profile": profile,
        }
```

**Step 4: Run tests**

```bash
python3 -m pytest chaos/tests/test_strategist.py -v
```
Expected: All pass.

**Step 5: Commit**

```bash
git add chaos/strategist/strategist.py chaos/tests/test_strategist.py
git commit -m "feat(AMA-677): add Strategist with scoring, directive selection, memory"
```

---

## Task 8: Bug Reporter

**Files:**
- Create: `chaos/reporting/bug_reporter.py`
- Create: `chaos/tests/test_bug_reporter.py`

**Step 1: Write failing tests**

```python
# chaos/tests/test_bug_reporter.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from chaos.reporting.bug_reporter import BugReporter, BugSeverity

@pytest.fixture
def reporter(tmp_path):
    known_bugs_path = tmp_path / "known_bugs.json"
    known_bugs_path.write_text("{}")
    return BugReporter(
        known_bugs_path=str(known_bugs_path),
        linear_api_key="test-key",
        linear_team_id="test-team",
    )

class TestBugReporterDeduplication:
    def test_new_bug_not_duplicate(self, reporter):
        assert not reporter.is_duplicate("web/dashboard", "crash", ["tap Start", "tap Workout"])

    def test_same_bug_is_duplicate(self, reporter):
        reporter.record_known_bug("web/dashboard", "crash", ["tap Start", "tap Workout"])
        assert reporter.is_duplicate("web/dashboard", "crash", ["tap Start", "tap Workout"])

    def test_different_surface_not_duplicate(self, reporter):
        reporter.record_known_bug("web/dashboard", "crash", ["tap Start"])
        assert not reporter.is_duplicate("web/workout-builder", "crash", ["tap Start"])

    def test_known_bugs_persists_to_file(self, reporter, tmp_path):
        reporter.record_known_bug("web/dashboard", "crash", ["tap Start"])
        data = json.loads((tmp_path / "known_bugs.json").read_text())
        assert len(data) == 1

class TestBugReporterSeverity:
    def test_crash_is_urgent(self, reporter):
        assert reporter.classify_severity("app crashed", "crash") == BugSeverity.URGENT

    def test_data_loss_is_urgent(self, reporter):
        assert reporter.classify_severity("workout data lost", "data_loss") == BugSeverity.URGENT

    def test_visual_bug_is_medium(self, reporter):
        assert reporter.classify_severity("button misaligned", "visual") == BugSeverity.MEDIUM

    def test_ai_quality_is_medium(self, reporter):
        assert reporter.classify_severity("ai response off-topic", "ai_quality") == BugSeverity.MEDIUM

class TestBugReporterTitle:
    def test_title_format(self, reporter):
        title = reporter.build_title(
            persona="Complete Beginner / Explorer",
            surface="workout-builder",
            error_summary="crash on empty submit",
        )
        assert "[CHAOS]" in title
        assert "Complete Beginner" in title
        assert "workout-builder" in title
        assert "crash" in title.lower()
```

**Step 2: Implement bug_reporter.py**

```python
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
```

**Step 3: Run tests**

```bash
python3 -m pytest chaos/tests/test_bug_reporter.py -v
```
Expected: All pass.

**Step 4: Commit**

```bash
git add chaos/reporting/bug_reporter.py chaos/tests/test_bug_reporter.py
git commit -m "feat(AMA-677): add bug reporter with dedup and Linear auto-filing"
```

---

## Task 9: Nightly Digest Formatter

**Files:**
- Create: `chaos/reporting/nightly_digest.py`
- Create: `chaos/tests/test_nightly_digest.py`

**Step 1: Write tests**

```python
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
```

**Step 2: Implement nightly_digest.py**

```python
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
        lines.append("NEW BUGS" if bugs else "NEW BUGS\n  None 🎉")
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
```

**Step 3: Run tests**

```bash
python3 -m pytest chaos/tests/test_nightly_digest.py -v
```
Expected: All pass.

**Step 4: Run full test suite**

```bash
python3 -m pytest chaos/tests/ -v
```
Expected: All tests pass across all modules.

**Step 5: Commit**

```bash
git add chaos/reporting/nightly_digest.py chaos/tests/test_nightly_digest.py
git commit -m "feat(AMA-677): add nightly digest formatter"
```

---

## Task 10: OpenClaw Chaos-Driver Skill

**Files:**
- Create: `chaos/skills/chaos-driver`

This is the system prompt for the Driver — the OpenClaw agent that receives a directive and runs the vision-action loop.

**Step 1: Create the skill file**

```markdown
# Chaos Driver

You are a chaos-driven E2E tester for AmakaFlow. You have been given a directive telling you who to be and what to probe. You must interact with the app exactly as that persona would — using only what you can see on the screen, never relying on internal app knowledge.

## Your Directive

Read the file `chaos/artifacts/current_directive.json` before starting. It contains:
- `persona_name`: Who you are
- `goal`: What you're trying to accomplish
- `surface`: Which part of the app to focus on
- `chaos_directive`: The specific chaos behaviour to inject
- `chaos_description`: What that directive means in practice
- `max_steps`: Maximum actions before stopping
- `frustration_threshold`: How many consecutive failures before giving up

## Rules

1. **You can only see what's on screen.** Take a screenshot before every action. Never assume what button is where.
2. **Be the persona.** A Rage Tapper clicks fast and repeatedly. A Completionist reads every word. An Explorer taps anything tappable.
3. **Inject chaos.** Your directive tells you the chaos to inject. Do it realistically — not obviously malicious, but humanly unexpected.
4. **Flag bugs immediately.** When something looks broken, capture:
   - A screenshot named `chaos/artifacts/screenshots/bug-{timestamp}.png`
   - A JSON entry appended to `chaos/artifacts/current_session_log.jsonl`
5. **Log every action.** After each step, append to `chaos/artifacts/current_session_log.jsonl`:
   ```json
   {"step": N, "action": "description", "result": "what happened", "screen": "screenshot path", "bug_flag": null}
   ```
6. **Log AI outputs.** If you see the app generate a workout, show a KB summary, suggest tags, or respond in chat, capture the output:
   ```json
   {"step": N, "ai_output": true, "feature": "workout-generation", "output": {...}, "screenshot": "path"}
   ```
7. **Stop when**: goal reached, `frustration_threshold` consecutive failures, `max_steps` reached, or critical crash.

## Session Summary

When you finish, write a final summary entry to `chaos/artifacts/current_session_log.jsonl`:
```json
{
  "type": "session_summary",
  "status": "completed|frustrated|crashed|max_steps",
  "actions_taken": N,
  "bugs_found": N,
  "ai_outputs_captured": N,
  "summary": "One paragraph natural language summary of what you did and found"
}
```

## Start

1. Read `chaos/artifacts/current_directive.json`
2. Navigate to: http://localhost:3000
3. Take a screenshot
4. Begin your session as the assigned persona
```

**Step 2: Update openclaw.chaos.json to reference the skill**

The `skills` array in `openclaw.chaos.json` already references `chaos/skills/chaos-driver`. No change needed.

**Step 3: Commit**

```bash
git add chaos/skills/chaos-driver
git commit -m "feat(AMA-677): add chaos-driver OpenClaw skill (vision-action loop prompt)"
```

---

## Task 11: Orchestrator

**Files:**
- Create: `chaos/orchestrator.py`
- Create: `chaos/run_nightly.sh`

**Step 1: Create orchestrator.py**

```python
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
```

**Step 2: Create run_nightly.sh**

```bash
#!/bin/bash
# run_nightly.sh — Chaos Engine nightly runner
# Cron: 0 23 * * * /path/to/amakaflow-automation/chaos/run_nightly.sh >> /tmp/chaos-engine.log 2>&1

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Chaos Engine nightly run: $(date) ==="

# Ensure backend services are up
if ! curl -sf http://localhost:8001/health > /dev/null 2>&1; then
    echo "ERROR: mapper-api not running. Start with: docker compose up -d"
    exit 1
fi

if ! curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo "ERROR: UI not running on localhost:3000"
    exit 1
fi

# Run web session
python3 -m chaos.orchestrator --platform web

echo "=== Chaos Engine run complete: $(date) ==="
```

```bash
chmod +x chaos/run_nightly.sh
```

**Step 3: Test orchestrator dry run**

```bash
cd /path/to/amakaflow-automation
python3 -m chaos.orchestrator --dry-run
```
Expected: Directive printed, no OpenClaw invoked. Output like:
```
[Strategist] Directive: Complete Beginner / Explorer on workout-builder (submit-empty-fields)
[Orchestrator] Dry run — skipping Driver and reporting
```

**Step 4: Commit**

```bash
git add chaos/orchestrator.py chaos/run_nightly.sh
git commit -m "feat(AMA-677): add orchestrator and nightly runner script"
```

---

## Task 12: Install Dependencies + Final Test Run

**Files:**
- Modify: `requirements.txt` (or `pyproject.toml` if present)

**Step 1: Check existing requirements**

```bash
cat requirements.txt 2>/dev/null || cat pyproject.toml 2>/dev/null | head -30
```

**Step 2: Add missing dependencies**

Add to `requirements.txt` (if not already present):
```
httpx>=0.27.0
pyyaml>=6.0
pytest>=8.0
```

**Step 3: Install**

```bash
pip install -r requirements.txt
```

**Step 4: Run full chaos test suite**

```bash
python3 -m pytest chaos/tests/ -v --tb=short
```
Expected: All tests pass. Summary like:
```
chaos/tests/test_judge_rules.py ............  PASSED
chaos/tests/test_garmin_emulator.py ......   PASSED
chaos/tests/test_strategist.py .......       PASSED
chaos/tests/test_bug_reporter.py ........    PASSED
chaos/tests/test_nightly_digest.py ..        PASSED
```

**Step 5: Dry run orchestrator end-to-end**

```bash
python3 -m chaos.orchestrator --dry-run
```
Verify directive is output, state graph is updated, no errors.

**Step 6: Commit**

```bash
git add requirements.txt
git commit -m "feat(AMA-677): Phase 1 Chaos Engine complete — all tests pass"
```

---

## Task 13: Cron Setup

**This is an ops step, not code — do it on the machine running nightly tests.**

**Step 1: Open crontab**

```bash
crontab -e
```

**Step 2: Add entry**

```
# Chaos Engine — nightly at 11pm
0 23 * * * /path/to/amakaflow-automation/chaos/run_nightly.sh >> /tmp/chaos-engine.log 2>&1
```

**Step 3: Verify cron is installed**

```bash
crontab -l | grep chaos
```
Expected: The line you just added.

**Step 4: Test manually (ensure services running first)**

```bash
# Start backend
cd /path/to/amakaflow-dev-workspace && docker compose up -d
# Start UI
cd /path/to/amakaflow-ui && npm run dev &
# Wait a few seconds then run
/path/to/amakaflow-automation/chaos/run_nightly.sh
```
Expected: Full run completes, digest printed to stdout, session log in `chaos/artifacts/logs/`.

---

## Phase 1 Complete

After all tasks, the Chaos Engine Phase 1 is running. Every night at 11pm:

1. Strategist picks the highest-priority unexplored surface
2. Assigns a random persona from the 160-persona library
3. Writes a directive JSON
4. OpenClaw chaos-driver agent navigates the web app as that persona, injecting chaos
5. Judge evaluates any AI outputs from the session
6. Bug reporter deduplicates and auto-files to Linear
7. State graph updated with visit data
8. Nightly digest written to `chaos/artifacts/reports/`

**What Phase 2 unlocks:** Run on dedicated machine, Sonnet Drivers, Haiku Judge, iOS and Android simulators, parallel execution. See `2026-02-19-ama-677-chaos-engine-design.md` for the full expansion roadmap.
