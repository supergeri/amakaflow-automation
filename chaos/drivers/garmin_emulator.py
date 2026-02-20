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
