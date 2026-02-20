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
            {"name": "strength", "tag_type": "topic", "confidence": 0.8},
        ]
        flags = judge.evaluate_tags(tags)
        assert flags == []

    def test_invalid_tag_type_flagged(self, judge):
        tags = [{"name": "squat", "tag_type": "invented_type", "confidence": 0.9},
                {"name": "legs", "tag_type": "muscle_group", "confidence": 0.85},
                {"name": "strength", "tag_type": "topic", "confidence": 0.8}]
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
        tags = [{"name": "squat", "tag_type": "movement_pattern", "confidence": 0.2},
                {"name": "legs", "tag_type": "muscle_group", "confidence": 0.85},
                {"name": "strength", "tag_type": "topic", "confidence": 0.8}]
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
