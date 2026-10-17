"""
conflict_detection.py — Independent trajectory conflict checker.

Validates a set of planned trajectories for vertex conflicts,
edge-swap conflicts, restricted-cell violations, and invalid moves.
This module is independent of the reservation table and serves as
a safety check after planning.
"""

from __future__ import annotations

from typing import Dict, List

from src.models import Aircraft, Conflict, ConflictType, GridConfig, Position


def detect_conflicts(
    aircraft_list: List[Aircraft],
    grid: GridConfig,
) -> List[Conflict]:
    """
    Check all planned paths for conflicts.

    Parameters
    ----------
    aircraft_list : list of Aircraft
        Each aircraft must have a non-empty ``planned_path``.
    grid : GridConfig
        The airspace grid (for restricted-cell and bounds checks).

    Returns
    -------
    list of Conflict
    """
    conflicts: List[Conflict] = []

    # Build a map: time_step -> list of (aircraft_id, position)
    max_t = max((len(ac.planned_path) for ac in aircraft_list if ac.planned_path), default=0)

    # Helper to get position at time t (aircraft stays at last position after arriving)
    def pos_at(ac: Aircraft, t: int) -> Position:
        if not ac.planned_path:
            return ac.start
        if t < len(ac.planned_path):
            return ac.planned_path[t]
        return ac.planned_path[-1]

    # Check all aircraft in the scenario (failed or unrouted aircraft remain at start)
    for t in range(max_t):
        positions: Dict[Position, List[str]] = {}
        for ac in aircraft_list:
            p = pos_at(ac, t)
            positions.setdefault(p, []).append(ac.aircraft_id)
        for pos, ids in positions.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.VERTEX,
                            time_step=t,
                            aircraft_a=ids[i],
                            aircraft_b=ids[j],
                            position_a=pos,
                            position_b=pos,
                            description=(
                                f"Vertex conflict at {pos}, t={t}: "
                                f"{ids[i]} and {ids[j]}"
                            ),
                        ))

    # Filter to aircraft that have planned paths for edge and path checks
    planned = [ac for ac in aircraft_list if ac.planned_path]

    # --- Edge-swap conflicts ---
    for t in range(max_t - 1):
        for i, ac_a in enumerate(planned):
            for ac_b in planned[i + 1:]:
                a_from = pos_at(ac_a, t)
                a_to = pos_at(ac_a, t + 1)
                b_from = pos_at(ac_b, t)
                b_to = pos_at(ac_b, t + 1)
                if a_from == b_to and a_to == b_from:
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.EDGE_SWAP,
                        time_step=t,
                        aircraft_a=ac_a.aircraft_id,
                        aircraft_b=ac_b.aircraft_id,
                        position_a=a_from,
                        position_b=b_from,
                        description=(
                            f"Edge-swap conflict at t={t}: "
                            f"{ac_a.aircraft_id} {a_from}->{a_to}, "
                            f"{ac_b.aircraft_id} {b_from}->{b_to}"
                        ),
                    ))

    # --- Restricted-cell violations ---
    for ac in planned:
        for t, pos in enumerate(ac.planned_path):
            if pos in grid.restricted_cells:
                conflicts.append(Conflict(
                    conflict_type=ConflictType.RESTRICTED,
                    time_step=t,
                    aircraft_a=ac.aircraft_id,
                    aircraft_b="",
                    position_a=pos,
                    description=(
                        f"Restricted-cell violation: {ac.aircraft_id} at {pos}, t={t}"
                    ),
                ))

    # --- Invalid / discontinuous movements ---
    for ac in planned:
        for t in range(len(ac.planned_path) - 1):
            p1 = ac.planned_path[t]
            p2 = ac.planned_path[t + 1]
            dx = abs(p2[0] - p1[0])
            dy = abs(p2[1] - p1[1])
            if dx + dy > 1:
                conflicts.append(Conflict(
                    conflict_type=ConflictType.INVALID_MOVE,
                    time_step=t,
                    aircraft_a=ac.aircraft_id,
                    aircraft_b="",
                    position_a=p1,
                    position_b=p2,
                    description=(
                        f"Invalid move: {ac.aircraft_id} from {p1} to {p2} at t={t}"
                    ),
                ))
            # Check out of bounds
            if not grid.in_bounds(p2):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.INVALID_MOVE,
                    time_step=t + 1,
                    aircraft_a=ac.aircraft_id,
                    aircraft_b="",
                    position_a=p2,
                    description=(
                        f"Out-of-bounds: {ac.aircraft_id} at {p2}, t={t+1}"
                    ),
                ))

    return conflicts
