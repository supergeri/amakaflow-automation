# AMA-677: Chaos Engine — Human-Like E2E Testing Design

**Date:** 2026-02-19
**Status:** Approved
**Linear:** [AMA-677](https://linear.app/amakaflow/issue/AMA-677)
**Repo:** `supergeri/amakaflow-automation`

---

## Problem

Current E2E tests are deterministic scripts. A developer imagines a path, writes it down, the agent walks it. These tests can only find bugs the developer already suspected. They are structurally incapable of finding bugs nobody thought of.

Human testers find bugs because they:
- Don't know what the developer intended, so they do unexpected things
- Get confused by the UI and try the "wrong" button
- Abandon mid-flow and come back in a broken state
- Have memory — "last week the sync broke after a background/foreground cycle, let me try that again"
- Notice things feel wrong even when nothing crashes

**Goal:** Build a system that approximates this as closely as possible, eventually replacing the need for a human to manually test every release.

**Core value drivers (in priority order):**
1. **Chaos** — find bugs we haven't imagined by doing things we'd never script
2. **Product validation** — always-on QA that catches regressions in the new-user experience
3. **Regression confidence** — non-linear navigation finds state bugs scripted tests miss

---

## Chosen Architecture: Approach B — Hierarchical Two-Brain System

Three architectural approaches were evaluated. All are documented below so future iterations can switch approaches at any layer.

### Approach A — Pure Vision Chaos Loop *(documented for future use)*
Every action: screenshot → LLM views screen cold (no context) → decides next action → execute → repeat. Zero structure. Maximum chaos. Finds the most surprising bugs but no coverage guarantees — tends to re-find popular-screen bugs while missing obscure surfaces. Most expensive per action. **Use as a mode within B, not as a replacement.**

Toggle: set `strategist: null` in `openclaw.chaos.json` and `max_chaos: 1.0`.

### Approach B — Hierarchical Two-Brain *(chosen)*
Strategist (plans, tracks coverage, directs chaos) + Driver (executes vision-action loop with persona) + Judge (evaluates AI output quality). Systematic coverage + genuine chaos + cross-session memory + AI evaluation. All three brains are swappable — the interface contracts are documented below.

### Approach C — Persona Swarm *(documented for future use)*
8+ fixed personas running in parallel, each with their own memory, no central Strategist. Great narrative ("the Beginner got confused here") and naturally parallel. But coverage is persona-constrained and no systematic guarantee every surface is hit.

Toggle: replace Strategist with parallel persona configs in `openclaw.chaos.json`, set `coordinator: null`.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CHAOS ENGINE                            │
│                                                             │
│  ┌──────────────┐    directives    ┌──────────────────────┐ │
│  │  STRATEGIST  │ ──────────────► │      DRIVER(S)       │ │
│  │  (see model  │                 │  (vision-action loop) │ │
│  │   routing)   │ ◄────────────── │                      │ │
│  │              │   session logs  │                      │ │
│  └──────┬───────┘                 └──────────┬───────────┘ │
│         │                                    │             │
│         │ reads/writes                       │ AI outputs  │
│         ▼                                    ▼             │
│  ┌──────────────┐                 ┌──────────────────────┐ │
│  │  STATE GRAPH │                 │       JUDGE          │ │
│  │  + MEMORY    │                 │  evaluates AI quality│ │
│  │  (JSON/MD)   │                 └──────────────────────┘ │
│  └──────────────┘                                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              DEVICE ABSTRACTION LAYER               │   │
│  │  Web │ iOS │ Android │ watchOS │ Garmin │ [Future]  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Runtime model:** The Strategist wakes once per session (or on a schedule). It reads the state graph, scores surfaces, picks the highest-value unexplored territory, assigns a persona + goal + chaos level to a Driver, then sleeps. The Driver runs the vision-action loop until it completes, crashes, or hits its frustration threshold. Results feed back into the state graph. In Phase 2+, multiple Drivers run in parallel on different platforms.

---

## Model Routing (Phase-Dependent)

### Phase 1 — Same machine, cost-conscious (NOW)
```yaml
strategist: claude-haiku-4-5-20251001
driver:     claude-haiku-4-5-20251001
judge:      rule-based (LLM escalation only on ambiguous outputs)
parallel:   false
schedule:   "0 23 * * *"   # nightly 11pm, done before David starts
simulators: sequential      # iOS → Android → Garmin, never simultaneously
```

### Phase 2 — Dedicated machine, post-revenue
```yaml
strategist: claude-opus-4-6
driver:     claude-sonnet-4-6
judge:      claude-haiku-4-5-20251001
parallel:   true            # 3-4 Drivers simultaneously
schedule:   continuous
machine:    dedicated Mac Mini M4 (~$600 hardware)
```

### Phase 3 — Multi-machine swarm
```yaml
# Machine A: Strategist + web Drivers
# Machine B: iOS + watchOS Drivers
# Machine C: Android + Garmin Drivers
# Full 160-persona rotation, ~7-day full cycle
```

Config lives in `openclaw.chaos.json` — separate from the coding agent's `openclaw.json`. Only the model routing changes between phases. All driver/strategist/judge logic is identical.

---

## The Strategist

### Responsibility
Knows the entire app. Tracks what's been explored. Decides where the next Driver goes and with what persona + chaos level. Maintains cross-session memory.

### State Graph (`chaos/state_graph.json`)

```json
{
  "surfaces": {
    "web": {
      "screens": ["dashboard", "workout-builder", "kb-cards", "kb-detail",
                  "chat", "settings", "instagram-import", "profile"],
      "ai_features": ["workout-generation", "kb-summarise", "kb-tag-discover",
                      "kb-relationships", "chat-response-quality"],
      "edge_states": ["empty-state", "error-state", "loading-timeout",
                      "concurrent-edit", "session-expiry-mid-flow"]
    },
    "ios": { "screens": [...], "ai_features": [...], "edge_states": [...] },
    "android": { "screens": [...], "ai_features": [...], "edge_states": [...] },
    "garmin": { "screens": [...], "data_events": ["sync", "mid-workout-disconnect",
                "duplicate-workout", "corrupt-gps", "extreme-heart-rate"] },
    "watchos": { "screens": [...] }
  },
  "explored": {
    "web/dashboard": { "visits": 14, "last": "2026-02-19", "bugs": ["AMA-BUG-003"] },
    "web/kb-detail":  { "visits": 2,  "last": "2026-02-17", "bugs": [] },
    "garmin/sync-mid-workout": { "visits": 0, "last": null, "bugs": [] }
  },
  "chaos_directives": [
    "background-app-mid-sync",
    "rapid-tap-before-load-completes",
    "submit-empty-fields",
    "rotate-device-mid-flow",
    "kill-network-during-ai-request",
    "concurrent-sessions-same-user",
    "send-malformed-workout-data-from-garmin",
    "exceed-kb-card-content-length",
    "spam-chat-with-nonsense",
    "log-workout-with-zero-reps",
    "log-workout-with-9999-reps",
    "submit-form-during-network-loss",
    "force-close-during-sync",
    "change-locale-mid-session",
    "deny-all-permissions-mid-onboarding"
  ]
}
```

### Prioritisation Formula

```
score = (days_since_last_visit  × 0.4)
      + (bug_density_nearby     × 0.3)   # re-probe surfaces near known bugs
      + (chaos_directive_weight × 0.2)   # high-risk directives score higher
      + (random_noise           × 0.1)   # never fully settles into a rut
```

Highest score gets the next Driver session. Unvisited surfaces accumulate score over time and eventually get explored. The 10% noise means the Strategist occasionally explores something unexpected — exactly like a real QA lead.

### Strategist Interface Contract
```
INPUT:  state_graph.json, memory/personas/*.md, last N session logs
OUTPUT: {
  platform:       "ios",
  persona:        "elderly-beginner+rage-tapper",
  goal:           "try to log a strength workout",
  surface:        "workout-builder",
  chaos_directive: "submit-empty-fields",
  max_steps:      50,
  frustration_threshold: 5   # give up after 5 consecutive failures
}
```

---

## The Driver

### The Vision-Action Loop

**Key principle:** The Driver is given the persona prompt and goal — not the app structure. It does not know button IDs, screen names, or navigation paths. It sees pixels and decides, exactly like a real user.

```
┌─────────────────────────────────────────────────────┐
│  1. SCREENSHOT  →  raw pixel view of current state  │
│         │                                           │
│  2. LLM SEES IT  (no accessibility tree,            │
│     no element IDs — only what a human sees)        │
│         │                                           │
│  3. DECISION  →  next_action output:                │
│     {                                               │
│       action: "tap",                                │
│       target: "the blue button that says            │
│               Start Workout",                       │
│       reasoning: "that's what I'd press next",      │
│       chaos_roll: 0.12                              │
│     }                                               │
│     if chaos_roll < persona.chaos_factor:           │
│       do something unexpected instead               │
│         │                                           │
│  4. EXECUTE  →  Device Abstraction Layer            │
│         │                                           │
│  5. BUG DETECTION                                   │
│     • crash signal (app killed / JS error)          │
│     • hang (>threshold ms with no screen change)    │
│     • error UI (red/warning state detected)         │
│     • AI output (route to Judge)                    │
│         │                                           │
│  6. LOG → append to session_log.jsonl               │
│         │                                           │
│  7. TERMINATION CHECK                               │
│     • goal reached?                                 │
│     • frustration_threshold hit?                    │
│     • max_steps hit?                                │
│     • critical crash?                               │
│         │                                           │
│  └──────► loop or terminate ────────────────────────┘
```

### Driver Interface Contract
```
INPUT:  Strategist directive (platform, persona, goal, chaos_directive, max_steps)
OUTPUT: {
  status:        "completed" | "frustrated" | "crashed" | "max_steps",
  actions_taken: [...],         # full replay log
  bugs_found:    [...],
  ai_outputs:    [...],         # routed to Judge
  final_screenshot: "path/to/final.png",
  summary:       "natural language summary of the session"
}
```

---

## The Persona Library

Personas compose from two axes: **fitness identity** (who they are) × **behaviour profile** (how they act). 20 identities × 8 profiles = **160 distinct personas**.

### Fitness Identities (20)

| Persona | Primary Device | Goals | Tech Savvy |
|---|---|---|---|
| Complete Beginner | iPhone | lose weight | none |
| Casual Gym-Goer | iPhone + Apple Watch | consistency | low |
| Serious Powerlifter | Android + Garmin | PRs, periodisation | high |
| Marathon Runner | Garmin | zone 2, mileage | high |
| HYROX Competitor | Garmin + Apple Watch | race prep | high |
| Triathlete | Garmin | multi-sport logging | expert |
| Cyclist | Garmin + Android | FTP, watts | expert |
| CrossFitter | iPhone | WOD, benchmarks | medium |
| Bodybuilder | Android | hypertrophy, macros | medium |
| Yoga/Mobility Focused | iPhone | recovery, HRV | low |
| Elderly User (65+) | iPhone (large text) | health, steps | very low |
| Rehab/Injury Recovery | iPhone | physio exercises | low |
| Personal Trainer | web + iPhone | client management | expert |
| Group Fitness Coach | iPad/web | class planning | medium |
| Weight Loss Journey | Android | calories, progress | low |
| Teen Athlete | iPhone | sport performance | low |
| Nutrition-Obsessed | web | macros, logging | high |
| Data Hoarder | Garmin + all devices | export everything | expert |
| Wearable Skeptic | no watch | manual logging | low |
| Privacy Paranoid | iPhone | denies all permissions | varies |

### Behaviour Profiles (8)

```yaml
rage_tapper:
  patience: 0.1           # gives up in <3s
  error_rate: 0.4         # frequent misfires
  chaos_factor: 0.6       # tries random things when frustrated
  habits: [rapid_multi_tap, force_close, reopen]

completionist:
  patience: 0.9
  error_rate: 0.05
  explores_every_menu: true
  reads_all_text: true
  chaos_factor: 0.1

skipper:
  patience: 0.7
  reads_nothing: true
  skips_all_onboarding: true
  chaos_factor: 0.3

explorer:
  patience: 0.8
  taps_everything: true    # any visible element is fair game
  chaos_factor: 0.8

abandoner:
  abandonment_rate: 0.6    # 60% chance of quitting mid-flow
  returns_later: true      # comes back in a different state
  chaos_factor: 0.4

accessibility_user:
  voiceover: true
  large_text: true
  reduce_motion: true
  chaos_factor: 0.1

bad_network:
  network_profile: "3G"
  retries_on_failure: true
  chaos_factor: 0.2

multi_tasker:
  background_frequency: 0.3  # backgrounds app every ~3 actions
  switches_to: [messages, safari, camera]
  chaos_factor: 0.5
```

### Persona Memory (`chaos/memory/personas/<name>.md`)
A running narrative log per persona across sessions: what they've discovered, what confused them, what they tried repeatedly. The Strategist reads this before each directive to avoid re-filing known bugs and to escalate surfaces where a persona has repeatedly failed.

---

## The Judge

Evaluates every AI output the Driver encounters. Not just "did a response arrive" — evaluates actual quality.

### What the Judge Evaluates

| AI Feature | Judge Checks |
|---|---|
| Workout generation | Exercises appropriate for stated goal/level? Sets/reps/rest sensible? No dangerous combinations for beginners? |
| KB card summarise | Summary captures main idea? micro_summary ≤100 chars AND meaningful (not truncated mid-word)? Takeaways actionable? |
| KB tag discovery | Tags relevant to content? No hallucinated tag types? Confidence scores reasonable? |
| KB relationships | Suggested related cards actually related? No spurious connections? |
| Chat responses | On-topic for fitness domain? Factually plausible? Not hallucinating specific numbers? |

### Phase 1 Judge — Rule-Based (zero LLM cost)

```python
def judge_workout(output):
    flags = []
    if output.get("sets", 0) > 10:
        flags.append("SUSPECT: >10 sets")
    if output.get("reps", 0) > 50:
        flags.append("SUSPECT: >50 reps")
    if len(output.get("micro_summary", "")) > 100:
        flags.append("FAIL: micro_summary exceeds 100 chars")
    if output.get("exercises") and len(output["exercises"]) > 15:
        flags.append("SUSPECT: >15 exercises in one workout")
    return flags
```

LLM escalation (Haiku) only when heuristics flag something ambiguous.

### Phase 2 Judge — LLM Scorer
Every AI output scored 1–5 on relevance, safety, and coherence. Scores <3 auto-file a bug. Score of 1 sends immediate Slack alert to David.

### Judge Interface Contract
```
INPUT:  { feature: "workout-generation", output: {...}, persona_context: {...} }
OUTPUT: { score: 4.2, flags: [], verdict: "pass" | "warn" | "fail", reason: "..." }
```

Judge scores feed the Strategist's memory — if quality degrades after a deploy, the Strategist increases Driver focus on that surface.

---

## Device Abstraction Layer

Every platform speaks the same interface to the Driver:

```python
class DeviceAbstractionLayer:
    def tap(self, target: str): ...       # natural language target
    def type(self, target: str, text: str): ...
    def swipe(self, direction: str): ...
    def screenshot(self) -> bytes: ...
    def background_app(self): ...
    def foreground_app(self): ...
    def inject_data(self, payload: dict): ...  # for Garmin/wearable emulators

# Platform implementations:
class WebDriver(DeviceAbstractionLayer):
    # playwright.click() / fill() / screenshot()

class iOSDriver(DeviceAbstractionLayer):
    # maestro tap / type / screenshot via exec

class AndroidDriver(DeviceAbstractionLayer):
    # maestro tap / type / screenshot via exec

class GarminDriver(DeviceAbstractionLayer):
    # Phase 1: data emitter (see below)
    # Phase 2: Connect IQ simulator via AppleScript

class WearOSDriver(DeviceAbstractionLayer):
    # ADB shell input + screencap
```

### Garmin Custom Emulator — Phase 1 (Data Layer)

Garmin's UI simulator is hard to automate headlessly. Phase 1 emulates the data layer — injects the exact JSON packets the real Garmin companion SDK produces.

```python
class GarminEmulator:
    """Mimics the exact data format the Garmin companion app sends
    to the AmakaFlow backend after a workout completes."""

    def emit_workout_complete(self, persona):
        payload = {
            "device": random.choice(["fenix_7", "forerunner_955", "epix_2"]),
            "activity_type": persona.workout_type,
            "duration_seconds": random.randint(1200, 5400),
            "heart_rate_avg": persona.typical_hr,
            "gps_track": self._generate_gps(persona),
            "timestamp": self._maybe_corrupt_timestamp(),  # chaos injection
            "sets": self._maybe_send_partial_data(persona) # chaos injection
        }
        requests.post(f"{INGESTOR_API_URL}/garmin/webhook", json=payload)

    # Chaos scenarios — things we'd never think to script manually:
    def emit_mid_workout_disconnect(self):   ...  # sync stops 40% through
    def emit_duplicate_workout(self):        ...  # same workout sent twice
    def emit_zero_duration_workout(self):    ...  # 0 second activity
    def emit_future_timestamp(self):         ...  # timestamp is tomorrow
    def emit_corrupt_gps(self):              ...  # coordinates in the ocean
    def emit_extreme_heart_rate(self):       ...  # 240 BPM
    def emit_partial_payload(self):          ...  # missing required fields
```

### Future Wearables

Every new wearable = one new class implementing `DeviceAbstractionLayer`. The DAL maps every device to the same `emit_workout`, `emit_heart_rate`, `emit_sleep` interface.

Planned wearable adapters (priority order):
1. Apple Watch (Phase 2 — UI-driven via watchOS simulator)
2. Wear OS (ADB + UIAutomator)
3. Fitbit (webhook emulator)
4. Polar (API emulator)
5. Whoop (API emulator)
6. Oura (API emulator)
7. Amazfit (API emulator)

---

## Bug Reporting Pipeline

```
1. CAPTURE
   • Screenshot of the broken state
   • Last 20 actions (the "how I got here" replay log)
   • Device logs (crash logs, console errors, API responses)
   • Persona + directive that triggered it

2. DEDUPLICATE
   • Hash the bug signature (screen + error type + last 3 actions)
   • Check chaos/memory/known_bugs.json for matching hash
   • If duplicate: increment occurrence count, do not re-file

3. AUTO-FILE TO LINEAR
   {
     title:       "[CHAOS] {persona} broke {surface}: {error_summary}",
     description: full report with replay steps,
     labels:      ["chaos-engine", "bug"],
     priority:    crash=1, data-loss=1, visual=3, AI-quality=3
   }

4. NOTIFY
   • Critical (crash / data loss): immediate Slack ping to David
   • Normal: included in nightly digest
   • AI quality degradation: trend alert if >3 in one session
```

### Nightly Digest Format

```
🤖 Chaos Engine — 2026-02-20

Personas run: 8  |  Actions: 847  |  Bugs filed: 3  |  Duplicates suppressed: 12

NEW BUGS
• [AMA-BUG-041] Rage Tapper + iOS: workout logger crashes on 0-rep submit [CRASH]
• [AMA-BUG-042] Abandoner + web: KB card edit leaves orphaned draft on return [MEDIUM]
• [AMA-BUG-043] Data Hoarder + Garmin: duplicate workout filed when sync retries [MEDIUM]

AI QUALITY (avg this session)
• Workout generation:   4.2/5 ✅
• KB summarise:         3.8/5 ✅
• Chat responses:       2.9/5 ⚠️ (trending down — 3 off-topic responses)

SURFACES HIT:    dashboard, workout-log, kb-cards, kb-detail, chat, garmin-sync
SURFACES MISSED: settings, instagram-import (queued for tomorrow)

Full report: chaos/artifacts/reports/2026-02-20-nightly.json
```

---

## Infrastructure

### Phase 1 — Same Machine (now)
- Same Mac as Joshua's coding tasks
- Simulators run sequentially, never simultaneously
- Nightly schedule (11pm, done by 7am)
- All chaos artifacts in `chaos/artifacts/`

### Phase 2 — Dedicated Machine (post-revenue)
- Dedicated Mac Mini M4 (~$600)
- All simulators always warm and running
- 3–4 Drivers running in parallel
- Continuous testing, 24/7

### Directory Structure
```
amakaflow-automation/
  openclaw.chaos.json          # Chaos Engine OpenClaw config (separate from coding)
  chaos/
    strategist/
      state_graph.json         # Living map of all app surfaces + explored status
      directives.json          # Chaos directive library
    personas/
      fitness_identities.yaml  # 20 fitness identities
      behaviour_profiles.yaml  # 8 behaviour profiles
    memory/
      personas/                # Per-persona cross-session memory logs
        elderly-beginner.md
        serious-powerlifter.md
        ...
      known_bugs.json          # Deduplication hash store
    drivers/
      web_driver.py
      ios_driver.py
      android_driver.py
      garmin_emulator.py
      wearos_driver.py
    judge/
      rules.py                 # Phase 1: heuristic evaluation
      llm_judge.py             # Phase 2: Haiku-based scorer
    artifacts/
      screenshots/
      logs/
      reports/
```

---

## Expansion Roadmap

```
Phase 1 — Same machine, Haiku, nightly (BUILD NOW)
  ✓ 20 personas, sequential, one platform/night
  ✓ Garmin = data emitter only
  ✓ Judge = heuristics (rule-based)
  ✓ State graph hand-seeded
  ✓ Bug reports auto-filed to Linear

Phase 2 — Dedicated machine, Sonnet, continuous (post-revenue)
  ✓ 160 personas (20 identities × 8 behaviour profiles)
  ✓ All simulators simultaneously
  ✓ Judge = Haiku LLM evaluation
  ✓ Garmin = UI simulator driven via AppleScript
  ✓ Approach C (persona swarm) available as a mode

Phase 3 — Multi-machine swarm (scale)
  ✓ Approach A (pure chaos) running alongside B
  ✓ State graph self-discovers new screens via exploration Drivers
  ✓ All 7 wearable adapters implemented
  ✓ Full 160-persona rotation in ~7 days continuous
```

### Switching Approaches

All three approaches are implemented as modes in `openclaw.chaos.json`:

```json
{
  "mode": "B",            // "A" = pure chaos, "B" = hierarchical, "C" = persona swarm
  "strategist": { ... },  // null for Approach A
  "coordinator": { ... }, // null for Approach C (replaced by parallel persona configs)
  "drivers": { ... },
  "judge": { ... }
}
```

---

## Related Tickets

- AMA-524: SPIKE — Automatic Workout Detection via Wearable Sensors
- AMA-525: SPIKE — Real-time Form Feedback Using Wearable Motion Sensors
- AMA-537: Capture middleware for replay test harness (already merged — feeds Driver replay log)
- AMA-617: Validation gate composite GitHub Action (already merged — CI integration point)
