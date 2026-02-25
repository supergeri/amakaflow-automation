#!/usr/bin/env python3
"""
Workout Import QA — automated pipeline quality testing.

Tests the AmakaFlow ingestor against real workout URLs and documents
what's captured correctly vs. what's wrong or missing.

Modes:
  Default (API):  Calls POST /ingest/url directly. Fast, structured JSON output.
  UI mode (--ui): Drives the web app via Playwright, screenshots each result,
                  uses Kimi vision to judge quality.

Assisted process (--assist):
  After a run, loads failures/uncertain results and walks through them
  interactively so you can label expected values for fix tickets.

Usage:
    # API mode (fast, default)
    python scripts/workout_import_qa.py

    # UI mode (visual, uses Playwright + Kimi vision)
    python scripts/workout_import_qa.py --ui

    # Test a single URL
    python scripts/workout_import_qa.py --url https://youtube.com/watch?v=abc

    # Interactive review of failures from last run
    python scripts/workout_import_qa.py --assist

    # Harvest fresh URLs then run QA
    python scripts/workout_import_qa.py --harvest

    # Filter to one platform
    python scripts/workout_import_qa.py --platform youtube
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

REPO_ROOT = Path(__file__).parent.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
SEEDS_FILE = REPO_ROOT / "fixtures" / "workout-qa-urls.json"

INGESTOR_BASE_URL = os.environ.get("INGESTOR_BASE_URL", "http://localhost:8004")
UI_BASE_URL = os.environ.get("UI_BASE_URL", "http://localhost:3000")
DEFAULT_TIMEOUT = int(os.environ.get("QA_TIMEOUT", "90"))

# Result status values
STATUS_OK = "ok"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"
STATUS_FETCH_ERROR = "fetch_error"
STATUS_PARSE_ERROR = "parse_error"
STATUS_UNSUPPORTED = "unsupported_platform"
STATUS_TIMEOUT = "timeout"
STATUS_SERVICE_DOWN = "service_down"
STATUS_IMPORT_FAILED = "import_failed"  # UI mode only


# ---------------------------------------------------------------------------
# Pure functions (unit-testable)
# ---------------------------------------------------------------------------

def classify_api_response(http_status: int, body: dict) -> str:
    """Map an HTTP status + body to a QA result status."""
    if http_status == 200:
        if body.get("needs_clarification"):
            return STATUS_NEEDS_CLARIFICATION
        return STATUS_OK
    if http_status == 400:
        detail = body.get("detail", "")
        if "Unsupported URL" in detail or "No adapter" in detail:
            return STATUS_UNSUPPORTED
        return STATUS_PARSE_ERROR
    if http_status == 422:
        return STATUS_PARSE_ERROR
    if http_status == 502:
        return STATUS_FETCH_ERROR
    return f"http_{http_status}"


def extract_fields(body: dict) -> dict:
    """Pull the key QA fields out of a Workout response dict."""
    blocks = body.get("blocks", [])
    structures = [b.get("structure") for b in blocks]
    rounds = [b.get("rounds") for b in blocks if b.get("rounds")]
    rest_times = [b.get("rest_between_seconds") for b in blocks if b.get("rest_between_seconds")]
    exercise_names = [
        ex.get("name", "")
        for b in blocks
        for ex in b.get("exercises", [])
    ]
    confidences = [b.get("structure_confidence") for b in blocks if b.get("structure_confidence") is not None]

    return {
        "structures": structures,
        "rounds": rounds,
        "rest_between_seconds": rest_times,
        "exercise_count": len(exercise_names),
        "exercise_names": exercise_names[:10],  # cap for readability
        "needs_clarification": body.get("needs_clarification", False),
        "min_confidence": min(confidences, default=None),
    }


def check_expected(fields: dict, expected: dict) -> list[str]:
    """Compare extracted fields against expected values. Returns list of mismatches."""
    mismatches = []

    expected_structure = expected.get("structure")
    if expected_structure and expected_structure not in ("ambiguous", "multi_block"):
        if not any(s == expected_structure for s in fields["structures"]):
            actual = fields["structures"]
            mismatches.append(f"Expected structure={expected_structure!r}, got {actual}")

    if expected.get("rounds") and expected["rounds"] not in fields["rounds"]:
        mismatches.append(f"Expected rounds={expected['rounds']}, got {fields['rounds']}")

    return mismatches


def build_report(results: list[dict], run_date: str, mode: str = "api") -> str:
    """Build Markdown QA report from result list."""
    total = len(results)
    ok = sum(1 for r in results if r["status"] == STATUS_OK)
    clarification = sum(1 for r in results if r["status"] == STATUS_NEEDS_CLARIFICATION)
    failed = sum(1 for r in results if r["status"] not in (STATUS_OK, STATUS_NEEDS_CLARIFICATION))

    lines = [
        f"# Workout Import QA — {run_date}",
        f"*Mode: {mode}*",
        "",
        "## Summary",
        f"- **Total:** {total} | ✅ OK: {ok} | ⚠️ Needs clarification: {clarification} | ❌ Failed: {failed}",
        "",
    ]

    # Per-platform breakdown
    platforms = {}
    for r in results:
        p = r.get("platform", "unknown")
        platforms.setdefault(p, {"ok": 0, "clarification": 0, "failed": 0})
        if r["status"] == STATUS_OK:
            platforms[p]["ok"] += 1
        elif r["status"] == STATUS_NEEDS_CLARIFICATION:
            platforms[p]["clarification"] += 1
        else:
            platforms[p]["failed"] += 1

    lines.append("## By Platform")
    lines.append("")
    lines.append("| Platform | ✅ OK | ⚠️ Clarification | ❌ Failed |")
    lines.append("|----------|------|-----------------|----------|")
    for platform, counts in sorted(platforms.items()):
        lines.append(f"| {platform} | {counts['ok']} | {counts['clarification']} | {counts['failed']} |")
    lines.append("")

    # Per-workout-type breakdown
    wtypes = {}
    for r in results:
        wt = r.get("workout_type", "unknown")
        wtypes.setdefault(wt, [])
        wtypes[wt].append(r["status"])

    lines.append("## By Workout Type")
    lines.append("")
    lines.append("| Type | Result |")
    lines.append("|------|--------|")
    for wtype, statuses in sorted(wtypes.items()):
        icons = " ".join("✅" if s == STATUS_OK else ("⚠️" if s == STATUS_NEEDS_CLARIFICATION else "❌") for s in statuses)
        lines.append(f"| {wtype} | {icons} |")
    lines.append("")

    lines.append("## Results")
    lines.append("")

    for r in results:
        status = r["status"]
        if status == STATUS_OK:
            icon = "✅"
        elif status == STATUS_NEEDS_CLARIFICATION:
            icon = "⚠️"
        else:
            icon = "❌"

        lines.append(f"### {icon} [{r.get('workout_type', 'unknown')}] {r.get('platform', '')} — {r.get('description', '')}")
        lines.append(f"**URL:** {r['url']}")
        lines.append(f"**Status:** `{status}`")

        if r.get("latency_ms"):
            lines.append(f"**Latency:** {r['latency_ms']}ms")

        if r.get("fields"):
            f = r["fields"]
            lines.append(f"**Structures:** {f['structures']}")
            if f["rounds"]:
                lines.append(f"**Rounds:** {f['rounds']}")
            if f["rest_between_seconds"]:
                lines.append(f"**Rest:** {f['rest_between_seconds']}s")
            lines.append(f"**Exercises:** {f['exercise_count']} ({', '.join(f['exercise_names'][:5])}{'...' if f['exercise_count'] > 5 else ''})")
            if f["min_confidence"] is not None:
                lines.append(f"**Min confidence:** {f['min_confidence']:.2f}")

        if r.get("mismatches"):
            lines.append("**Mismatches:**")
            for m in r["mismatches"]:
                lines.append(f"- ⚠️ {m}")

        if r.get("error"):
            lines.append(f"**Error:** {r['error']}")

        if r.get("screenshot_path"):
            lines.append(f"**Screenshot:** {r['screenshot_path']}")

        if r.get("findings"):
            lines.append("**Visual findings:**")
            for finding in r["findings"]:
                lines.append(f"- {finding}")

        lines.append("")

    # Patterns section — aggregate observations
    all_mismatches = [m for r in results for m in r.get("mismatches", [])]
    parse_errors = [r for r in results if r["status"] == STATUS_PARSE_ERROR]
    unsupported = [r for r in results if r["status"] == STATUS_UNSUPPORTED]

    if all_mismatches or parse_errors or unsupported:
        lines.append("## Patterns / Action Items")
        lines.append("")
        if parse_errors:
            lines.append(f"- **{len(parse_errors)} parse failures** — LLM could not extract workout structure")
        if unsupported:
            lines.append(f"- **{len(unsupported)} unsupported URLs** — URL pattern not registered (see AMA-750)")
        if all_mismatches:
            lines.append(f"- **{len(all_mismatches)} field mismatches** vs expected values:")
            for m in all_mismatches[:10]:
                lines.append(f"  - {m}")
        lines.append("")

    return "\n".join(lines)


def set_has_issues_output(results: list[dict]) -> None:
    """Write GitHub Actions output variable `has_issues`."""
    has_issues = any(r["status"] != STATUS_OK for r in results)
    value = "true" if has_issues else "false"
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_issues={value}\n")
    else:
        print(f"[qa] has_issues={value}")


def parse_kimi_response(raw: str) -> dict:
    """Parse Kimi vision JSON response into normalised dict."""
    try:
        data = json.loads(raw)
        return {
            "status": data.get("status", "ok"),
            "findings": data.get("findings", []),
        }
    except (json.JSONDecodeError, AttributeError) as e:
        return {
            "status": "parse_error",
            "findings": [f"Could not parse Kimi response: {e}. Raw: {raw[:200]}"],
        }


# ---------------------------------------------------------------------------
# API mode: call ingestor directly
# ---------------------------------------------------------------------------

def ingest_via_api(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Call POST /ingest/youtube for YouTube URLs, /ingest/url for everything else."""
    start = time.monotonic()
    is_youtube = "youtube.com" in url or "youtu.be" in url
    endpoint = "/ingest/youtube" if is_youtube else "/ingest/url"
    try:
        resp = httpx.post(
            f"{INGESTOR_BASE_URL}{endpoint}",
            json={"url": url, "user_id": "qa-bot"},
            timeout=timeout,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass

        status = classify_api_response(resp.status_code, body)
        fields = extract_fields(body) if resp.status_code == 200 else {}
        error = body.get("detail") if resp.status_code != 200 else None

        return {
            "status": status,
            "fields": fields,
            "error": error,
            "http_status": resp.status_code,
            "latency_ms": latency_ms,
            "raw_response": body if resp.status_code != 200 else None,
        }

    except httpx.TimeoutException:
        return {"status": STATUS_TIMEOUT, "error": f"No response within {timeout}s", "fields": {}}
    except httpx.ConnectError:
        return {"status": STATUS_SERVICE_DOWN, "error": f"Cannot connect to {INGESTOR_BASE_URL}", "fields": {}}


def run_api_mode(
    url_entries: list[dict],
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Run QA in API mode — fast, structured, no browser needed."""
    results = []

    for entry in url_entries:
        url = entry["url"]
        platform = entry.get("platform", "unknown")
        workout_type = entry.get("workout_type", "unknown")
        description = entry.get("description", "")
        expected = entry.get("expected", {})

        print(f"  [{workout_type}] {platform}: {url[:80]}", end=" ... ", flush=True)
        result = ingest_via_api(url, timeout=timeout)

        mismatches = check_expected(result.get("fields", {}), expected) if result["fields"] else []

        icon = "✅" if result["status"] == STATUS_OK and not mismatches else (
            "⚠️" if result["status"] == STATUS_NEEDS_CLARIFICATION else "❌"
        )
        latency = f"{result.get('latency_ms', 0)}ms"
        print(f"{icon} {result['status']} ({latency})")

        if mismatches:
            for m in mismatches:
                print(f"    ⚠️  {m}")

        results.append({
            "url": url,
            "platform": platform,
            "workout_type": workout_type,
            "description": description,
            "expected": expected,
            "status": result["status"],
            "fields": result.get("fields", {}),
            "mismatches": mismatches,
            "error": result.get("error"),
            "http_status": result.get("http_status"),
            "latency_ms": result.get("latency_ms"),
        })

    return results


# ---------------------------------------------------------------------------
# UI mode: Playwright + Kimi vision
# ---------------------------------------------------------------------------

def judge_screenshot(screenshot_path: Path, description: str, platform: str, kimi_api_key: str) -> dict:
    """Send screenshot to Kimi 2.5 vision and return structured findings."""
    from openai import OpenAI

    client = OpenAI(api_key=kimi_api_key, base_url="https://api.moonshot.cn/v1")
    with open(screenshot_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        f'You are reviewing a workout import result in the AmakaFlow web app.\n\n'
        f'Context: The user imported a "{description}" from {platform}.\n\n'
        f"Look at this screenshot and identify any issues:\n"
        f"1. Does the workout structure match what was described?\n"
        f"   (e.g. EMOM labelled as Circuit, superset shown as straight sets)\n"
        f"2. Are exercise names reasonable and complete? Any obviously wrong names?\n"
        f"3. Are any metrics obviously wrong?\n"
        f"   (e.g. missing reps/sets when they should be present)\n"
        f"4. Are there any visible errors, loading spinners, or empty states?\n\n"
        f"Be concise. Only report actual problems, not stylistic preferences.\n\n"
        f'Return JSON only, no markdown:\n'
        f'{{"status": "ok" or "issues_found", "findings": ["finding 1", "finding 2"]}}'
    )

    response = client.chat.completions.create(
        model="moonshot-v1-vision-preview",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        temperature=0.1,
        max_tokens=512,
    )
    raw = response.choices[0].message.content or ""
    return parse_kimi_response(raw)


def import_url_via_ui(page, url: str, screenshot_path: Path, timeout_sec: int) -> dict:
    """Drive the AmakaFlow UI to import a URL and screenshot the result."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
    except ImportError:
        return {"status": STATUS_IMPORT_FAILED, "error": "playwright not installed"}

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        page.goto(UI_BASE_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15_000)
        page.get_by_text("Import URL", exact=True).click()
        page.wait_for_selector('[data-testid="import-url-input"]', timeout=10_000)
        page.fill('[data-testid="import-url-input"]', url)
        page.click('[data-testid="import-url-submit"]')
        page.wait_for_selector(
            '[data-testid="import-url-submit"]:has-text("Importing")', timeout=10_000
        )
        page.wait_for_selector(
            '[data-testid="import-url-submit"]:has-text("Import")',
            timeout=timeout_sec * 1_000,
        )
        page.wait_for_timeout(1_500)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        return {"status": STATUS_OK, "error": None}

    except Exception as e:
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        return {"status": STATUS_IMPORT_FAILED, "error": str(e)}


def run_ui_mode(
    url_entries: list[dict],
    timeout: int = DEFAULT_TIMEOUT,
    headed: bool = False,
    kimi_api_key: Optional[str] = None,
) -> list[dict]:
    """Run QA in UI mode — Playwright browser + Kimi vision judgment."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    if not kimi_api_key:
        print("ERROR: KIMI_API_KEY not set (required for UI mode)", file=sys.stderr)
        sys.exit(1)

    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1280, "height": 900})

        for entry in url_entries:
            url = entry["url"]
            platform = entry.get("platform", "unknown")
            workout_type = entry.get("workout_type", "unknown")
            description = entry.get("description", "")

            slug = (url.split("/")[-1] or url.split("/")[-2])[:20]
            ts = int(time.time())
            screenshot_path = ARTIFACTS_DIR / "screenshots" / f"{platform}-{slug}-{ts}.png"

            print(f"  [{workout_type}] {platform}: {url[:70]}", end=" ... ", flush=True)
            page = context.new_page()
            import_result = import_url_via_ui(page, url, screenshot_path, timeout)
            page.close()

            if import_result["status"] == STATUS_IMPORT_FAILED:
                print(f"❌ {import_result['error'][:60]}")
                results.append({
                    "url": url, "platform": platform, "workout_type": workout_type,
                    "description": description, "status": STATUS_IMPORT_FAILED,
                    "error": import_result["error"],
                    "screenshot_path": str(screenshot_path), "findings": [],
                })
                continue

            judgment = judge_screenshot(screenshot_path, description, platform, kimi_api_key)
            icon = "✅" if judgment["status"] == "ok" else "⚠️"
            print(f"{icon} {judgment['status']}")

            results.append({
                "url": url, "platform": platform, "workout_type": workout_type,
                "description": description,
                "status": judgment["status"],
                "findings": judgment["findings"],
                "screenshot_path": str(screenshot_path),
                "fields": {}, "mismatches": [], "error": None,
            })

        browser.close()

    return results


# ---------------------------------------------------------------------------
# Assisted process — interactive review of failures
# ---------------------------------------------------------------------------

def run_assist_mode(failures_file: Optional[Path] = None) -> None:
    """
    Interactive CLI for reviewing failed/uncertain ingestions.

    Walks through each case and lets you:
    - Label the expected structure (becomes ground truth for fix tickets)
    - Mark dead URLs for removal from seed list
    - Note known issues
    - Flag false positives
    """
    # Find the most recent failures file if not specified
    if failures_file is None:
        candidates = sorted(ARTIFACTS_DIR.glob("workout-qa-failures-*.json"), reverse=True)
        if not candidates:
            print("No failures file found. Run the QA script first.")
            print(f"Expected files matching: {ARTIFACTS_DIR}/workout-qa-failures-*.json")
            return
        failures_file = candidates[0]
        print(f"Using most recent failures file: {failures_file.name}")

    with open(failures_file) as f:
        data = json.load(f)

    cases = data.get("cases", [])
    if not cases:
        print("No cases to review — all clear! ✅")
        return

    print(f"\n{'='*60}")
    print(f"ASSISTED REVIEW — {len(cases)} cases")
    print(f"From run: {data.get('run_date', 'unknown')}")
    print("Your input becomes ground truth for fix tickets.")
    print(f"{'='*60}\n")

    reviewed = []
    seeds_to_remove = []

    for i, case in enumerate(cases, 1):
        url = case["url"]
        platform = case.get("platform", "?")
        wtype = case.get("workout_type", "?")
        status = case["status"]
        description = case.get("description", "")
        fields = case.get("fields", {})

        print(f"\n[{i}/{len(cases)}] {wtype.upper()} — {platform}")
        print(f"  URL: {url}")
        print(f"  Description: {description}")
        print(f"  Status: {status}")

        if status == STATUS_NEEDS_CLARIFICATION:
            print(f"  Structures returned: {fields.get('structures', [])}")
            print(f"  Min confidence: {fields.get('min_confidence', 'N/A')}")
            print(f"  Exercises ({fields.get('exercise_count', 0)}): {', '.join(fields.get('exercise_names', [])[:5])}")

        elif status in (STATUS_FETCH_ERROR, STATUS_TIMEOUT, STATUS_IMPORT_FAILED):
            print(f"  Error: {case.get('error', 'none')}")

        elif status == STATUS_PARSE_ERROR:
            print(f"  Error: {case.get('error', 'none')}")

        elif status == STATUS_UNSUPPORTED:
            print(f"  Error: URL pattern not recognised by ingestor")

        if case.get("mismatches"):
            print(f"  Mismatches vs expected:")
            for m in case["mismatches"]:
                print(f"    ⚠️  {m}")

        if case.get("screenshot_path") and Path(case["screenshot_path"]).exists():
            print(f"  Screenshot: {case['screenshot_path']}")

        print()

        # Build option menu based on status
        options = {}
        print("  Options:")
        print("    [s] Skip (not a real issue)")

        if status in (STATUS_FETCH_ERROR, STATUS_TIMEOUT, STATUS_IMPORT_FAILED):
            print("    [d] Dead URL — remove from seed list")
            print("    [r] Retry issue — keep, mark for retry")
            options.update({"d": "dead_url", "r": "retry"})

        if status == STATUS_PARSE_ERROR:
            print("    [b] Bug — paste this into a Linear ticket")
            print("    [e] Enter expected structure for ground truth")
            options.update({"b": "bug", "e": "enter_expected"})

        if status == STATUS_NEEDS_CLARIFICATION:
            print("    [c] Correct — structure was actually right (false positive)")
            print("    [w] Wrong — enter the correct expected structure")
            options.update({"c": "correct", "w": "wrong_structure"})

        if status == STATUS_UNSUPPORTED:
            print("    [u] Unsupported — feeds into AMA-750 (URL pattern fixes)")
            options["u"] = "unsupported_noted"

        print("    [k] Known issue — add a note and skip")
        options.update({"s": "skip", "k": "known_issue"})

        print()
        while True:
            choice = input("  Choice: ").strip().lower()
            if choice in options or choice in ("s", "k"):
                break
            print(f"  Invalid choice. Options: {', '.join(sorted({**options, 's': '', 'k': ''}.keys()))}")

        entry = {**case, "review": {"action": options.get(choice, choice), "timestamp": datetime.utcnow().isoformat()}}

        if choice == "d":
            seeds_to_remove.append(url)
            print("  → Marked for removal from seed list")

        elif choice == "w":
            structures = "circuit/amrap/emom/superset/straight_sets/for_time/ambiguous/multi_block/hyrox/single_exercise"
            expected = input(f"  Expected structure [{structures}]: ").strip()
            entry["review"]["expected_structure"] = expected
            print(f"  → Labeled: {expected}")

        elif choice == "e":
            structures = "circuit/amrap/emom/superset/straight_sets/for_time/ambiguous/multi_block/hyrox/single_exercise"
            expected = input(f"  Expected structure [{structures}]: ").strip()
            entry["review"]["expected_structure"] = expected
            rounds_str = input("  Rounds (leave blank if N/A): ").strip()
            if rounds_str:
                entry["review"]["expected_rounds"] = int(rounds_str) if rounds_str.isdigit() else rounds_str
            print(f"  → Ground truth recorded")

        elif choice == "b":
            print("  → Bug report template:")
            print(f"     URL: {url}")
            print(f"     Platform: {platform}")
            print(f"     Expected: {case.get('expected', {})}")
            print(f"     Error: {case.get('error', '')}")
            input("  (Press Enter to continue)")

        elif choice == "k":
            note = input("  Note: ").strip()
            entry["review"]["note"] = note

        reviewed.append(entry)

    # Save reviewed results
    date_str = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_file = ARTIFACTS_DIR / f"workout-qa-assisted-{date_str}.json"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump({
            "reviewed_at": datetime.utcnow().isoformat(),
            "source_file": str(failures_file),
            "cases": reviewed,
        }, f, indent=2)

    print(f"\n✅ Saved {len(reviewed)} reviewed cases to {out_file.name}")

    # Offer to clean dead URLs from seed list
    if seeds_to_remove and SEEDS_FILE.exists():
        print(f"\n{len(seeds_to_remove)} URL(s) marked as dead.")
        remove = input("Remove them from the seed list? [y/N]: ").strip().lower()
        if remove == "y":
            with open(SEEDS_FILE) as f:
                seeds = json.load(f)
            before = len(seeds)
            seeds = [s for s in seeds if s["url"] not in seeds_to_remove]
            with open(SEEDS_FILE, "w") as f:
                json.dump(seeds, f, indent=2)
            print(f"Removed {before - len(seeds)} URLs from seed list.")

    # Summary
    actions = {}
    for r in reviewed:
        a = r["review"]["action"]
        actions[a] = actions.get(a, 0) + 1
    print("\nReview summary:")
    for action, count in sorted(actions.items()):
        print(f"  {action}: {count}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Telegram delivery (from Joshua's implementation — already configured)
# ---------------------------------------------------------------------------

def send_telegram_report(report: str, screenshot_paths: list[str]) -> None:
    """Send QA report and issue screenshots via Telegram Bot."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "7888191549")
    if not bot_token:
        return

    # Truncate report to Telegram's 4096 char limit
    message = report[:4000] + ("…" if len(report) > 4000 else "")
    httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
        timeout=10,
    )
    for path in screenshot_paths:
        if Path(path).exists():
            with open(path, "rb") as f:
                httpx.post(
                    f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": Path(path).name},
                    files={"photo": f},
                    timeout=15,
                )


def load_url_entries(seeds_file: Path, platform_filter: Optional[str] = None) -> list[dict]:
    if not seeds_file.exists():
        print(f"No seed file found at {seeds_file}", file=sys.stderr)
        print("Run: python scripts/workout-url-harvester.py --youtube-only", file=sys.stderr)
        sys.exit(1)
    with open(seeds_file) as f:
        entries = json.load(f)
    if platform_filter:
        entries = [e for e in entries if e.get("platform") == platform_filter]
    return entries


def save_failures(results: list[dict], run_date: str) -> Optional[Path]:
    """Save failures + needs_clarification cases for --assist mode."""
    cases = [r for r in results if r["status"] not in (STATUS_OK,)]
    if not cases:
        return None
    date_str = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_file = ARTIFACTS_DIR / f"workout-qa-failures-{date_str}.json"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump({"run_date": run_date, "cases": cases}, f, indent=2)
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Workout Import QA")
    parser.add_argument("--ui", action="store_true", help="Use UI mode (Playwright + Kimi vision)")
    parser.add_argument("--assist", action="store_true", help="Interactive review of failures from last run")
    parser.add_argument("--harvest", action="store_true", help="Run URL harvester before QA")
    parser.add_argument("--url", help="Test a single URL")
    parser.add_argument("--platform", help="Filter to one platform (youtube/instagram/tiktok)")
    parser.add_argument("--urls", default=str(SEEDS_FILE), help="Path to URL seed file")
    parser.add_argument("--output", default=str(ARTIFACTS_DIR / "workout-qa-report.md"))
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--headed", action="store_true", help="UI mode: headed browser")
    args = parser.parse_args()

    if args.assist:
        run_assist_mode()
        return

    if args.harvest:
        import subprocess
        harvester = Path(__file__).parent / "workout-url-harvester.py"
        subprocess.run([sys.executable, str(harvester), "--youtube-only"], check=True)

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Single URL mode
    if args.url:
        url_entries = [{
            "url": args.url,
            "platform": "unknown",
            "workout_type": "unknown",
            "description": "ad-hoc test URL",
            "expected": {},
        }]
    else:
        url_entries = load_url_entries(Path(args.urls), platform_filter=args.platform)

    print(f"\n🏋️  Workout Import QA — {run_date}")
    print(f"Mode: {'UI (Playwright + Kimi)' if args.ui else 'API'}")
    print(f"URLs: {len(url_entries)} | Timeout: {args.timeout}s")
    print()

    if args.ui:
        kimi_api_key = os.environ.get("KIMI_API_KEY")
        results = run_ui_mode(url_entries, timeout=args.timeout, headed=args.headed, kimi_api_key=kimi_api_key)
        mode = "ui"
    else:
        results = run_api_mode(url_entries, timeout=args.timeout)
        mode = "api"

    # Write report
    report = build_report(results, run_date=run_date, mode=mode)
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report)

    # Save failures for --assist
    failures_file = save_failures(results, run_date)

    # GitHub Actions output
    set_has_issues_output(results)

    # Telegram notification if issues found
    if bad > 0:
        screenshot_paths = [r["screenshot_path"] for r in results if r.get("screenshot_path")]
        send_telegram_report(report, screenshot_paths)

    # Summary
    ok = sum(1 for r in results if r["status"] == STATUS_OK)
    bad = len(results) - ok
    print(f"\n{'='*60}")
    print(f"✅ OK: {ok}  |  ❌/⚠️ Issues: {bad}  |  Total: {len(results)}")
    print(f"Report: {output_file}")
    if failures_file:
        print(f"Failures: {failures_file.name}")
        print(f"\nTo review failures interactively:")
        print(f"  python scripts/workout_import_qa.py --assist")
    print()

    sys.exit(1 if bad > 0 else 0)


if __name__ == "__main__":
    main()
