#!/usr/bin/env python3
"""
Workout URL Harvester — automatically discovers fresh workout URLs.

Searches for real workout content on YouTube (via yt-dlp, no API key),
Instagram, and TikTok (via Apify, requires APIFY_API_TOKEN).

Appends discovered URLs to fixtures/workout-qa-urls.json, deduplicating
against existing entries.

Usage:
    python scripts/workout-url-harvester.py                   # all platforms
    python scripts/workout-url-harvester.py --youtube-only    # YouTube only
    python scripts/workout-url-harvester.py --count 3         # 3 URLs per type
    python scripts/workout-url-harvester.py --dry-run         # print, don't save
    python scripts/workout-url-harvester.py --workout circuit # one type only
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
SEEDS_FILE = REPO_ROOT / "fixtures" / "workout-qa-urls.json"

# ---------------------------------------------------------------------------
# Search terms per workout type
# ---------------------------------------------------------------------------

WORKOUT_TYPES = {
    "circuit": {
        "description_template": "Circuit workout with rounds and rest periods",
        "expected_structure": "circuit",
        "youtube_queries": [
            "circuit workout 4 rounds 90 seconds rest",
            "full body circuit training rounds timer",
        ],
        "instagram_hashtags": ["circuitworkout", "circuittraining"],
        "tiktok_queries": ["circuit workout rounds rest timer"],
    },
    "amrap": {
        "description_template": "AMRAP workout (as many rounds as possible)",
        "expected_structure": "amrap",
        "youtube_queries": [
            "10 minute AMRAP bodyweight workout",
            "AMRAP crossfit workout as many rounds",
        ],
        "instagram_hashtags": ["amrapworkout", "amrap"],
        "tiktok_queries": ["AMRAP workout 10 minutes"],
    },
    "emom": {
        "description_template": "EMOM workout (every minute on the minute)",
        "expected_structure": "emom",
        "youtube_queries": [
            "20 minute EMOM strength workout",
            "EMOM weightlifting every minute on the minute",
        ],
        "instagram_hashtags": ["emomworkout", "emom"],
        "tiktok_queries": ["EMOM workout strength"],
    },
    "superset": {
        "description_template": "Superset workout with paired exercises",
        "expected_structure": "superset",
        "youtube_queries": [
            "upper body superset workout gym",
            "chest back superset workout pairs",
        ],
        "instagram_hashtags": ["supersetworkout", "superset"],
        "tiktok_queries": ["superset workout gym pairs"],
    },
    "straight_sets": {
        "description_template": "Straight sets strength workout (sets x reps)",
        "expected_structure": "straight_sets",
        "youtube_queries": [
            "strength training sets reps 3x10 workout",
            "powerlifting program sets reps squat bench",
        ],
        "instagram_hashtags": ["strengthtraining", "liftingworkout"],
        "tiktok_queries": ["strength workout sets reps"],
    },
    "for_time": {
        "description_template": "For time workout (descending reps, complete as fast as possible)",
        "expected_structure": "for_time",
        "youtube_queries": [
            "21-15-9 workout for time crossfit",
            "for time workout descending reps complete fast",
        ],
        "instagram_hashtags": ["crossfitworkout", "fortime"],
        "tiktok_queries": ["for time workout 21 15 9"],
    },
    "ambiguous": {
        "description_template": "Workout exercise list without clear structure",
        "expected_structure": "ambiguous",
        "youtube_queries": [
            "bodyweight workout routine exercise list no equipment",
            "home workout exercises list beginner",
        ],
        "instagram_hashtags": ["homeworkout", "bodyweightworkout"],
        "tiktok_queries": ["home workout exercises list"],
    },
    "multi_block": {
        "description_template": "Multi-block workout (warm-up, main block, finisher)",
        "expected_structure": "multi_block",
        "youtube_queries": [
            "full body workout warm up main finisher",
            "complete workout warm up strength cardio cooldown",
        ],
        "instagram_hashtags": ["fullbodyworkout", "completeworkout"],
        "tiktok_queries": ["full workout warm up main finisher"],
    },
    "hyrox": {
        "description_template": "HYROX-style workout with running and functional stations",
        "expected_structure": "hyrox",
        "youtube_queries": [
            "HYROX training workout stations running",
            "HYROX race simulation workout",
        ],
        "instagram_hashtags": ["hyrox", "hyroxtraining"],
        "tiktok_queries": ["HYROX workout stations"],
    },
    "single_exercise": {
        "description_template": "Single exercise demonstration or snippet",
        "expected_structure": "single_exercise",
        "youtube_queries": [
            "how to do burpees workout form tutorial",
            "squat technique single exercise workout snippet",
        ],
        "instagram_hashtags": ["exercisetutorial", "workoutsnippet"],
        "tiktok_queries": ["exercise form tutorial single"],
    },
}


# ---------------------------------------------------------------------------
# YouTube harvester (yt-dlp, no API key needed)
# ---------------------------------------------------------------------------

def harvest_youtube(workout_type: str, queries: list[str], count: int) -> list[dict]:
    """Search YouTube for workout videos using yt-dlp."""
    results = []
    seen_urls = set()

    for query in queries:
        if len(results) >= count:
            break

        search_term = f"ytsearch{count}:{query}"
        logger.info(f"  YouTube search: {query!r}")

        try:
            proc = subprocess.run(
                [
                    "yt-dlp",
                    search_term,
                    "--flat-playlist",
                    "--print", "%(webpage_url)s\t%(title)s\t%(duration)s",
                    "--no-warnings",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            for line in proc.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                url = parts[0] if parts else ""
                title = parts[1] if len(parts) > 1 else ""
                duration = parts[2] if len(parts) > 2 else ""

                if not url or url in seen_urls:
                    continue
                # Skip very short (<30s) or very long (>30min) videos
                try:
                    dur_secs = int(duration) if duration else 0
                    if dur_secs > 0 and (dur_secs < 30 or dur_secs > 1800):
                        continue
                except ValueError:
                    pass

                seen_urls.add(url)
                results.append({
                    "url": url,
                    "platform": "youtube",
                    "workout_type": workout_type,
                    "description": f"{WORKOUT_TYPES[workout_type]['description_template']} — {title[:80]}",
                    "expected": {"structure": WORKOUT_TYPES[workout_type]["expected_structure"]},
                })

                if len(results) >= count:
                    break

        except subprocess.TimeoutExpired:
            logger.warning(f"  yt-dlp timed out for query: {query!r}")
        except FileNotFoundError:
            logger.error("yt-dlp not found. Install with: pip install yt-dlp")
            break
        except Exception as e:
            logger.warning(f"  yt-dlp error: {e}")

    return results[:count]


# ---------------------------------------------------------------------------
# Instagram harvester (Apify)
# ---------------------------------------------------------------------------

def harvest_instagram(workout_type: str, hashtags: list[str], count: int) -> list[dict]:
    """Search Instagram for workout reels using Apify hashtag scraper."""
    apify_token = os.environ.get("APIFY_API_TOKEN")
    if not apify_token:
        logger.warning("APIFY_API_TOKEN not set — skipping Instagram harvest")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed — skipping Instagram harvest")
        return []

    results = []
    client = ApifyClient(apify_token)

    for hashtag in hashtags:
        if len(results) >= count:
            break

        logger.info(f"  Instagram hashtag: #{hashtag}")
        try:
            run = client.actor("apify/instagram-scraper").call(
                run_input={
                    "directUrls": [f"https://www.instagram.com/explore/tags/{hashtag}/"],
                    "resultsType": "posts",
                    "resultsLimit": count * 2,
                    "addParentData": False,
                },
                timeout_secs=60,
            )
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                continue

            for item in client.dataset(dataset_id).iterate_items():
                if len(results) >= count:
                    break
                url = item.get("url") or item.get("shortCode")
                if not url:
                    continue
                if not url.startswith("http"):
                    url = f"https://www.instagram.com/p/{url}/"

                caption = (item.get("caption") or "")[:80]
                results.append({
                    "url": url,
                    "platform": "instagram",
                    "workout_type": workout_type,
                    "description": f"{WORKOUT_TYPES[workout_type]['description_template']} — {caption}",
                    "expected": {"structure": WORKOUT_TYPES[workout_type]["expected_structure"]},
                })

        except Exception as e:
            logger.warning(f"  Instagram Apify error: {e}")

    return results[:count]


# ---------------------------------------------------------------------------
# TikTok harvester (Apify)
# ---------------------------------------------------------------------------

def harvest_tiktok(workout_type: str, queries: list[str], count: int) -> list[dict]:
    """Search TikTok for workout videos using Apify search scraper."""
    apify_token = os.environ.get("APIFY_API_TOKEN")
    if not apify_token:
        logger.warning("APIFY_API_TOKEN not set — skipping TikTok harvest")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed — skipping TikTok harvest")
        return []

    results = []
    client = ApifyClient(apify_token)

    for query in queries:
        if len(results) >= count:
            break

        logger.info(f"  TikTok search: {query!r}")
        try:
            run = client.actor("clockworks/tiktok-scraper").call(
                run_input={
                    "searchQueries": [query],
                    "maxProfilesPerQuery": count * 2,
                    "shouldDownloadVideos": False,
                    "shouldDownloadCovers": False,
                },
                timeout_secs=60,
            )
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                continue

            for item in client.dataset(dataset_id).iterate_items():
                if len(results) >= count:
                    break
                url = item.get("webVideoUrl") or item.get("videoUrl")
                if not url:
                    continue

                desc = (item.get("text") or "")[:80]
                results.append({
                    "url": url,
                    "platform": "tiktok",
                    "workout_type": workout_type,
                    "description": f"{WORKOUT_TYPES[workout_type]['description_template']} — {desc}",
                    "expected": {"structure": WORKOUT_TYPES[workout_type]["expected_structure"]},
                })

        except Exception as e:
            logger.warning(f"  TikTok Apify error: {e}")

    return results[:count]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_existing_seeds() -> tuple[list[dict], set[str]]:
    """Load the existing seed file and return (entries, existing_url_set)."""
    if not SEEDS_FILE.exists():
        return [], set()
    with open(SEEDS_FILE) as f:
        entries = json.load(f)
    return entries, {e["url"] for e in entries}


def save_seeds(entries: list[dict]) -> None:
    SEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEDS_FILE, "w") as f:
        json.dump(entries, f, indent=2)
    logger.info(f"Saved {len(entries)} entries to {SEEDS_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Workout URL Harvester")
    parser.add_argument("--youtube-only", action="store_true", help="YouTube only (no Apify)")
    parser.add_argument("--count", type=int, default=2, help="URLs per workout type per platform")
    parser.add_argument("--dry-run", action="store_true", help="Print URLs, don't save")
    parser.add_argument("--workout", help="Harvest only this workout type")
    args = parser.parse_args()

    workout_types = [args.workout] if args.workout else list(WORKOUT_TYPES.keys())
    unknown = [w for w in workout_types if w not in WORKOUT_TYPES]
    if unknown:
        print(f"Unknown workout types: {unknown}", file=sys.stderr)
        sys.exit(1)

    existing_entries, existing_urls = load_existing_seeds()
    new_entries = []

    for wtype in workout_types:
        config = WORKOUT_TYPES[wtype]
        logger.info(f"\nHarvesting: {wtype}")

        # YouTube
        yt_results = harvest_youtube(wtype, config["youtube_queries"], args.count)
        for r in yt_results:
            if r["url"] not in existing_urls:
                new_entries.append(r)
                existing_urls.add(r["url"])

        if not args.youtube_only:
            # Instagram
            ig_results = harvest_instagram(wtype, config["instagram_hashtags"], args.count)
            for r in ig_results:
                if r["url"] not in existing_urls:
                    new_entries.append(r)
                    existing_urls.add(r["url"])

            # TikTok
            tt_results = harvest_tiktok(wtype, config["tiktok_queries"], args.count)
            for r in tt_results:
                if r["url"] not in existing_urls:
                    new_entries.append(r)
                    existing_urls.add(r["url"])

    logger.info(f"\nFound {len(new_entries)} new URLs (skipped {len(existing_urls) - len(new_entries)} duplicates)")

    if args.dry_run:
        print(json.dumps(new_entries, indent=2))
        return

    all_entries = existing_entries + new_entries
    save_seeds(all_entries)
    print(f"\n✅ Added {len(new_entries)} URLs. Total: {len(all_entries)}")


if __name__ == "__main__":
    main()
