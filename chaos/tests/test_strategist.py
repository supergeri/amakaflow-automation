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
