"""
coordinator.py — Multi-agent coordination using prioritized space-time planning.

Plans aircraft in priority order, reserving space-time positions
progressively.  If conflicts remain after initial planning, the
coordinator tries alternative priority orders and bounded replanning.

Limitation: prioritized planning is not guaranteed to find a solution
for every feasible multi-agent problem.
"""

from __future__ import annotations

import itertools
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.conflict_detection import detect_conflicts
from src.models import (
    Aircraft,
    AircraftStatus,
    Conflict,
    ConflictType,
    EventType,
    GridConfig,
    SearchResult,
    SimulationEvent,
)
from src.reservations import ReservationTable
from src.search import astar_search, ucs_search


# Type for a search function matching the signature of astar_search / ucs_search
SearchFn = Callable[..., SearchResult]


def _get_search_fn(algorithm: str) -> SearchFn:
    if algorithm.upper() in ("A*", "ASTAR"):
        return astar_search
    elif algorithm.upper() == "UCS":
        return ucs_search
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


def plan_all_aircraft(
    grid: GridConfig,
    aircraft_list: List[Aircraft],
    algorithm: str = "A*",
    max_time: int = 100,
    max_replan_attempts: int = 3,
    record_trace: bool = False,
) -> Tuple[List[SimulationEvent], List[Conflict], ReservationTable, int]:
    """
    Coordinate planning for all aircraft using prioritized space-time planning.

    Parameters
    ----------
    grid : GridConfig
    aircraft_list : list of Aircraft
        Modified in-place (planned_path, search_result, status, route_cost).
    algorithm : str
        "A*" or "UCS".
    max_time : int
        Planning horizon in time steps.
    max_replan_attempts : int
        How many different priority orderings to try if conflicts remain.
    record_trace : bool
        If True, record step-by-step expansion trace for each aircraft's search.

    Returns
    -------
    events : list of SimulationEvent
    conflicts : list of Conflict — unresolved conflicts (ideally empty).
    reservation_table : ReservationTable
    replan_count : int
    """
    search_fn = _get_search_fn(algorithm)
    events: List[SimulationEvent] = []
    best_result = None
    best_score = None
    replan_count = 0

    cumulative_nodes_expanded = 0
    cumulative_nodes_generated = 0
    cumulative_runtime_ms = 0.0

    # Generate priority orderings to try
    orderings = _generate_orderings(aircraft_list, max_replan_attempts)
    reorder_events: List[SimulationEvent] = []

    for ordering_idx, order in enumerate(orderings):
        table = ReservationTable()
        attempt_events: List[SimulationEvent] = []
        all_ok = True

        if ordering_idx > 0:
            replan_count += 1
            re_evt = SimulationEvent(
                time_step=0,
                aircraft_id=None,
                event_type=EventType.PRIORITY_REORDER,
                position=None,
                description=f"Trying priority order #{ordering_idx + 1}: {[a.aircraft_id for a in order]}",
            )
            attempt_events.append(re_evt)
            reorder_events.append(re_evt)

        # Reset aircraft
        for ac in aircraft_list:
            ac.reset()

        for ac in order:
            reserved_cells = table.get_reserved_cells()
            reserved_edges = table.get_reserved_edges()

            result = search_fn(
                grid=grid,
                start=ac.start,
                goal=ac.goal,
                reserved_cells=reserved_cells,
                reserved_edges=reserved_edges,
                max_time=max_time,
                record_trace=record_trace,
            )
            ac.search_result = result
            cumulative_nodes_expanded += result.nodes_expanded
            cumulative_nodes_generated += result.nodes_generated
            cumulative_runtime_ms += result.runtime_ms

            if result.success:
                ac.planned_path = result.path
                ac.route_cost = result.cost
                ac.status = AircraftStatus.PLANNED

                ok = table.reserve_path(ac.aircraft_id, result.path, max_time=max_time)
                if not ok:
                    ac.status = AircraftStatus.FAILED
                    ac.planned_path = []
                    ac.route_cost = 0.0
                    all_ok = False
                    # Reserve start cell for failed aircraft across entire horizon so it doesn't vanish
                    for t in range(0, max_time + 1):
                        table.reserve_cell(ac.aircraft_id, ac.start[0], ac.start[1], t)
                    attempt_events.append(SimulationEvent(
                        time_step=0,
                        aircraft_id=ac.aircraft_id,
                        event_type=EventType.RESERVATION_REJECTED,
                        position=ac.start,
                        description=f"Reservation rejected for {ac.aircraft_id} despite successful search.",
                    ))
                else:
                    attempt_events.append(SimulationEvent(
                        time_step=0,
                        aircraft_id=ac.aircraft_id,
                        event_type=EventType.ROUTE_PLANNED,
                        position=ac.start,
                        description=(
                            f"Route planned for {ac.aircraft_id}: cost={result.cost}, "
                            f"length={len(result.path)}, expanded={result.nodes_expanded}"
                        ),
                    ))
            else:
                ac.status = AircraftStatus.FAILED
                ac.planned_path = []
                ac.route_cost = 0.0
                all_ok = False
                # Reserve start cell for failed aircraft across entire horizon so it doesn't vanish
                for t in range(0, max_time + 1):
                    table.reserve_cell(ac.aircraft_id, ac.start[0], ac.start[1], t)
                attempt_events.append(SimulationEvent(
                    time_step=0,
                    aircraft_id=ac.aircraft_id,
                    event_type=EventType.PLANNING_FAILED,
                    position=ac.start,
                    description=f"Planning failed for {ac.aircraft_id}: {result.failure_reason}",
                ))

        # Validate with independent conflict detector checking ALL aircraft (including failed stationary)
        conflicts = detect_conflicts(aircraft_list, grid)

        num_planned = sum(1 for ac in aircraft_list if ac.status == AircraftStatus.PLANNED)
        total_cost = sum(ac.route_cost for ac in aircraft_list if ac.status == AircraftStatus.PLANNED)
        attempt_score = (num_planned, -len(conflicts), -total_cost)

        # Snapshot aircraft states for this attempt
        snapshot = {
            ac.aircraft_id: {
                "status": ac.status,
                "planned_path": list(ac.planned_path),
                "route_cost": ac.route_cost,
                "search_result": ac.search_result,
                "waiting_time": ac.waiting_time,
                "executed_path": list(ac.executed_path),
                "current_position": ac.current_position,
                "arrival_time": ac.arrival_time,
            }
            for ac in aircraft_list
        }

        # Keep the best attempt
        if best_result is None or attempt_score > best_score:
            best_score = attempt_score
            best_result = (attempt_events, conflicts, table, snapshot)

        # Attach cumulative stats to reservation table
        table.cumulative_nodes_expanded = cumulative_nodes_expanded
        table.cumulative_nodes_generated = cumulative_nodes_generated
        table.cumulative_runtime_ms = cumulative_runtime_ms

        # Complete success: ALL aircraft planned and NO conflicts detected
        if all_ok and not conflicts:
            for r_evt in reorder_events:
                if r_evt not in attempt_events:
                    events.append(r_evt)
            events.extend(attempt_events)
            if ordering_idx > 0:
                events.append(SimulationEvent(
                    time_step=0,
                    aircraft_id=None,
                    event_type=EventType.CONFLICT_RESOLVED,
                    position=None,
                    description=f"All conflicts resolved and all aircraft planned with priority order #{ordering_idx + 1}.",
                ))
            table.cumulative_nodes_expanded = cumulative_nodes_expanded
            table.cumulative_nodes_generated = cumulative_nodes_generated
            table.cumulative_runtime_ms = cumulative_runtime_ms
            return events, [], table, replan_count

    # If no ordering planned all aircraft conflict-free, restore state to best attempt
    best_events, best_conflicts, best_table, best_snapshot = best_result  # type: ignore
    for ac in aircraft_list:
        data = best_snapshot[ac.aircraft_id]
        ac.status = data["status"]
        ac.planned_path = list(data["planned_path"])
        ac.route_cost = data["route_cost"]
        ac.search_result = data["search_result"]
        ac.waiting_time = data["waiting_time"]
        ac.executed_path = list(data["executed_path"])
        ac.current_position = data["current_position"]
        ac.arrival_time = data["arrival_time"]

    for r_evt in reorder_events:
        if r_evt not in best_events:
            events.append(r_evt)
    events.extend(best_events)
    if best_conflicts:
        for c in best_conflicts:
            events.append(SimulationEvent(
                time_step=c.time_step,
                aircraft_id=c.aircraft_a,
                event_type=EventType.CONFLICT_DETECTED,
                position=c.position_a,
                description=c.description,
            ))
    best_table.cumulative_nodes_expanded = cumulative_nodes_expanded
    best_table.cumulative_nodes_generated = cumulative_nodes_generated
    best_table.cumulative_runtime_ms = cumulative_runtime_ms
    return events, best_conflicts, best_table, replan_count


def _generate_orderings(
    aircraft_list: List[Aircraft],
    max_orderings: int,
) -> List[List[Aircraft]]:
    """
    Generate diverse priority orderings to try.

    1. Base ordering: sorted by (priority, aircraft_id).
    2. Cyclic rotations: base[k:] + base[:k] so every aircraft takes a turn at highest priority.
    3. Reversal and reverse rotations.
    4. Distinct permutations if more orderings are requested.
    """
    limit = max(1, max_orderings)
    base = sorted(aircraft_list, key=lambda a: (a.priority, a.aircraft_id))
    orderings: List[List[Aircraft]] = [base]
    if limit == 1:
        return orderings

    seen = {tuple(a.aircraft_id for a in base)}

    # 1. Cyclic rotations so every aircraft gets a turn at top priority
    for i in range(1, len(base)):
        rot = base[i:] + base[:i]
        key = tuple(a.aircraft_id for a in rot)
        if key not in seen:
            seen.add(key)
            orderings.append(rot)
            if len(orderings) >= limit:
                return orderings[:limit]

    # 2. Reversal and reverse rotations
    rev = list(reversed(base))
    key_rev = tuple(a.aircraft_id for a in rev)
    if key_rev not in seen:
        seen.add(key_rev)
        orderings.append(rev)
        if len(orderings) >= limit:
            return orderings[:limit]

    for i in range(1, len(rev)):
        rot = rev[i:] + rev[:i]
        key = tuple(a.aircraft_id for a in rot)
        if key not in seen:
            seen.add(key)
            orderings.append(rot)
            if len(orderings) >= limit:
                return orderings[:limit]

    # 3. Permutations if still under limit
    for perm in itertools.permutations(base):
        perm_list = list(perm)
        key = tuple(a.aircraft_id for a in perm_list)
        if key not in seen:
            seen.add(key)
            orderings.append(perm_list)
            if len(orderings) >= limit:
                break

    return orderings[:limit]
