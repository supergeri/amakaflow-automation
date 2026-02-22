# Workout Import QA Automation — Design

**Date:** 2026-02-21
**Status:** Approved

---

## Goal

Automatically import workout URLs from a curated seed list, screenshot the result in the AmakaFlow UI, use Kimi 2.5 vision to identify what looks wrong, and email a report. Phase 1 is observation only — no auto-fix, no Linear ticket creation yet.

## Architecture

```
fixtures/workout-qa-urls.json   ← David maintains this list
          ↓
.github/workflows/workout-qa.yml  (nightly 06:00 UTC cron)
          ↓
scripts/workout-import-qa.py
    ├── For each URL:
    │   ├── Playwright: open localhost:3000, trigger import via UI
    │   ├── Wait up to 90s for workout blocks to render
    │   ├── Screenshot full workout result → artifacts/screenshots/
    │   ├── If timeout/error: screenshot error state, mark import_failed
    │   └── Kimi 2.5 vision: judge screenshot against description
    └── Write artifacts/workout-qa-report.md
          ↓
    If any issues found → send email notification
```

## Components

### 1. URL Seed List — `fixtures/workout-qa-urls.json`

```json
[
  {
    "url": "https://www.instagram.com/reel/...",
    "platform": "instagram",
    "description": "HYROX EMOM workout — should show emom structure, 6 rounds"
  },
  {
    "url": "https://www.youtube.com/watch?v=...",
    "platform": "youtube",
    "description": "Upper body superset — should show superset structure"
  }
]
```

David adds/removes URLs here. The `description` is passed to Kimi as context for what the parsed result *should* look like.

### 2. Python Script — `scripts/workout-import-qa.py`

**Dependencies:** `playwright`, `openai`, `jinja2` (for report templating)

**Per-URL flow:**
1. Launch Chromium via Playwright (headless in CI, headed locally)
2. Navigate to `http://localhost:3000`
3. Find the URL import input (by `data-testid` or placeholder text)
4. Paste URL, submit
5. Wait up to 90s for workout blocks to appear
6. Screenshot full page → `artifacts/screenshots/{platform}-{shortid}-{timestamp}.png`
7. On timeout/error → screenshot error state, status = `import_failed`, skip vision step
8. Call Kimi 2.5 vision with screenshot + prompt
9. Store `{ url, platform, description, status, findings, screenshot_path }`

**Vision prompt:**
```
You are reviewing a workout import result in the AmakaFlow web app.

Context: The user imported a "{description}" from {platform}.

Look at this screenshot and identify any issues:
1. Does the workout structure match what was described?
   (e.g. EMOM labelled as Circuit, superset shown as straight sets)
2. Are exercise names reasonable and complete? Any obviously wrong names?
3. Are any metrics obviously wrong?
   (e.g. calorie target shown as distance in meters, missing reps/sets)
4. Are there any visible errors, empty states, or loading spinners?

Be concise. Only report actual problems, not stylistic preferences.

Return JSON only:
{
  "status": "ok" | "issues_found",
  "findings": ["finding 1", "finding 2"]
}
```

**Vision model:** `moonshot-v1-vision-preview` via `https://api.moonshot.cn/v1`

### 3. Report — `artifacts/workout-qa-report.md`

```markdown
# Workout Import QA — 2026-02-22 06:00 UTC

## Summary
- Total: 10 | ✅ OK: 7 | ⚠️ Issues: 2 | ❌ Failed: 1

## Results

### ⚠️ instagram — HYROX EMOM workout
**URL:** https://www.instagram.com/reel/...
**Screenshot:** screenshots/instagram-abc123-20260222.png
**Findings:**
- EMOM showing as Circuit badge
- No rounds count visible

### ✅ youtube — Upper body superset
**URL:** https://www.youtube.com/watch?v=...
**Screenshot:** screenshots/youtube-def456-20260222.png

### ❌ tiktok — Full body HIIT
**URL:** https://www.tiktok.com/...
**Status:** import_failed (timeout after 90s)
```

### 4. GitHub Action — `.github/workflows/workout-qa.yml`

```yaml
name: Workout Import QA
on:
  schedule:
    - cron: '0 6 * * *'  # 06:00 UTC nightly
  workflow_dispatch:       # Allow manual trigger

jobs:
  qa:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start dev stack
        run: docker compose up -d
        working-directory: ../amakaflow-dev-workspace
      - name: Wait for services
        run: ./scripts/wait-for-services.sh
      - name: Install dependencies
        run: pip install playwright openai && playwright install chromium
      - name: Run QA script
        env:
          KIMI_API_KEY: ${{ secrets.KIMI_API_KEY }}
        run: python scripts/workout-import-qa.py
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: workout-qa-${{ github.run_id }}
          path: artifacts/
          retention-days: 7
      - name: Send email if issues found
        if: failure() || steps.qa.outputs.has_issues == 'true'
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: smtp.gmail.com
          server_port: 587
          username: ${{ secrets.SMTP_USERNAME }}
          password: ${{ secrets.SMTP_PASSWORD }}
          to: david@amakaflow.com
          subject: "⚠️ Workout Import QA — Issues Found"
          body: "See attached report. Artifacts: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

### 5. GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `KIMI_API_KEY` | Moonshot AI API key for Kimi 2.5 vision |
| `SMTP_USERNAME` | Gmail address for sending reports |
| `SMTP_PASSWORD` | Gmail app password (not account password) |

## Repo

`supergeri/amakaflow-automation`

## Files Created/Modified

| File | Action |
|------|--------|
| `fixtures/workout-qa-urls.json` | Create — seed URL list |
| `scripts/workout-import-qa.py` | Create — main QA script |
| `scripts/wait-for-services.sh` | Create — health check loop |
| `.github/workflows/workout-qa.yml` | Create — nightly scheduler |
| `requirements-qa.txt` | Create — `playwright`, `openai` |

## Acceptance Criteria

- [ ] Script runs end-to-end against 10 URLs without crashing
- [ ] Screenshot captured for every URL (success or failure state)
- [ ] Kimi vision returns structured JSON findings for each screenshot
- [ ] Markdown report generated with summary table + per-URL details
- [ ] GitHub Action triggers on schedule and uploads artifacts
- [ ] Email sent when `has_issues == 'true'`, not sent on clean runs
- [ ] `pytest scripts/test_workout_import_qa.py` passes (unit tests for report generation and finding parsing)

## Phase 2 (not in scope now)

- Auto-create Linear bug tickets from findings
- Route fix to Joshua via Antfarm
- Golden snapshot comparison for regression detection
