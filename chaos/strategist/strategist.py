# chaos/strategist/strategist.py
"""Strategist brain for Phase 1 Chaos Engine.

Reads the state graph, scores unexplored surfaces, and outputs
a directive for the Driver. Records visit results back to the graph.
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class Strategist:
    def __init__(
        self,
        state_graph_path: str,
        directives_path: str,
        personas: Dict[str, Any],
        platform: str = "web",
    ) -> None:
        self._sg_path = Path(state_graph_path)
        self._dir_path = Path(directives_path)
        self._personas = personas
        self._platform = platform

    # -- Public API ------------------------------------------------------------

    def get_next_directive(self) -> Dict[str, Any]:
        graph = self._load_state_graph()
        surface = self._pick_surface(graph)
        directive = self._pick_chaos_directive(surface)
        persona = self._pick_persona()

        return {
            "platform": self._platform,
            "persona_id": persona["id"],
            "persona_name": persona.get("name", persona["id"]),
            "goal": f"Use the app as {persona.get('name', persona['id'])} would",
            "surface": surface.split("/")[-1] if "/" in surface else surface,
            "chaos_directive": directive["id"],
            "chaos_description": directive["description"],
            "max_steps": 50,
            "frustration_threshold": 5,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def record_visit(self, surface_key: str, bugs_found: int) -> None:
        graph = self._load_state_graph()
        explored = graph.setdefault("explored", {})
        entry = explored.setdefault(surface_key, {"visits": 0, "bugs": 0, "last": None})
        entry["visits"] += 1
        entry["bugs"] += bugs_found
        entry["last"] = datetime.now(timezone.utc).date().isoformat()
        graph["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save_state_graph(graph)

    # -- Internal helpers ------------------------------------------------------

    def _load_state_graph(self) -> Dict[str, Any]:
        return json.loads(self._sg_path.read_text())

    def _save_state_graph(self, graph: Dict[str, Any]) -> None:
        self._sg_path.write_text(json.dumps(graph, indent=2))

    def _all_surfaces(self, graph: Dict[str, Any]) -> List[str]:
        platform_data = graph["surfaces"].get(self._platform, {})
        surfaces = []
        for category in ("screens", "ai_features", "edge_states"):
            for name in platform_data.get(category, []):
                surfaces.append(f"{self._platform}/{name}")
        return surfaces

    def _score_surface(self, surface: str, graph: Dict[str, Any]) -> float:
        explored = graph.get("explored", {})
        entry = explored.get(surface, {})
        visits = entry.get("visits", 0)
        bugs = entry.get("bugs", 0)
        last = entry.get("last")

        days_since = 999 if last is None else max(0, (
            datetime.now(timezone.utc).date() -
            datetime.fromisoformat(last).date()
        ).days)

        score = (
            min(days_since, 30) / 30 * 0.4
            + min(bugs, 5) / 5 * 0.3
            + (1.0 if visits == 0 else 0.0) * 0.2
            + random.random() * 0.1
        )
        return score

    def _pick_surface(self, graph: Dict[str, Any]) -> str:
        surfaces = self._all_surfaces(graph)
        if not surfaces:
            return f"{self._platform}/dashboard"
        scored = [(s, self._score_surface(s, graph)) for s in surfaces]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _pick_chaos_directive(self, surface: str) -> Dict[str, Any]:
        directives = json.loads(self._dir_path.read_text())["directives"]
        surface_name = surface.split("/")[-1]
        applicable = [
            d for d in directives
            if "all" in d.get("applicable_surfaces", [])
            or surface_name in d.get("applicable_surfaces", [])
        ]
        if not applicable:
            applicable = directives
        # Weighted random selection
        weights = [d.get("weight", 0.5) for d in applicable]
        return random.choices(applicable, weights=weights, k=1)[0]

    def _pick_persona(self) -> Dict[str, Any]:
        identities = self._personas.get("identities", [])
        profiles = self._personas.get("profiles", [])
        identity = random.choice(identities) if identities else {"id": "default"}
        profile = random.choice(profiles) if profiles else {"id": "explorer"}
        return {
            "id": f"{identity['id']}+{profile['id']}",
            "name": f"{identity.get('name', identity['id'])} / {profile.get('name', profile['id'])}",
            "identity": identity,
            "profile": profile,
        }
