"""
test_core.py — Comprehensive automated tests for the Air Traffic simulation.

Covers search correctness, conflict detection, reservations,
coordination, simulation execution, edge cases, and reproducibility.
"""

import pytest

from src.environment import create_grid, get_neighbors, validate_aircraft_config
from src.models import (
    Aircraft,
    AircraftStatus,
    ConflictType,
    GridConfig,
    Position,
)
from src.search import astar_search, ucs_search, manhattan_distance
from src.conflict_detection import detect_conflicts
from src.reservations import ReservationTable
from src.coordinator import plan_all_aircraft
from src.simulation import Simulation
from src.scenarios import (
    SCENARIO_REGISTRY,
    scenario_conflict_free,
    scenario_crossing,
    scenario_unreachable,
    scenario_narrow_corridor,
    scenario_start_equals_goal,
    scenario_head_on,
    scenario_five_aircraft,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _empty_grid(w=10, h=10):
    return create_grid(w, h)


def _is_valid_path(grid: GridConfig, path, start, goal):
    """Check that a path is continuous, in-bounds, avoids restricted cells,
    starts at start, and ends at goal."""
    if not path:
        return False
    if path[0] != start or path[-1] != goal:
        return False
    for i, pos in enumerate(path):
        if not grid.is_valid(pos):
            return False
        if i > 0:
            prev = path[i - 1]
            dx = abs(pos[0] - prev[0])
            dy = abs(pos[1] - prev[1])
            if dx + dy > 1:
                return False
    return True


# ══════════════════════════════════════════════════════════════════════
# 1. A* finds a valid path in an empty grid
# ══════════════════════════════════════════════════════════════════════

class TestAStarBasic:
    def test_finds_path_empty_grid(self):
        grid = _empty_grid()
        result = astar_search(grid, (0, 0), (9, 9))
        assert result.success
        assert _is_valid_path(grid, result.path, (0, 0), (9, 9))
        assert result.algorithm == "A*"
        assert result.nodes_expanded > 0

    def test_optimal_cost_empty_grid(self):
        grid = _empty_grid()
        result = astar_search(grid, (0, 0), (5, 5))
        assert result.success
        assert result.cost == 10.0  # Manhattan distance

    def test_path_includes_start_and_goal(self):
        grid = _empty_grid()
        result = astar_search(grid, (1, 1), (4, 4))
        assert result.path[0] == (1, 1)
        assert result.path[-1] == (4, 4)


# ══════════════════════════════════════════════════════════════════════
# 2. UCS finds a valid path in an empty grid
# ══════════════════════════════════════════════════════════════════════

class TestUCSBasic:
    def test_finds_path_empty_grid(self):
        grid = _empty_grid()
        result = ucs_search(grid, (0, 0), (9, 9))
        assert result.success
        assert _is_valid_path(grid, result.path, (0, 0), (9, 9))
        assert result.algorithm == "UCS"
        assert result.nodes_expanded > 0

    def test_optimal_cost_empty_grid(self):
        grid = _empty_grid()
        result = ucs_search(grid, (0, 0), (5, 5))
        assert result.success
        assert result.cost == 10.0


# ══════════════════════════════════════════════════════════════════════
# 3. A* and UCS return equal optimal costs
# ══════════════════════════════════════════════════════════════════════

class TestAlgorithmEquivalence:
    def test_equal_costs_small_grid(self):
        grid = _empty_grid(6, 6)
        r_astar = astar_search(grid, (0, 0), (5, 5))
        r_ucs = ucs_search(grid, (0, 0), (5, 5))
        assert r_astar.success and r_ucs.success
        assert r_astar.cost == r_ucs.cost

    def test_equal_costs_with_obstacles(self):
        grid = create_grid(8, 8, restricted={(3, 3), (3, 4), (4, 3)})
        r_astar = astar_search(grid, (0, 0), (7, 7))
        r_ucs = ucs_search(grid, (0, 0), (7, 7))
        assert r_astar.success and r_ucs.success
        assert r_astar.cost == r_ucs.cost

    def test_astar_expands_fewer_or_equal_nodes(self):
        """A* with admissible heuristic should expand <= nodes than UCS."""
        grid = _empty_grid(8, 8)
        r_astar = astar_search(grid, (0, 0), (7, 7))
        r_ucs = ucs_search(grid, (0, 0), (7, 7))
        assert r_astar.nodes_expanded <= r_ucs.nodes_expanded


# ══════════════════════════════════════════════════════════════════════
# 4. Paths avoid restricted cells
# ══════════════════════════════════════════════════════════════════════

class TestRestrictedCells:
    def test_path_avoids_obstacles(self):
        # Wall with a gap at y=4 so the path can go around
        restricted = {(3, 0), (3, 1), (3, 2), (3, 3)}
        grid = create_grid(7, 6, restricted=restricted)
        result = astar_search(grid, (0, 0), (6, 0))
        assert result.success
        for pos in result.path:
            assert pos not in restricted

    def test_ucs_avoids_obstacles(self):
        restricted = {(2, 2), (3, 2), (4, 2)}
        grid = create_grid(6, 6, restricted=restricted)
        result = ucs_search(grid, (0, 2), (5, 2))
        assert result.success
        for pos in result.path:
            assert pos not in restricted


# ══════════════════════════════════════════════════════════════════════
# 5. Planner detects unreachable goals
# ══════════════════════════════════════════════════════════════════════

class TestUnreachable:
    def test_enclosed_goal_astar(self):
        grid, aircraft = scenario_unreachable()
        result = astar_search(grid, aircraft[0].start, aircraft[0].goal)
        assert not result.success
        assert result.failure_reason

    def test_enclosed_goal_ucs(self):
        grid, aircraft = scenario_unreachable()
        result = ucs_search(grid, aircraft[0].start, aircraft[0].goal)
        assert not result.success
        assert result.failure_reason


# ══════════════════════════════════════════════════════════════════════
# 6. Start equals goal
# ══════════════════════════════════════════════════════════════════════

class TestStartEqualsGoal:
    def test_astar_trivial(self):
        grid = _empty_grid()
        result = astar_search(grid, (3, 3), (3, 3))
        assert result.success
        assert result.path == [(3, 3)]
        assert result.cost == 0.0

    def test_ucs_trivial(self):
        grid = _empty_grid()
        result = ucs_search(grid, (3, 3), (3, 3))
        assert result.success
        assert result.path == [(3, 3)]
        assert result.cost == 0.0


# ══════════════════════════════════════════════════════════════════════
# 7. Invalid coordinates are rejected
# ══════════════════════════════════════════════════════════════════════

class TestInvalidCoordinates:
    def test_out_of_bounds_start(self):
        grid = _empty_grid(5, 5)
        result = astar_search(grid, (-1, 0), (4, 4))
        assert not result.success

    def test_out_of_bounds_goal(self):
        grid = _empty_grid(5, 5)
        result = astar_search(grid, (0, 0), (10, 10))
        assert not result.success

    def test_validation_catches_bad_config(self):
        grid = _empty_grid(5, 5)
        ac = Aircraft("AC-BAD", (-1, -1), (10, 10), priority=0)
        errors = validate_aircraft_config(grid, [ac])
        assert len(errors) >= 2  # at least start + goal errors


# ══════════════════════════════════════════════════════════════════════
# 8. Vertex conflicts are detected
# ══════════════════════════════════════════════════════════════════════

class TestVertexConflict:
    def test_same_cell_same_time(self):
        grid = _empty_grid(5, 5)
        ac1 = Aircraft("A", (0, 0), (2, 0), planned_path=[(0, 0), (1, 0), (2, 0)])
        ac2 = Aircraft("B", (0, 1), (2, 0), planned_path=[(0, 1), (1, 0), (2, 0)])
        conflicts = detect_conflicts([ac1, ac2], grid)
        vertex = [c for c in conflicts if c.conflict_type == ConflictType.VERTEX]
        assert len(vertex) >= 1
        assert vertex[0].time_step == 1  # conflict at (1,0) t=1


# ══════════════════════════════════════════════════════════════════════
# 9. Edge-swap conflicts are detected
# ══════════════════════════════════════════════════════════════════════

class TestEdgeSwapConflict:
    def test_swap_positions(self):
        grid = _empty_grid(5, 5)
        ac1 = Aircraft("A", (0, 0), (1, 0), planned_path=[(0, 0), (1, 0)])
        ac2 = Aircraft("B", (1, 0), (0, 0), planned_path=[(1, 0), (0, 0)])
        conflicts = detect_conflicts([ac1, ac2], grid)
        edge = [c for c in conflicts if c.conflict_type == ConflictType.EDGE_SWAP]
        assert len(edge) >= 1


# ══════════════════════════════════════════════════════════════════════
# 10. Time-dependent reservations are respected
# ══════════════════════════════════════════════════════════════════════

class TestReservations:
    def test_reserved_cell_avoided(self):
        grid = _empty_grid(5, 5)
        reserved = {(2, 0, 2)}  # cell (2,0) reserved at t=2
        result = astar_search(grid, (0, 0), (4, 0), reserved_cells=reserved)
        assert result.success
        # Path should not occupy (2,0) at t=2
        if len(result.path) > 2:
            assert result.path[2] != (2, 0)

    def test_reservation_table_basic(self):
        table = ReservationTable()
        path = [(0, 0), (1, 0), (2, 0)]
        ok = table.reserve_path("AC-1", path, max_time=10)
        assert ok
        assert table.is_cell_reserved((0, 0, 0))
        assert table.is_cell_reserved((1, 0, 1))
        assert table.is_cell_reserved((2, 0, 2))

    def test_reservation_conflict(self):
        table = ReservationTable()
        table.reserve_path("AC-1", [(0, 0), (1, 0), (2, 0)], max_time=10)
        # Try to reserve a conflicting path at t=1
        ok = table.reserve_path("AC-2", [(0, 1), (1, 0), (2, 1)], max_time=10)
        assert not ok  # (1,0) at t=1 already reserved

    def test_parking_reservation_persists_to_horizon(self):
        """Aircraft parked at their goal must reserve the goal cell through max_time."""
        table = ReservationTable()
        path = [(0, 0), (1, 0), (2, 0)]  # Arrives at (2,0) at t=2
        ok = table.reserve_path("AC-1", path, max_time=15)
        assert ok
        # Goal cell (2,0) must remain reserved for all t from arrival (2) to max_time (15)
        for t in range(2, 16):
            assert table.is_cell_reserved((2, 0, t))
            assert table.cell_owner((2, 0, t)) == "AC-1"

        # A second aircraft attempting to traverse or end at (2,0) at t=5 must be rejected
        conflicting_path = [(2, 2), (2, 1), (2, 0)]  # reaches (2,0) at t=2, but let's test t=5
        conflicting_at_t5 = [(1, 1)] * 5 + [(2, 0)]  # reaches (2,0) at t=5
        assert not table.reserve_path("AC-2", conflicting_at_t5, max_time=15)


# ══════════════════════════════════════════════════════════════════════
# 11. Waiting can resolve a corridor conflict
# ══════════════════════════════════════════════════════════════════════

class TestCorridorConflict:
    def test_corridor_all_aircraft_planned_and_conflict_free(self):
        grid, aircraft = scenario_narrow_corridor()
        events, conflicts, table, replan_count = plan_all_aircraft(
            grid, aircraft, algorithm="A*", max_time=50, max_replan_attempts=3,
        )
        planned = [ac for ac in aircraft if ac.status == AircraftStatus.PLANNED]
        # All aircraft must successfully plan
        assert len(planned) == len(aircraft)
        # Zero unresolved conflicts from coordinator
        assert len(conflicts) == 0
        # Independent conflict detector must confirm zero collisions
        final_conflicts = detect_conflicts(planned, grid)
        assert len(final_conflicts) == 0

    def test_corridor_forces_waiting(self):
        """The narrow corridor bottleneck must force lower-priority aircraft to wait their turn."""
        grid, aircraft = scenario_narrow_corridor()
        sim = Simulation(grid, aircraft, algorithm="A*", max_time=50)
        sim.plan()
        sim.run_full()
        m = sim.compute_metrics()
        assert m.aircraft_completed == len(aircraft)
        assert m.unresolved_conflicts == 0
        # Genuine queuing: waiting time must be strictly positive
        assert m.total_waiting_time > 0
        # Specifically, lower-priority aircraft AC-2 and AC-3 must have waited
        ac_map = {a.aircraft_id: a for a in sim.aircraft}
        assert ac_map["AC-1"].waiting_time == 0  # Priority 0 departs first with 0 waiting
        assert ac_map["AC-2"].waiting_time > 0   # Priority 1 must wait outside corridor
        assert ac_map["AC-3"].waiting_time > 0   # Priority 2 must wait even longer


# ══════════════════════════════════════════════════════════════════════
# 12. Final trajectories are conflict-free when planning succeeds
# ══════════════════════════════════════════════════════════════════════

class TestConflictFreeResult:
    def test_conflict_free_scenario(self):
        grid, aircraft = scenario_conflict_free()
        events, conflicts, table, _ = plan_all_aircraft(
            grid, aircraft, algorithm="A*",
        )
        assert len(conflicts) == 0
        planned = [ac for ac in aircraft if ac.planned_path]
        final_conflicts = detect_conflicts(planned, grid)
        assert len(final_conflicts) == 0

    def test_crossing_resolved(self):
        grid, aircraft = scenario_crossing()
        events, conflicts, table, _ = plan_all_aircraft(
            grid, aircraft, algorithm="A*",
        )
        assert len(conflicts) == 0
        planned = [ac for ac in aircraft if ac.planned_path]
        assert len(detect_conflicts(planned, grid)) == 0

    def test_five_aircraft_zero_conflicts(self):
        """Scenario 7 (Default 5 Aircraft) must produce zero conflicts under parking reservations."""
        grid, aircraft = scenario_five_aircraft()
        events, conflicts, table, _ = plan_all_aircraft(
            grid, aircraft, algorithm="A*", max_time=100,
        )
        assert len(conflicts) == 0
        planned = [ac for ac in aircraft if ac.planned_path]
        assert len(planned) == 5
        final_conflicts = detect_conflicts(planned, grid)
        assert len(final_conflicts) == 0

    def test_all_feasible_registry_scenarios_zero_conflicts(self):
        """All feasible scenarios in the registry must produce strictly 0 conflicts for A* and UCS."""
        for sname, (sfn, sdesc) in SCENARIO_REGISTRY.items():
            if sname == "3. Unreachable Destination":
                continue
            for algo in ["A*", "UCS"]:
                grid, aircraft = sfn()
                events, conflicts, table, _ = plan_all_aircraft(
                    grid, aircraft, algorithm=algo, max_time=100,
                )
                assert len(conflicts) == 0, f"Unresolved conflicts in {sname} ({algo}): {conflicts}"
                planned = [ac for ac in aircraft if ac.planned_path]
                detector_conflicts = detect_conflicts(planned, grid)
                assert len(detector_conflicts) == 0, f"Detector conflicts in {sname} ({algo}): {detector_conflicts}"


# ══════════════════════════════════════════════════════════════════════
# 13. Aircraft reach destinations when execution succeeds
# ══════════════════════════════════════════════════════════════════════

class TestSimulationExecution:
    def test_conflict_free_execution(self):
        grid, aircraft = scenario_conflict_free()
        sim = Simulation(grid, aircraft, algorithm="A*")
        sim.plan()
        sim.run_full()
        # Strictly assert that ALL aircraft completed and arrived at their exact goal
        assert len([ac for ac in sim.aircraft if ac.status == AircraftStatus.ARRIVED]) == len(aircraft)
        for ac in sim.aircraft:
            assert ac.status == AircraftStatus.ARRIVED
            assert ac.current_position == ac.goal
            assert ac.arrival_time is not None
            assert ac.executed_path == ac.planned_path

    def test_crossing_execution(self):
        grid, aircraft = scenario_crossing()
        sim = Simulation(grid, aircraft, algorithm="A*")
        sim.plan()
        sim.run_full()
        arrived = [ac for ac in sim.aircraft if ac.status == AircraftStatus.ARRIVED]
        assert len(arrived) == len(aircraft) == 2
        for ac in sim.aircraft:
            assert ac.status == AircraftStatus.ARRIVED
            assert ac.current_position == ac.goal
            assert ac.executed_path == ac.planned_path
        # One aircraft must have waited to resolve crossing conflict
        m = sim.compute_metrics()
        assert m.total_waiting_time >= 1
        assert m.unresolved_conflicts == 0
        assert m.conflicts_before_resolution >= 1

    def test_early_goal_visit_does_not_halt_early(self):
        """Bug 1: Aircraft visiting goal cell mid-plan must NOT stop early; must execute full path."""
        grid = _empty_grid(10, 10)
        # AC-1 has a plan that visits goal (3,4) at step 2, leaves to (4,4), and returns to (3,4) at step 7
        custom_path = [(2, 3), (3, 3), (3, 4), (3, 4), (3, 4), (4, 4), (4, 4), (3, 4)]
        ac = Aircraft("AC-1", start=(2, 3), goal=(3, 4), priority=0)
        ac.status = AircraftStatus.PLANNED
        ac.planned_path = custom_path
        ac.route_cost = 7.0

        sim = Simulation(grid, [ac], algorithm="A*")
        sim._has_planned = True
        sim.state = sim.state.READY
        sim.run_full()

        # Must not stop at step 2! Must execute all 7 steps to completion
        assert ac.status == AircraftStatus.ARRIVED
        assert ac.arrival_time == 7
        assert ac.executed_path == custom_path
        assert len(ac.executed_path) == 8

    def test_failed_aircraft_remains_reserved_as_obstacle(self):
        """Bug 3: Failed aircraft must not vanish; its start cell must remain reserved for all t."""
        grid = _empty_grid(6, 6)
        # Block AC-1's goal completely so AC-1 fails
        for nbr in [(4, 5), (5, 4)]:
            grid.restricted_cells.add(nbr)
        ac1 = Aircraft("AC-1", start=(2, 2), goal=(5, 5), priority=0)
        # AC-2 wants to fly straight through AC-1's start cell (2, 2)
        ac2 = Aircraft("AC-2", start=(0, 2), goal=(4, 2), priority=1)

        events, conflicts, table, replan_count = plan_all_aircraft(
            grid, [ac1, ac2], algorithm="A*", max_time=20, max_replan_attempts=1,
        )
        assert ac1.status == AircraftStatus.FAILED
        # AC-1's start cell (2, 2) must be reserved for all t
        for t in range(21):
            assert table.is_cell_reserved((2, 2, t))

        # If AC-2 successfully planned, its path must NOT pass through (2, 2)
        if ac2.status == AircraftStatus.PLANNED:
            for p in ac2.planned_path:
                assert p != (2, 2)

    def test_duplicate_goals_validation_error(self):
        """Bug 6: Duplicate goals must be caught by validation and reject planning."""
        grid = _empty_grid(8, 8)
        ac1 = Aircraft("AC-1", start=(0, 0), goal=(4, 4), priority=0)
        ac2 = Aircraft("AC-2", start=(0, 7), goal=(4, 4), priority=1)  # Duplicate goal (4, 4)

        errors = validate_aircraft_config(grid, [ac1, ac2])
        assert any("shared with another aircraft" in err and "goal" in err for err in errors)

        sim = Simulation(grid, [ac1, ac2])
        assert not sim.plan()
        assert sim.state.value == "failed"

    def test_run_before_plan_rejected(self):
        """Bug 7: run_full() before plan() must be cleanly rejected, not reported as success."""
        grid = _empty_grid(8, 8)
        ac1 = Aircraft("AC-1", start=(0, 0), goal=(4, 4), priority=0)
        sim = Simulation(grid, [ac1])
        # Call run_full directly without plan()
        sim.run_full()
        assert sim.state.value == "failed"
        assert any(e.description.startswith("Cannot run simulation") for e in sim.events)

    def test_start_inside_restricted_cell_fails(self):
        """Bug 5: A* and UCS must reject start in restricted cell even if start == goal."""
        grid = _empty_grid(5, 5)
        grid.restricted_cells.add((2, 2))
        res_astar = astar_search(grid, (2, 2), (2, 2))
        assert not res_astar.success
        assert "restricted" in res_astar.failure_reason or "invalid" in res_astar.failure_reason

        res_ucs = ucs_search(grid, (2, 2), (2, 2))
        assert not res_ucs.success
        assert "restricted" in res_ucs.failure_reason or "invalid" in res_ucs.failure_reason

    def test_execution_limit_marks_en_route_aircraft_failed(self):
        """Additional Bug: Aircraft truncated by execution step limit must be marked FAILED."""
        grid = _empty_grid(10, 10)
        # Create aircraft with long route (cost 18) but restrict execution limit to 5 steps
        ac = Aircraft("AC-1", start=(0, 0), goal=(9, 9), priority=0)
        sim = Simulation(grid, [ac], algorithm="A*", max_execution_steps=5)
        sim.plan()
        sim.run_full()
        assert sim.state.value == "failed"
        assert ac.status == AircraftStatus.FAILED
        m = sim.compute_metrics()
        assert m.aircraft_failed == 1
        assert m.aircraft_completed == 0

    def test_json_scenarios_load_and_match(self):
        """Verify data/scenarios.json loads all scenarios cleanly."""
        from src.scenarios import load_scenarios_from_json
        scenarios = load_scenarios_from_json("data/scenarios.json")
        assert len(scenarios) == 7
        assert "1. Conflict-Free Routes" in scenarios
        assert "4. Narrow Corridor" in scenarios
        for name, (g, acs) in scenarios.items():
            assert g.width > 0 and g.height > 0
            assert len(acs) >= 1

    def test_bounded_replanning_resolves_failure(self):
        """Bug 2: Replanning must trigger when an aircraft fails under initial priority order."""
        grid = GridConfig(width=5, height=2, restricted_cells={(2, 1), (3, 1)})
        # Under priority [AC-1, AC-2], AC-2 fails due to corridor contention.
        # Under priority [AC-2, AC-1], both succeed conflict-free.
        ac1 = Aircraft("AC-1", start=(1, 0), goal=(4, 0), priority=0)
        ac2 = Aircraft("AC-2", start=(2, 0), goal=(0, 1), priority=1)

        events, conflicts, table, replan_count = plan_all_aircraft(
            grid, [ac1, ac2], algorithm="A*", max_time=15, max_replan_attempts=2,
        )
        # Bounded replanning must have triggered and incremented replan_count
        assert replan_count >= 1
        # Both aircraft must now be successfully planned
        assert ac1.status == AircraftStatus.PLANNED
        assert ac2.status == AircraftStatus.PLANNED
        assert len(conflicts) == 0


# ══════════════════════════════════════════════════════════════════════
# 14. Safety invariants hold after every simulation step
# ══════════════════════════════════════════════════════════════════════

class TestSafetyInvariants:
    def test_no_collision_during_execution(self):
        grid, aircraft = scenario_conflict_free()
        sim = Simulation(
            grid,
            [Aircraft(a.aircraft_id, a.start, a.goal, a.priority, a.color)
             for a in aircraft],
            algorithm="A*",
        )
        sim.plan()
        sim.run_full()
        # Check planned paths are conflict free
        planned = [ac for ac in sim.aircraft if ac.planned_path]
        conflicts = detect_conflicts(planned, grid)
        assert len(conflicts) == 0
        # All arrived aircraft should be at their goal
        for ac in sim.aircraft:
            if ac.status == AircraftStatus.ARRIVED:
                assert ac.current_position == ac.goal


# ══════════════════════════════════════════════════════════════════════
# 15. Failure cases are reported accurately
# ══════════════════════════════════════════════════════════════════════

class TestFailureReporting:
    def test_unreachable_reports_failure(self):
        grid, aircraft = scenario_unreachable()
        sim = Simulation(grid, aircraft, algorithm="A*")
        sim.plan()
        failed = [ac for ac in sim.aircraft if ac.status == AircraftStatus.FAILED]
        assert len(failed) >= 1
        for ac in failed:
            assert ac.search_result is not None
            assert not ac.search_result.success
            assert ac.search_result.failure_reason


# ══════════════════════════════════════════════════════════════════════
# 16. Identical seeds reproduce the same scenario
# ══════════════════════════════════════════════════════════════════════

class TestReproducibility:
    def test_deterministic_scenario(self):
        grid1, ac1 = scenario_crossing()
        grid2, ac2 = scenario_crossing()

        r1 = astar_search(grid1, ac1[0].start, ac1[0].goal)
        r2 = astar_search(grid2, ac2[0].start, ac2[0].goal)

        assert r1.path == r2.path
        assert r1.cost == r2.cost
        assert r1.nodes_expanded == r2.nodes_expanded


# ══════════════════════════════════════════════════════════════════════
# Additional: Metrics computation
# ══════════════════════════════════════════════════════════════════════

class TestMetrics:
    def test_metrics_computed(self):
        grid, aircraft = scenario_conflict_free()
        sim = Simulation(grid, aircraft, algorithm="A*")
        sim.plan()
        sim.run_full()
        metrics = sim.compute_metrics()
        assert metrics.aircraft_completed >= 1
        assert metrics.total_route_cost > 0
        assert metrics.algorithm_used == "A*"


# ══════════════════════════════════════════════════════════════════════
# Additional: Environment helpers
# ══════════════════════════════════════════════════════════════════════

class TestEnvironment:
    def test_neighbors_center(self):
        grid = _empty_grid(5, 5)
        nbrs = get_neighbors(grid, (2, 2), include_wait=False)
        assert len(nbrs) == 4

    def test_neighbors_corner(self):
        grid = _empty_grid(5, 5)
        nbrs = get_neighbors(grid, (0, 0), include_wait=False)
        assert len(nbrs) == 2

    def test_neighbors_include_wait(self):
        grid = _empty_grid(5, 5)
        nbrs = get_neighbors(grid, (2, 2), include_wait=True)
        assert (2, 2) in nbrs

    def test_grid_bounds(self):
        grid = _empty_grid(5, 5)
        assert grid.in_bounds((0, 0))
        assert grid.in_bounds((4, 4))
        assert not grid.in_bounds((-1, 0))
        assert not grid.in_bounds((5, 0))

    def test_heuristic(self):
        assert manhattan_distance((0, 0), (3, 4)) == 7.0
        assert manhattan_distance((5, 5), (5, 5)) == 0.0


# ══════════════════════════════════════════════════════════════════════
# 17. Evaluator bug fix regression tests
# ══════════════════════════════════════════════════════════════════════

class TestReviewerBugFixes:
    def test_run_full_idempotent_on_completed(self):
        """Bug 1: Calling run_full() twice must be an idempotent no-op, not flip to FAILED."""
        grid, aircraft = scenario_conflict_free()
        sim = Simulation(grid, aircraft, algorithm="A*")
        sim.plan()
        sim.run_full()
        assert sim.state.value == "completed"
        event_count = len(sim.events)
        sim.run_full()
        assert sim.state.value == "completed"
        assert len(sim.events) == event_count

    def test_run_full_on_failed_plan_has_distinct_message(self):
        """Bug 1: run_full() after plan() failure must report route planning failure, not missing plan."""
        grid, aircraft = scenario_unreachable()
        sim = Simulation(grid, aircraft, algorithm="A*")
        sim.plan()
        assert sim.state.value == "failed"
        sim.run_full()
        assert any("route planning failed to find valid routes" in e.description for e in sim.events)
        assert not any("routes have not been planned" in e.description for e in sim.events)

    def test_max_replan_attempts_zero_does_not_crash(self):
        """Bug 2: max_replan_attempts=0 must execute base ordering without TypeError."""
        grid, aircraft = scenario_conflict_free()
        events, conflicts, table, replan_count = plan_all_aircraft(
            grid, aircraft, algorithm="A*", max_replan_attempts=0,
        )
        assert replan_count == 0
        assert len(conflicts) == 0

    def test_start_equals_goal_with_future_reservation_maneuvers(self):
        """Bug 3: Start == goal with future reservation must fall through to search and maneuver safely."""
        grid = _empty_grid(5, 5)
        # (2, 2) is reserved at t=2
        reserved = {(2, 2, 2)}
        res_astar = astar_search(grid, (2, 2), (2, 2), reserved_cells=reserved, max_time=10)
        assert res_astar.success
        assert res_astar.cost > 0.0
        assert len(res_astar.path) >= 3

        res_ucs = ucs_search(grid, (2, 2), (2, 2), reserved_cells=reserved, max_time=10)
        assert res_ucs.success
        assert res_ucs.cost > 0.0
        assert len(res_ucs.path) >= 3

    def test_plan_returns_false_and_blocks_run_when_unresolved_conflicts(self):
        """Bug 4: plan() must return False and block run_full() when unresolved conflicts remain."""
        grid = GridConfig(width=6, height=1, restricted_cells=set())
        ac1 = Aircraft("A", (0, 0), (5, 0), 0)
        ac2 = Aircraft("B", (5, 0), (0, 0), 1)
        sim = Simulation(grid, [ac1, ac2], algorithm="A*", max_time=20, max_replan_attempts=2)
        ok = sim.plan()
        assert not ok
        assert sim.state.value == "failed"
        assert len(sim.unresolved_conflicts) > 0
        sim.run_full()
        assert sim.state.value == "failed"

    def test_reorderings_rotate_top_priority(self):
        """Bug 5: Bounded replanning orderings must rotate top priority across agents."""
        from src.coordinator import _generate_orderings
        aircraft = [Aircraft(f"AC-{i}", (0, i), (9, i), i) for i in range(1, 6)]
        orderings = _generate_orderings(aircraft, max_orderings=5)
        leading_ids = [order[0].aircraft_id for order in orderings]
        assert len(set(leading_ids)) >= 4
        assert leading_ids[0] == "AC-1"
        assert leading_ids[1] == "AC-2"
        assert leading_ids[2] == "AC-3"

    def test_duplicate_aircraft_id_rejected(self):
        """Bug 6: validate_aircraft_config must flag duplicate aircraft IDs."""
        grid = _empty_grid(8, 8)
        ac1 = Aircraft("AC-1", start=(0, 0), goal=(4, 4), priority=0)
        ac2 = Aircraft("AC-1", start=(1, 1), goal=(5, 5), priority=1)
        errors = validate_aircraft_config(grid, [ac1, ac2])
        assert any("duplicate aircraft id" in err.lower() for err in errors)

    def test_failed_aircraft_clears_planned_path(self):
        """Bug 7: Failed aircraft must have planned_path cleared to empty list."""
        grid = _empty_grid(6, 6)
        for p in [(4, 5), (5, 4)]:
            grid.restricted_cells.add(p)
        ac = Aircraft("AC-1", start=(0, 0), goal=(5, 5), priority=0)
        events, conflicts, table, _ = plan_all_aircraft(grid, [ac], algorithm="A*", max_time=10)
        assert ac.status == AircraftStatus.FAILED
        assert ac.planned_path == []
        assert ac.route_cost == 0.0

    def test_partial_flight_plan_proceeds_if_zero_conflicts(self):
        """Remaining Bug 1: Conflict-free planned flights must execute even if an isolated flight fails."""
        grid = _empty_grid(8, 8)
        # Block destination of AC-2 completely so AC-2 fails
        grid.restricted_cells.add((7, 6))
        grid.restricted_cells.add((6, 7))
        ac1 = Aircraft("AC-1", start=(0, 0), goal=(4, 0), priority=0)
        ac2 = Aircraft("AC-2", start=(0, 7), goal=(7, 7), priority=1)
        sim = Simulation(grid, [ac1, ac2], algorithm="A*")
        ok = sim.plan()
        assert ok  # Succeeded because zero conflicts exist and AC-1 planned
        assert sim.state.value == "ready"
        sim.run_full()
        assert sim.state.value == "completed"
        assert ac1.status == AircraftStatus.ARRIVED
        assert ac2.status == AircraftStatus.FAILED
        assert ac1.executed_path == ac1.planned_path

    def test_repeated_run_full_does_not_duplicate_events(self):
        """Remaining Bug 2: Repeated run_full() calls on failed simulation must not spam duplicate events."""
        # 1. Failure at plan time
        grid, aircraft = scenario_unreachable()
        sim = Simulation(grid, aircraft, algorithm="A*")
        sim.plan()
        sim.run_full()
        count1 = len(sim.events)
        sim.run_full()
        sim.run_full()
        assert len(sim.events) == count1  # Zero duplicate events added

        # 2. Failure at execution limit
        grid2, aircraft2 = scenario_conflict_free()
        sim2 = Simulation(grid2, aircraft2, algorithm="A*", max_execution_steps=2)
        sim2.plan()
        sim2.run_full()
        assert sim2.state.value == "failed"
        count2 = len(sim2.events)
        sim2.run_full()
        sim2.run_full()
        assert len(sim2.events) == count2  # Zero duplicate events added

    def test_shared_start_goal_endpoint_warning_flagged(self):
        """Remaining Bug 3: Shared start/goal endpoints across flights must be flagged with a warning."""
        grid = _empty_grid(8, 8)
        ac1 = Aircraft("A", start=(0, 0), goal=(3, 3), priority=0)
        ac2 = Aircraft("B", start=(3, 3), goal=(5, 5), priority=1)
        msgs = validate_aircraft_config(grid, [ac1, ac2])
        assert any("warning" in m.lower() and "coincides with" in m.lower() for m in msgs)
        sim = Simulation(grid, [ac1, ac2], algorithm="A*")
        sim.plan()
        assert any("Validation: Warning:" in e.description for e in sim.events)

    def test_plan_then_run_full_called_again_on_same_instance(self):
        """Calling plan() then run_full() a second time on the same Simulation object must work cleanly."""
        grid, aircraft = scenario_conflict_free()
        sim = Simulation(grid, aircraft, algorithm="A*")
        # First execution
        assert sim.plan()
        sim.run_full()
        assert sim.state.value == "completed"
        for ac in sim.aircraft:
            assert ac.status == AircraftStatus.ARRIVED

        # Second execution on same instance
        assert sim.plan()
        assert sim.current_step == 0
        sim.run_full()
        assert sim.state.value == "completed"
        for ac in sim.aircraft:
            assert ac.status == AircraftStatus.ARRIVED


# ══════════════════════════════════════════════════════════════════════
# 18. Search expansion tracing and conflict metrics tests (Review Part A4)
# ══════════════════════════════════════════════════════════════════════

class TestExpansionTracingAndNewMetrics:
    def test_trace_empty_by_default_and_non_empty_when_enabled(self):
        """Trace must be empty by default, and non-empty when record_trace=True."""
        grid, aircraft = scenario_conflict_free()
        
        # Default: record_trace=False
        sim_default = Simulation(grid, aircraft, algorithm="A*")
        sim_default.plan()
        for ac in sim_default.aircraft:
            assert ac.search_result is not None
            assert len(ac.search_result.expansion_trace) == 0

        # Enabled: record_trace=True
        sim_traced = Simulation(grid, aircraft, algorithm="A*", record_trace=True)
        sim_traced.plan()
        for ac in sim_traced.aircraft:
            assert ac.search_result is not None
            assert len(ac.search_result.expansion_trace) > 0

    def test_trace_length_equals_nodes_expanded_conflict_free_and_reservations(self):
        """len(expansion_trace) == nodes_expanded for A* and UCS on conflict-free and reservation cases."""
        # Case 1: Conflict-free (Scenario 1)
        for algo in ["A*", "UCS"]:
            grid, aircraft = scenario_conflict_free()
            sim = Simulation(grid, aircraft, algorithm=algo, record_trace=True)
            assert sim.plan()
            for ac in sim.aircraft:
                assert ac.search_result is not None
                assert len(ac.search_result.expansion_trace) == ac.search_result.nodes_expanded

        # Case 2: Reservations present (Scenario 2 Crossing)
        for algo in ["A*", "UCS"]:
            grid, aircraft = scenario_crossing()
            sim = Simulation(grid, aircraft, algorithm=algo, record_trace=True)
            assert sim.plan()
            for ac in sim.aircraft:
                assert ac.search_result is not None
                assert len(ac.search_result.expansion_trace) == ac.search_result.nodes_expanded

    def test_first_trace_entry_and_monotonicity(self):
        """First trace entry is start state at t=0. A* f-values and UCS g-values never decrease."""
        grid, aircraft = scenario_crossing()

        # A* check
        sim_a = Simulation(grid, aircraft, algorithm="A*", record_trace=True)
        sim_a.plan()
        for ac in sim_a.aircraft:
            trace = ac.search_result.expansion_trace
            assert len(trace) > 0
            # First entry is start state at t=0
            assert trace[0].state == (ac.start[0], ac.start[1], 0)
            assert trace[0].step == 1
            # f-values non-decreasing
            for i in range(len(trace) - 1):
                assert trace[i].f <= trace[i + 1].f, f"A* f decreased from step {i+1} to {i+2}"

        # UCS check
        grid_u, aircraft_u = scenario_crossing()
        sim_u = Simulation(grid_u, aircraft_u, algorithm="UCS", record_trace=True)
        sim_u.plan()
        for ac in sim_u.aircraft:
            trace = ac.search_result.expansion_trace
            assert len(trace) > 0
            # First entry is start state at t=0
            assert trace[0].state == (ac.start[0], ac.start[1], 0)
            assert trace[0].step == 1
            # g-values non-decreasing
            for i in range(len(trace) - 1):
                assert trace[i].g <= trace[i + 1].g, f"UCS g decreased from step {i+1} to {i+2}"

    def test_trace_determinism(self):
        """Tracing twice on the same scenario produces an identical sequence of expansions."""
        grid1, ac1 = scenario_crossing()
        sim1 = Simulation(grid1, ac1, algorithm="A*", record_trace=True)
        sim1.plan()
        ac2_run1 = next(a for a in sim1.aircraft if a.aircraft_id == "AC-2")

        grid2, ac2 = scenario_crossing()
        sim2 = Simulation(grid2, ac2, algorithm="A*", record_trace=True)
        sim2.plan()
        ac2_run2 = next(a for a in sim2.aircraft if a.aircraft_id == "AC-2")

        trace1 = ac2_run1.search_result.expansion_trace
        trace2 = ac2_run2.search_result.expansion_trace
        assert len(trace1) == len(trace2)
        for r1, r2 in zip(trace1, trace2):
            assert r1.step == r2.step
            assert r1.state == r2.state
            assert r1.g == r2.g
            assert r1.h == r2.h
            assert r1.f == r2.f
            assert r1.blocked_successors == r2.blocked_successors

    def test_comparison_table_columns_and_no_conflicts_column(self):
        """comparison_table has the two new conflict column names and no 'Conflicts' column."""
        from src.models import ComparisonRow
        from src.metrics import comparison_table

        rows = [
            ComparisonRow(
                scenario_name="Test",
                algorithm="A*",
                success=True,
                path_cost=10.0,
                nodes_expanded=10,
                nodes_generated=20,
                runtime_ms=1.0,
                waiting_time=0,
                makespan=5,
                conflicts_before=2,
                conflicts_unresolved=0,
            )
        ]
        df = comparison_table(rows)
        assert "Conflicts Before Coordination" in df.columns
        assert "Unresolved Conflicts After Coordination" in df.columns
        assert "Conflicts" not in df.columns

    def test_scenario3_cost_na_and_scenario5_zero(self):
        """Scenario 3 has path cost N/A and Scenario 5 has 0.0 in the comparison output."""
        from src.models import ComparisonRow
        from src.metrics import comparison_table

        # Scenario 3: Unreachable destination
        g3, ac3 = scenario_unreachable()
        sim3 = Simulation(g3, ac3, algorithm="A*")
        sim3.plan()
        sim3.run_full()
        m3 = sim3.compute_metrics()
        c3_cost = None if (m3.aircraft_completed == 0 and m3.aircraft_failed > 0) else m3.total_route_cost

        # Scenario 5: Start equals goal
        g5, ac5 = scenario_start_equals_goal()
        sim5 = Simulation(g5, ac5, algorithm="A*")
        sim5.plan()
        sim5.run_full()
        m5 = sim5.compute_metrics()
        c5_cost = None if (m5.aircraft_completed == 0 and m5.aircraft_failed > 0) else m5.total_route_cost

        row3 = ComparisonRow(
            scenario_name="3. Unreachable Destination",
            algorithm="A*",
            success=sim3.state.value == "completed",
            path_cost=c3_cost,
            nodes_expanded=m3.total_nodes_expanded,
            nodes_generated=m3.total_nodes_generated,
            runtime_ms=m3.total_search_runtime_ms,
            waiting_time=None if c3_cost is None else m3.total_waiting_time,
            makespan=None if c3_cost is None else m3.makespan,
            conflicts_before=m3.conflicts_before_resolution,
            conflicts_unresolved=m3.unresolved_conflicts,
        )
        row5 = ComparisonRow(
            scenario_name="5. Start Equals Goal",
            algorithm="A*",
            success=True,
            path_cost=c5_cost,
            nodes_expanded=m5.total_nodes_expanded,
            nodes_generated=m5.total_nodes_generated,
            runtime_ms=m5.total_search_runtime_ms,
            waiting_time=m5.total_waiting_time,
            makespan=m5.makespan,
            conflicts_before=m5.conflicts_before_resolution,
            conflicts_unresolved=m5.unresolved_conflicts,
        )

        df = comparison_table([row3, row5])
        s3_row = df[df["Scenario"].str.contains("Unreachable")].iloc[0]
        s5_row = df[df["Scenario"].str.contains("Start Equals Goal")].iloc[0]

        assert s3_row["Path Cost"] == "N/A"
        assert s3_row["Waiting Time"] == "N/A"
        assert s3_row["Makespan"] == "N/A"
        assert s5_row["Path Cost"] == 0.0

    def test_scenario7_totals_astar_90_ucs_89(self):
        """Scenario 7 totals are strictly preserved: A* cost 90.0, UCS cost 89.0."""
        # A*
        g7_a, ac7_a = scenario_five_aircraft()
        sim_a = Simulation(g7_a, ac7_a, algorithm="A*")
        assert sim_a.plan()
        sim_a.run_full()
        m_a = sim_a.compute_metrics()
        assert m_a.total_route_cost == 90.0

        # UCS
        g7_u, ac7_u = scenario_five_aircraft()
        sim_u = Simulation(g7_u, ac7_u, algorithm="UCS")
        assert sim_u.plan()
        sim_u.run_full()
        m_u = sim_u.compute_metrics()
        assert m_u.total_route_cost == 89.0


