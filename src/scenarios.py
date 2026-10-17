"""
scenarios.py — Deterministic scenario library for testing and demonstration.

Each scenario function returns (GridConfig, List[Aircraft]) ready for
the coordinator.  Scenarios are reproducible with identical output
across runs.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.models import Aircraft, GridConfig, Position


# ──────────────────────────────────────────────────────────────────────
# Colour palette for aircraft (distinct, high-contrast colours)
# ──────────────────────────────────────────────────────────────────────
AIRCRAFT_COLORS = [
    "#e74c3c",  # red
    "#2ecc71",  # green
    "#3498db",  # blue
    "#f39c12",  # orange
    "#9b59b6",  # purple
    "#1abc9c",  # teal
    "#e67e22",  # dark orange
    "#2c3e50",  # dark blue-grey
]


def _make_aircraft(
    configs: List[Tuple[str, Position, Position, int]],
) -> List[Aircraft]:
    """Helper: build Aircraft list from (id, start, goal, priority) tuples."""
    result = []
    for i, (aid, start, goal, prio) in enumerate(configs):
        result.append(Aircraft(
            aircraft_id=aid,
            start=start,
            goal=goal,
            priority=prio,
            color=AIRCRAFT_COLORS[i % len(AIRCRAFT_COLORS)],
        ))
    return result


# ══════════════════════════════════════════════════════════════════════
# Scenario 1: Conflict-free routes
# ══════════════════════════════════════════════════════════════════════
def scenario_conflict_free() -> Tuple[GridConfig, List[Aircraft]]:
    """
    Two aircraft follow separate horizontal routes on different rows.
    Expected: both arrive without conflicts or unnecessary waiting.
    """
    grid = GridConfig(width=10, height=10, restricted_cells=set())
    aircraft = _make_aircraft([
        ("AC-1", (0, 2), (9, 2), 0),
        ("AC-2", (0, 7), (9, 7), 1),
    ])
    return grid, aircraft


# ══════════════════════════════════════════════════════════════════════
# Scenario 2: Crossing routes
# ══════════════════════════════════════════════════════════════════════
def scenario_crossing() -> Tuple[GridConfig, List[Aircraft]]:
    """
    Two aircraft have intersecting paths.  Their independent shortest
    routes would produce a conflict at the crossing cell.
    Expected: conflict detected, coordination resolves it.
    """
    grid = GridConfig(width=8, height=8, restricted_cells=set())
    aircraft = _make_aircraft([
        ("AC-1", (0, 3), (7, 3), 0),   # horizontal
        ("AC-2", (3, 0), (3, 7), 1),   # vertical — crosses at (3, 3)
    ])
    return grid, aircraft


# ══════════════════════════════════════════════════════════════════════
# Scenario 3: Unreachable destination
# ══════════════════════════════════════════════════════════════════════
def scenario_unreachable() -> Tuple[GridConfig, List[Aircraft]]:
    """
    Restricted cells completely enclose the destination.
    Expected: planner reports no feasible route.
    """
    blocked = {(4, 3), (5, 3), (6, 3),
               (4, 4),        (6, 4),
               (4, 5), (5, 5), (6, 5)}
    grid = GridConfig(width=10, height=10, restricted_cells=blocked)
    aircraft = _make_aircraft([
        ("AC-1", (0, 0), (5, 4), 0),  # (5,4) is enclosed
    ])
    return grid, aircraft


# ══════════════════════════════════════════════════════════════════════
# Scenario 4: Narrow corridor
# ══════════════════════════════════════════════════════════════════════
def scenario_narrow_corridor() -> Tuple[GridConfig, List[Aircraft]]:
    """
    Three aircraft must negotiate a single-cell-wide corridor (row 3, x=3..6).
    AC-1 and AC-3 travel West-to-East while AC-2 travels East-to-West.
    Because the corridor admits only one aircraft at a time and edge swaps
    are forbidden, lower-priority aircraft must wait outside the bottleneck
    until the corridor clears before entering, demonstrating genuine queuing.
    """
    # Block everything except row 3 in the corridor zone (x=3..6)
    restricted = set()
    for x in range(3, 7):
        for y in range(0, 7):
            if y != 3:
                restricted.add((x, y))

    grid = GridConfig(width=10, height=7, restricted_cells=restricted)
    aircraft = _make_aircraft([
        ("AC-1", (0, 3), (9, 3), 0),   # West -> East, departs first
        ("AC-2", (9, 2), (0, 2), 1),   # East -> West, waits for AC-1 to clear
        ("AC-3", (0, 4), (9, 4), 2),   # West -> East, waits for AC-2 to clear
    ])
    return grid, aircraft


# ══════════════════════════════════════════════════════════════════════
# Edge-case scenarios
# ══════════════════════════════════════════════════════════════════════

def scenario_start_equals_goal() -> Tuple[GridConfig, List[Aircraft]]:
    """Aircraft starts at its goal — should be handled gracefully."""
    grid = GridConfig(width=5, height=5, restricted_cells=set())
    aircraft = _make_aircraft([("AC-1", (2, 2), (2, 2), 0)])
    return grid, aircraft


def scenario_head_on() -> Tuple[GridConfig, List[Aircraft]]:
    """
    Two aircraft moving in opposite directions on the same row.
    Expected: edge-swap conflict detected and resolved.
    """
    grid = GridConfig(width=8, height=8, restricted_cells=set())
    aircraft = _make_aircraft([
        ("AC-1", (0, 3), (7, 3), 0),
        ("AC-2", (7, 3), (0, 3), 1),
    ])
    return grid, aircraft


def scenario_five_aircraft() -> Tuple[GridConfig, List[Aircraft]]:
    """Default five-aircraft scenario on a 12×12 grid."""
    restricted = {(5, 5), (5, 6), (6, 5), (6, 6),
                  (3, 8), (3, 9), (4, 8)}
    grid = GridConfig(width=12, height=12, restricted_cells=restricted)
    aircraft = _make_aircraft([
        ("AC-1", (0, 0), (11, 11), 0),
        ("AC-2", (11, 0), (0, 11), 1),
        ("AC-3", (0, 6), (11, 6), 2),
        ("AC-4", (6, 0), (6, 11), 3),
        ("AC-5", (2, 2), (9, 9), 4),
    ])
    return grid, aircraft


# ══════════════════════════════════════════════════════════════════════
# Scenario registry
# ══════════════════════════════════════════════════════════════════════

SCENARIO_REGISTRY: Dict[str, Tuple] = {
    "1. Conflict-Free Routes": (scenario_conflict_free, "Two aircraft on separate rows — no conflicts expected."),
    "2. Crossing Routes": (scenario_crossing, "Intersecting paths — conflict detection and resolution."),
    "3. Unreachable Destination": (scenario_unreachable, "Enclosed goal — planner should report failure."),
    "4. Narrow Corridor": (scenario_narrow_corridor, "Three aircraft through a single-cell corridor."),
    "5. Start Equals Goal": (scenario_start_equals_goal, "Trivial case — aircraft already at destination."),
    "6. Head-On Collision": (scenario_head_on, "Opposite-direction aircraft — edge-swap detection."),
    "7. Five Aircraft (Default)": (scenario_five_aircraft, "Five aircraft on 12×12 grid with obstacles."),
}


def load_scenario_from_dict(data: dict) -> Tuple[GridConfig, List[Aircraft]]:
    """Construct (GridConfig, List[Aircraft]) from a parsed dictionary."""
    grid_data = data["grid"]
    grid = GridConfig(
        width=grid_data["width"],
        height=grid_data["height"],
        restricted_cells={tuple(p) for p in grid_data.get("restricted_cells", [])},
    )
    aircraft = [
        Aircraft(
            aircraft_id=ac["id"],
            start=tuple(ac["start"]),
            goal=tuple(ac["goal"]),
            priority=ac.get("priority", 0),
            color=ac.get("color", "#3498db"),
        )
        for ac in data["aircraft"]
    ]
    return grid, aircraft


def load_scenarios_from_json(filepath: str = "data/scenarios.json") -> Dict[str, Tuple[GridConfig, List[Aircraft]]]:
    """Load machine-readable scenario configurations from a JSON file."""
    import json
    import os
    if not os.path.exists(filepath):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fallback = os.path.join(base_dir, "data", "scenarios.json")
        if os.path.exists(fallback):
            filepath = fallback
    with open(filepath, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {name: load_scenario_from_dict(spec) for name, spec in raw.items()}
