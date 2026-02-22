# Workout Import QA Automation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A nightly Python + Playwright script that imports workout URLs into the AmakaFlow UI, screenshots each result, sends screenshots to Kimi 2.5 vision for judgment, and emails a Markdown report when issues are found.

**Architecture:** Standalone Python script in `amakaflow-automation/scripts/` drives a headless Chromium browser via Playwright, imports each URL from a JSON seed list through the real UI, captures screenshots, calls Kimi 2.5 vision API to identify problems, and outputs a Markdown report. A GitHub Action runs this nightly and emails the report if issues are found.

**Tech Stack:** Python 3.11+, playwright-python, openai SDK (Moonshot-compatible), GitHub Actions, dawidd6/action-send-mail

**Repo:** `supergeri/amakaflow-automation`

**Key facts about the UI:**
- URL import input: `[data-testid="import-url-input"]`
- Submit button: `[data-testid="import-url-submit"]`
- Button text is `"Importing..."` while streaming, `"Import"` when done
- Auth bypass: when `VITE_CLERK_PUBLISHABLE_KEY` contains `"placeholder"`, the app auto-creates a dev user — no login required
- The UI runs at `http://localhost:3000` in dev

---

### Task 1: URL seed list

**Files:**
- Create: `fixtures/workout-qa-urls.json`

**Step 1: Create the seed file**

```json
[
  {
    "url": "https://www.instagram.com/reel/REPLACE_ME_1/",
    "platform": "instagram",
    "description": "Replace with a real Instagram workout reel description"
  },
  {
    "url": "https://www.youtube.com/watch?v=REPLACE_ME_2",
    "platform": "youtube",
    "description": "Replace with a real YouTube workout video description"
  },
  {
    "url": "https://www.tiktok.com/@user/video/REPLACE_ME_3",
    "platform": "tiktok",
    "description": "Replace with a real TikTok workout description"
  }
]
```

**NOTE:** David will replace the placeholder URLs with real ones before the first run. Leave the placeholders in — they serve as the template.

**Step 2: Verify file is valid JSON**

Run: `python3 -c "import json; json.load(open('fixtures/workout-qa-urls.json')); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add fixtures/workout-qa-urls.json
git commit -m "feat: add workout QA URL seed list"
```

---

### Task 2: Python dependencies

**Files:**
- Create: `requirements-qa.txt`

**Step 1: Create requirements file**

```
playwright==1.41.0
openai==1.12.0
```

**Step 2: Install and verify**

```bash
pip install -r requirements-qa.txt
playwright install chromium
python3 -c "from playwright.sync_api import sync_playwright; print('playwright OK')"
python3 -c "import openai; print('openai OK')"
```

Expected: both print OK

**Step 3: Commit**

```bash
git add requirements-qa.txt
git commit -m "feat: add QA script Python dependencies"
```

---

### Task 3: Unit tests for report generation

**Files:**
- Create: `scripts/test_workout_import_qa.py`

**Step 1: Write the failing tests**

```python
# scripts/test_workout_import_qa.py
import json
import pytest
from unittest.mock import patch, MagicMock


# We test the pure functions before writing them.
# Import will fail until Task 4 creates the module.
from workout_import_qa import (
    build_report,
    parse_kimi_response,
    set_has_issues_output,
)


class TestParseKimiResponse:
    def test_ok_status(self):
        raw = '{"status": "ok", "findings": []}'
        result = parse_kimi_response(raw)
        assert result["status"] == "ok"
        assert result["findings"] == []

    def test_issues_found(self):
        raw = '{"status": "issues_found", "findings": ["EMOM showing as Circuit"]}'
        result = parse_kimi_response(raw)
        assert result["status"] == "issues_found"
        assert len(result["findings"]) == 1

    def test_invalid_json_returns_unknown(self):
        result = parse_kimi_response("not json at all")
        assert result["status"] == "parse_error"
        assert len(result["findings"]) == 1  # error message as finding

    def test_missing_fields_handled(self):
        raw = '{"status": "ok"}'  # no findings key
        result = parse_kimi_response(raw)
        assert result["findings"] == []


class TestBuildReport:
    def test_all_ok(self):
        results = [
            {
                "url": "https://instagram.com/reel/abc",
                "platform": "instagram",
                "description": "EMOM workout",
                "status": "ok",
                "findings": [],
                "screenshot_path": "artifacts/screenshots/instagram-abc.png",
            }
        ]
        report = build_report(results, run_date="2026-02-22 06:00 UTC")
        assert "# Workout Import QA" in report
        assert "2026-02-22" in report
        assert "Total: 1" in report
        assert "✅ OK: 1" in report
        assert "⚠️ Issues: 0" in report
        assert "❌ Failed: 0" in report
        assert "instagram" in report

    def test_issues_shown(self):
        results = [
            {
                "url": "https://instagram.com/reel/abc",
                "platform": "instagram",
                "description": "EMOM workout",
                "status": "issues_found",
                "findings": ["EMOM showing as Circuit", "No rounds visible"],
                "screenshot_path": "artifacts/screenshots/instagram-abc.png",
            }
        ]
        report = build_report(results, run_date="2026-02-22 06:00 UTC")
        assert "⚠️ Issues: 1" in report
        assert "EMOM showing as Circuit" in report
        assert "No rounds visible" in report

    def test_failed_import_shown(self):
        results = [
            {
                "url": "https://tiktok.com/video/123",
                "platform": "tiktok",
                "description": "HIIT workout",
                "status": "import_failed",
                "findings": ["Timeout after 90s"],
                "screenshot_path": "artifacts/screenshots/tiktok-123.png",
            }
        ]
        report = build_report(results, run_date="2026-02-22 06:00 UTC")
        assert "❌ Failed: 1" in report
        assert "import_failed" in report or "Timeout" in report


class TestSetHasIssuesOutput:
    def test_sets_env_file(self, tmp_path):
        env_file = tmp_path / "github_output"
        results = [{"status": "issues_found", "findings": ["problem"]}]
        with patch.dict("os.environ", {"GITHUB_OUTPUT": str(env_file)}):
            set_has_issues_output(results)
        content = env_file.read_text()
        assert "has_issues=true" in content

    def test_no_issues(self, tmp_path):
        env_file = tmp_path / "github_output"
        results = [{"status": "ok", "findings": []}]
        with patch.dict("os.environ", {"GITHUB_OUTPUT": str(env_file)}):
            set_has_issues_output(results)
        content = env_file.read_text()
        assert "has_issues=false" in content

    def test_no_github_output_env(self):
        # Should not crash if not in GitHub Actions
        results = [{"status": "ok", "findings": []}]
        with patch.dict("os.environ", {}, clear=True):
            set_has_issues_output(results)  # must not raise
```

**Step 2: Run tests to verify they fail**

```bash
cd /path/to/amakaflow-automation
python3 -m pytest scripts/test_workout_import_qa.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'workout_import_qa'`

**Step 3: Commit the tests**

```bash
git add scripts/test_workout_import_qa.py
git commit -m "test: add unit tests for workout QA report generation"
```

---

### Task 4: Core QA script

**Files:**
- Create: `scripts/workout_import_qa.py`

This is the main module. Write it so the tests from Task 3 pass.

**Step 1: Create the script**

```python
#!/usr/bin/env python3
"""
Workout Import QA — nightly automation script.

Imports workout URLs into the AmakaFlow UI via Playwright, screenshots each
result, calls Kimi 2.5 vision to judge what's wrong, and writes a Markdown report.

Usage:
    python3 scripts/workout_import_qa.py [--urls fixtures/workout-qa-urls.json]
                                         [--base-url http://localhost:3000]
                                         [--timeout 90]
                                         [--output artifacts/workout-qa-report.md]
                                         [--headed]
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# ---------------------------------------------------------------------------
# Pure functions (unit-testable, no Playwright/network side-effects)
# ---------------------------------------------------------------------------

def parse_kimi_response(raw: str) -> dict:
    """Parse Kimi vision response JSON into a normalised dict.

    Returns: {"status": "ok"|"issues_found"|"parse_error", "findings": [...]}
    """
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


def build_report(results: list[dict], run_date: str) -> str:
    """Build a Markdown QA report from a list of per-URL result dicts."""
    total = len(results)
    ok = sum(1 for r in results if r["status"] == "ok")
    issues = sum(1 for r in results if r["status"] == "issues_found")
    failed = sum(1 for r in results if r["status"] in ("import_failed", "parse_error"))

    lines = [
        f"# Workout Import QA — {run_date}",
        "",
        "## Summary",
        f"- Total: {total} | ✅ OK: {ok} | ⚠️ Issues: {issues} | ❌ Failed: {failed}",
        "",
        "## Results",
        "",
    ]

    for r in results:
        status = r["status"]
        if status == "ok":
            icon = "✅"
        elif status == "issues_found":
            icon = "⚠️"
        else:
            icon = "❌"

        lines.append(f"### {icon} {r['platform']} — {r['description']}")
        lines.append(f"**URL:** {r['url']}")
        lines.append(f"**Screenshot:** {r['screenshot_path']}")

        if r["findings"]:
            lines.append("**Findings:**")
            for finding in r["findings"]:
                lines.append(f"- {finding}")
        lines.append("")

    return "\n".join(lines)


def set_has_issues_output(results: list[dict]) -> None:
    """Write GitHub Actions output variable `has_issues` (true/false)."""
    has_issues = any(r["status"] != "ok" for r in results)
    value = "true" if has_issues else "false"

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_issues={value}\n")
    else:
        print(f"[qa] has_issues={value} (not in GitHub Actions, skipping output)")


# ---------------------------------------------------------------------------
# Vision judgment (calls Kimi 2.5)
# ---------------------------------------------------------------------------

def judge_screenshot(
    screenshot_path: Path,
    description: str,
    platform: str,
    kimi_api_key: str,
) -> dict:
    """Send screenshot to Kimi 2.5 vision and get structured findings."""
    client = OpenAI(
        api_key=kimi_api_key,
        base_url="https://api.moonshot.cn/v1",
    )

    with open(screenshot_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    prompt = f"""You are reviewing a workout import result in the AmakaFlow web app.

Context: The user imported a "{description}" from {platform}.

Look at this screenshot and identify any issues:
1. Does the workout structure match what was described?
   (e.g. EMOM labelled as Circuit, superset shown as straight sets)
2. Are exercise names reasonable and complete? Any obviously wrong names?
3. Are any metrics obviously wrong?
   (e.g. calorie target shown as distance in meters, missing reps/sets when they should be present)
4. Are there any visible errors, loading spinners, or empty states?

Be concise. Only report actual problems, not stylistic preferences.

Return JSON only, no markdown:
{{"status": "ok" or "issues_found", "findings": ["finding 1", "finding 2"]}}"""

    response = client.chat.completions.create(
        model="moonshot-v1-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        temperature=0.1,
        max_tokens=512,
    )

    raw = response.choices[0].message.content or ""
    return parse_kimi_response(raw)


# ---------------------------------------------------------------------------
# Playwright import flow (one URL)
# ---------------------------------------------------------------------------

def import_url_and_screenshot(
    page,
    url: str,
    platform: str,
    screenshot_path: Path,
    base_url: str,
    timeout_sec: int,
) -> dict:
    """
    Drive the AmakaFlow UI to import a URL and screenshot the result.

    Returns: {"status": "ok"|"import_failed", "error": str|None}
    """
    try:
        # Navigate to the app
        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15_000)

        # Click the "Import URL" nav button
        page.get_by_text("Import URL", exact=True).click()
        page.wait_for_selector('[data-testid="import-url-input"]', timeout=10_000)

        # Fill in the URL and submit
        page.fill('[data-testid="import-url-input"]', url)
        page.click('[data-testid="import-url-submit"]')

        # Wait for streaming to start (button changes to "Importing...")
        page.wait_for_selector(
            '[data-testid="import-url-submit"]:has-text("Importing")',
            timeout=10_000,
        )

        # Wait for streaming to finish (button reverts to "Import")
        page.wait_for_selector(
            '[data-testid="import-url-submit"]:has-text("Import")',
            timeout=timeout_sec * 1_000,
        )

        # Brief settle time for rendering
        page.wait_for_timeout(1_500)

        # Screenshot the full result
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)

        return {"status": "ok", "error": None}

    except PlaywrightTimeout as e:
        # Capture whatever is on screen when we time out
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        return {"status": "import_failed", "error": f"Timeout: {e}"}

    except Exception as e:
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        return {"status": "import_failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_qa(
    urls_file: Path,
    base_url: str,
    timeout_sec: int,
    output_file: Path,
    headed: bool,
    kimi_api_key: str,
) -> list[dict]:
    """Run the full QA loop. Returns list of per-URL result dicts."""
    with open(urls_file) as f:
        url_entries = json.load(f)

    results = []
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1280, "height": 900})

        for entry in url_entries:
            url = entry["url"]
            platform = entry.get("platform", "unknown")
            description = entry.get("description", "workout")

            # Build a short slug for the screenshot filename
            slug = url.split("/")[-2] if url.endswith("/") else url.split("/")[-1]
            slug = slug[:20] or platform
            timestamp = int(time.time())
            screenshot_path = Path(f"artifacts/screenshots/{platform}-{slug}-{timestamp}.png")

            print(f"\n[qa] Importing {platform}: {url[:80]}")

            # Open fresh page per URL to avoid state bleed
            page = context.new_page()

            import_result = import_url_and_screenshot(
                page=page,
                url=url,
                platform=platform,
                screenshot_path=screenshot_path,
                base_url=base_url,
                timeout_sec=timeout_sec,
            )
            page.close()

            if import_result["status"] == "import_failed":
                print(f"[qa] ❌ Import failed: {import_result['error']}")
                results.append({
                    "url": url,
                    "platform": platform,
                    "description": description,
                    "status": "import_failed",
                    "findings": [import_result["error"] or "Unknown error"],
                    "screenshot_path": str(screenshot_path),
                })
                continue

            # Judge the screenshot with Kimi vision
            print(f"[qa] Sending screenshot to Kimi for judgment...")
            judgment = judge_screenshot(
                screenshot_path=screenshot_path,
                description=description,
                platform=platform,
                kimi_api_key=kimi_api_key,
            )

            icon = "✅" if judgment["status"] == "ok" else "⚠️"
            print(f"[qa] {icon} {judgment['status']}: {judgment['findings']}")

            results.append({
                "url": url,
                "platform": platform,
                "description": description,
                "status": judgment["status"],
                "findings": judgment["findings"],
                "screenshot_path": str(screenshot_path),
            })

        browser.close()

    # Write report
    output_file.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(results, run_date=run_date)
    output_file.write_text(report)
    print(f"\n[qa] Report written to {output_file}")

    # Set GitHub Actions output
    set_has_issues_output(results)

    return results


def main():
    parser = argparse.ArgumentParser(description="Workout Import QA")
    parser.add_argument("--urls", default="fixtures/workout-qa-urls.json")
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--timeout", type=int, default=90,
                        help="Seconds to wait for import to complete")
    parser.add_argument("--output", default="artifacts/workout-qa-report.md")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser in headed mode (for local debugging)")
    args = parser.parse_args()

    kimi_api_key = os.environ.get("KIMI_API_KEY")
    if not kimi_api_key:
        print("ERROR: KIMI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    results = run_qa(
        urls_file=Path(args.urls),
        base_url=args.base_url,
        timeout_sec=args.timeout,
        output_file=Path(args.output),
        headed=args.headed,
        kimi_api_key=kimi_api_key,
    )

    # Exit 1 if any issues (useful for CI to detect problems)
    has_issues = any(r["status"] != "ok" for r in results)
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
```

**Step 2: Run the unit tests**

```bash
cd /path/to/amakaflow-automation
python3 -m pytest scripts/test_workout_import_qa.py -v
```

Expected: all tests pass

**Step 3: Commit**

```bash
git add scripts/workout_import_qa.py
git commit -m "feat: add workout import QA script (Playwright + Kimi vision)"
```

---

### Task 5: Service health check script

**Files:**
- Create: `scripts/wait-for-services.sh`

**Step 1: Create the script**

```bash
#!/usr/bin/env bash
# Wait for all AmakaFlow services to be healthy before running QA.
set -e

MAX_WAIT=120  # seconds
INTERVAL=3

SERVICES=(
  "http://localhost:3000"
  "http://localhost:8004/health"
)

for SERVICE in "${SERVICES[@]}"; do
  echo "Waiting for $SERVICE..."
  elapsed=0
  until curl -sf "$SERVICE" > /dev/null 2>&1; do
    if [ $elapsed -ge $MAX_WAIT ]; then
      echo "ERROR: $SERVICE did not become healthy within ${MAX_WAIT}s"
      exit 1
    fi
    sleep $INTERVAL
    elapsed=$((elapsed + INTERVAL))
  done
  echo "  ✅ $SERVICE is up"
done

echo "All services healthy."
```

**Step 2: Make it executable and test it locally**

```bash
chmod +x scripts/wait-for-services.sh
# With dev stack running:
./scripts/wait-for-services.sh
```

Expected: `All services healthy.`

**Step 3: Commit**

```bash
git add scripts/wait-for-services.sh
git commit -m "feat: add service health check script for QA"
```

---

### Task 6: GitHub Action workflow

**Files:**
- Create: `.github/workflows/workout-qa.yml`

**Step 1: Create the workflow**

```yaml
name: Workout Import QA

on:
  schedule:
    - cron: '0 6 * * *'   # 06:00 UTC nightly
  workflow_dispatch:        # Allow manual trigger from GitHub UI

jobs:
  qa:
    runs-on: ubuntu-latest
    outputs:
      has_issues: ${{ steps.qa.outputs.has_issues }}

    steps:
      - name: Checkout automation repo
        uses: actions/checkout@v4

      - name: Checkout dev-workspace (for docker-compose)
        uses: actions/checkout@v4
        with:
          repository: supergeri/amakaflow-dev-workspace
          token: ${{ secrets.GH_PAT }}
          path: amakaflow-dev-workspace

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install QA dependencies
        run: |
          pip install -r requirements-qa.txt
          playwright install chromium --with-deps

      - name: Create .env for dev stack
        run: |
          cat > amakaflow-dev-workspace/.env <<EOF
          SUPABASE_URL=${{ secrets.SUPABASE_URL }}
          SUPABASE_ANON_KEY=${{ secrets.SUPABASE_ANON_KEY }}
          SUPABASE_SERVICE_ROLE_KEY=${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}
          APIFY_API_TOKEN=${{ secrets.APIFY_API_TOKEN }}
          VITE_CLERK_PUBLISHABLE_KEY=placeholder
          EOF

      - name: Start dev stack
        run: docker compose up -d
        working-directory: amakaflow-dev-workspace

      - name: Wait for services
        run: ./scripts/wait-for-services.sh

      - name: Run QA script
        id: qa
        env:
          KIMI_API_KEY: ${{ secrets.KIMI_API_KEY }}
        run: |
          python3 scripts/workout_import_qa.py \
            --urls fixtures/workout-qa-urls.json \
            --base-url http://localhost:3000 \
            --timeout 120 \
            --output artifacts/workout-qa-report.md
        continue-on-error: true   # Don't fail the job — we handle this in email step

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: workout-qa-${{ github.run_id }}
          path: artifacts/
          retention-days: 7

      - name: Send email if issues found
        if: steps.qa.outputs.has_issues == 'true'
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: smtp.gmail.com
          server_port: 587
          secure: false
          username: ${{ secrets.SMTP_USERNAME }}
          password: ${{ secrets.SMTP_PASSWORD }}
          to: ${{ secrets.QA_REPORT_EMAIL }}
          from: AmakaFlow QA <${{ secrets.SMTP_USERNAME }}>
          subject: "⚠️ Workout Import QA — Issues Found (${{ github.run_id }})"
          body: |
            Workout import QA found issues in the nightly run.

            View the full report and screenshots here:
            ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}

            Artifacts are available for 7 days.
```

**Step 2: Verify the YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/workout-qa.yml')); print('YAML OK')"
```

Expected: `YAML OK`

**Step 3: Commit**

```bash
git add .github/workflows/workout-qa.yml
git commit -m "feat: add nightly workout import QA GitHub Action"
```

---

### Task 7: Final wiring — test the full script locally

**Before running, confirm:**
- `KIMI_API_KEY` is set in your shell
- The dev stack is running (`docker compose up -d` from `amakaflow-dev-workspace/`)
- `fixtures/workout-qa-urls.json` has at least one real URL in it

**Step 1: Run a dry-run with one URL**

Edit `fixtures/workout-qa-urls.json` temporarily to have just one entry with a real URL (ask David for a test URL if needed).

**Step 2: Run the script headed (so you can watch)**

```bash
KIMI_API_KEY=your_key python3 scripts/workout_import_qa.py \
  --urls fixtures/workout-qa-urls.json \
  --headed \
  --timeout 120
```

Expected:
- Chromium opens and navigates to `localhost:3000`
- Imports the URL via the UI
- A screenshot appears in `artifacts/screenshots/`
- Report written to `artifacts/workout-qa-report.md`
- Output shows `✅` or `⚠️` per URL

**Step 3: Read the report**

```bash
cat artifacts/workout-qa-report.md
```

**Step 4: Run all unit tests one final time**

```bash
python3 -m pytest scripts/test_workout_import_qa.py -v
```

Expected: all pass

**Step 5: Final commit**

```bash
git add fixtures/workout-qa-urls.json  # if you updated it
git commit -m "feat: workout import QA — ready for nightly schedule"
```

---

## GitHub Secrets Required

Add these in `supergeri/amakaflow-automation` → Settings → Secrets:

| Secret | Description |
|--------|-------------|
| `KIMI_API_KEY` | Moonshot AI API key for Kimi 2.5 vision |
| `SMTP_USERNAME` | Gmail address (e.g. qa@amakaflow.com) |
| `SMTP_PASSWORD` | Gmail app password (generate at myaccount.google.com/apppasswords) |
| `QA_REPORT_EMAIL` | Email to send reports to (David's email) |
| `GH_PAT` | GitHub Personal Access Token to checkout amakaflow-dev-workspace |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `OPENAI_API_KEY` | OpenAI API key (used by ingestor parsers) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `APIFY_API_TOKEN` | Apify token for Instagram scraping |

## Acceptance Criteria

- [ ] `python3 -m pytest scripts/test_workout_import_qa.py -v` — all tests pass
- [ ] Script runs end-to-end against at least one real URL without crashing
- [ ] Screenshot captured for the URL (success or timeout state)
- [ ] Kimi vision returns structured JSON with status + findings
- [ ] `artifacts/workout-qa-report.md` contains summary table and per-URL details
- [ ] GitHub Action YAML is valid and workflow appears in Actions tab
- [ ] Email sent when `has_issues=true` (verify by triggering with a bad URL temporarily)
- [ ] No email sent on clean run
