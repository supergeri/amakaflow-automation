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
        emulator.emit_duplicate_workout()   # sends POST twice (that's the whole point)
        emulator.emit_future_timestamp()
        emulator.emit_extreme_heart_rate()
        emulator.emit_corrupt_gps()
        emulator.emit_partial_payload()
        assert mock_post.call_count == 7  # duplicate sends 2 posts
