#!/usr/bin/env python3
"""Workout Import QA Script.

Nightly automated QA that imports real workout URLs into the AmakaFlow UI via Playwright,
screenshots each result, sends the screenshot to Kimi 2.5 vision to judge what looks wrong,
and sends a Markdown report plus screenshots via Telegram when issues are found.
"""
import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


def parse_kimi_response(raw: str) -> dict:
    """Parse Kimi JSON response, handling errors.
    
    Args:
        raw: Raw string response from Kimi API
        
    Returns:
        Dict with status and findings keys
    """
    try:
        data = json.loads(raw)
        return {
            "status": data.get("status", "ok"),
            "findings": data.get("findings", [])
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "status": "parse_error",
            "findings": []
        }


def build_report(results: list[dict], run_date: str) -> str:
    """Generate Markdown report from QA results.
    
    Args:
        results: List of result dicts from QA runs
        run_date: Date string for the report header
        
    Returns:
        Markdown formatted report string
    """
    total = len(results)
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    issues_count = sum(1 for r in results if r.get("status") == "issues_found")
    failed_count = sum(1 for r in results if r.get("status") == "error")
    
    lines = [
        f"# Workout Import QA Report",
        f"",
        f"**Run Date:** {run_date}",
        f"",
        f"## Summary",
        f"",
        f"| Total | OK | Issues | Failed |",
        f"|-------|-----|--------|--------|",
        f"| {total} | {ok_count} | {issues_count} | {failed_count} |",
        f"",
        f"## Results",
        f"",
    ]
    
    for i, result in enumerate(results, 1):
        url = result.get("url", "unknown")
        status = result.get("status", "unknown")
        description = result.get("description", "")
        
        lines.append(f"### {i}. {description}")
        lines.append(f"")
        lines.append(f"**URL:** {url}")
        lines.append(f"")
        lines.append(f"**Status:** {status}")
        lines.append(f"")
        
        if status == "issues_found":
            findings = result.get("findings", [])
            if findings:
                lines.append("**Findings:**")
                for finding in findings:
                    lines.append(f"- {finding}")
                lines.append("")
        elif status == "error":
            error = result.get("error", "Unknown error")
            lines.append(f"**Error:** {error}")
            lines.append("")
    
    return "\n".join(lines)


def set_has_issues_output(results: list[dict]) -> None:
    """Write has_issues to GitHub Actions output file.
    
    Args:
        results: List of result dicts from QA runs
    """
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    
    has_issues = any(
        r.get("status") in ("issues_found", "error", "parse_error")
        for r in results
    )
    
    with open(github_output, "a") as f:
        f.write(f"has_issues={'true' if has_issues else 'false'}\n")


def judge_screenshot(screenshot_path: str, description: str, platform: str, kimi_api_key: str) -> dict:
    """Judge screenshot using Kimi vision API.
    
    Args:
        screenshot_path: Path to the screenshot PNG file
        description: Description of the workout being tested
        platform: Platform the URL came from (instagram, etc.)
        kimi_api_key: Kimi API key
        
    Returns:
        Dict with status and findings from Kimi
    """
    # Read and base64 encode the screenshot
    with open(screenshot_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    # Initialize Kimi client (OpenAI-compatible)
    client = OpenAI(
        api_key=kimi_api_key,
        base_url="https://api.moonshot.cn/v1"
    )
    
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
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    }
                ]
            }
        ],
        temperature=0.1,
    )
    
    raw_response = response.choices[0].message.content
    return parse_kimi_response(raw_response)


def import_url_and_screenshot(page, url: str, platform: str, screenshot_path: str, base_url: str, timeout_sec: int = 120) -> dict:
    """Import URL via Playwright and take screenshot.
    
    Args:
        page: Playwright page object
        url: URL to import
        platform: Platform identifier
        screenshot_path: Where to save screenshot
        base_url: Base URL of the app
        timeout_sec: Timeout in seconds for import
        
    Returns:
        Dict with import result
    """
    try:
        # Navigate to the app
        page.goto(base_url, wait_until="networkidle", timeout=timeout_sec * 1000)
        
        # Click "Import URL" in navigation
        import_url_nav = page.locator('[data-testid="import-url-input"]')
        if import_url_nav.count() == 0:
            # Try to find and click an import button/link
            import_button = page.get_by_role("button", name="Import")
            if import_button.count() > 0:
                import_button.first.click()
                page.wait_for_timeout(500)
        
        # Fill the URL input
        url_input = page.locator('[data-testid="import-url-input"]')
        url_input.fill(url)
        
        # Click submit
        submit_button = page.locator('[data-testid="import-url-submit"]')
        submit_button.click()
        
        # Wait for streaming to finish - button text changes from "Importing..." to "Import"
        page.wait_for_function("""() => {
            const btn = document.querySelector('[data-testid="import-url-submit"]');
            return btn && btn.textContent === 'Import';
        }""", timeout=timeout_sec * 1000)
        
        # Wait a bit for any animations
        page.wait_for_timeout(1000)
        
        # Take screenshot
        page.screenshot(path=screenshot_path, full_page=True)
        
        return {
            "status": "imported",
            "screenshot": screenshot_path
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def run_qa(urls_file: str, base_url: str, headed: bool = False, timeout: int = 120) -> list[dict]:
    """Run the full QA workflow.
    
    Args:
        urls_file: Path to JSON file with URLs to test
        base_url: Base URL of the app
        headed: Whether to run browser in headed mode
        timeout: Timeout for each import in seconds
        
    Returns:
        List of result dicts
    """
    from playwright.sync_api import sync_playwright
    
    # Load URLs
    with open(urls_file) as f:
        urls = json.load(f)
    
    # Get API key
    kimi_api_key = os.environ.get("KIMI_API_KEY")
    if not kimi_api_key:
        raise ValueError("KIMI_API_KEY environment variable is required")
    
    # Create artifacts directory
    artifacts_dir = Path("artifacts")
    screenshots_dir = artifacts_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        
        for i, entry in enumerate(urls):
            url = entry["url"]
            platform = entry["platform"]
            description = entry["description"]
            
            # Open fresh page for each URL
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            
            screenshot_path = screenshots_dir / f"workout_{i+1}_{platform}.png"
            
            # Import URL and take screenshot
            import_result = import_url_and_screenshot(
                page, url, platform, str(screenshot_path), base_url, timeout
            )
            
            if import_result.get("status") == "error":
                results.append({
                    "url": url,
                    "description": description,
                    "platform": platform,
                    "status": "error",
                    "error": import_result.get("error", "Unknown error")
                })
                context.close()
                continue
            
            # Judge with Kimi
            judgment = judge_screenshot(
                str(screenshot_path), description, platform, kimi_api_key
            )
            
            results.append({
                "url": url,
                "description": description,
                "platform": platform,
                "status": judgment.get("status", "ok"),
                "findings": judgment.get("findings", []),
                "screenshot": str(screenshot_path)
            })
            
            context.close()
        
        browser.close()
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Workout Import QA")
    parser.add_argument("--urls", required=True, help="Path to JSON file with URLs")
    parser.add_argument("--base-url", default="http://localhost:3000", help="Base URL of the app")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout for each import in seconds")
    
    args = parser.parse_args()
    
    # Run QA
    results = run_qa(args.urls, args.base_url, args.headed, args.timeout)
    
    # Generate report
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = build_report(results, run_date)
    
    # Write report to artifacts
    report_path = Path("artifacts") / "workout-qa-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"Report written to {report_path}")
    print()
    print(report)
    
    # Set GitHub output
    set_has_issues_output(results)
    
    # Exit with error code if there were issues
    has_issues = any(
        r.get("status") in ("issues_found", "error", "parse_error")
        for r in results
    )
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
