"""
environment.py — Grid-based airspace environment.

Handles grid creation, movement validation, neighbor generation,
and input validation for aircraft configurations.
"""

from __future__ import annotations

from typing import List, Set, Tuple

from src.models import Aircraft, GridConfig, Position


# Movement deltas: right, left, down, up, wait
MOVES: List[Tuple[int, int]] = [(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)]
MOVE_NAMES = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up", (0, 0): "wait"}


def get_neighbors(grid: GridConfig, pos: Position, include_wait: bool = True) -> List[Position]:
    """
    Return list of valid neighboring positions from *pos*.

    Includes the wait action (staying in place) when *include_wait* is True.
    Restricted and out-of-bounds cells are excluded.
    """
    neighbors: List[Position] = []
    for dx, dy in MOVES:
        if not include_wait and dx == 0 and dy == 0:
            continue
        nx, ny = pos[0] + dx, pos[1] + dy
        if grid.is_valid((nx, ny)):
            neighbors.append((nx, ny))
    return neighbors


def movement_cost(from_pos: Position, to_pos: Position) -> float:
    """
    Return the cost of moving from *from_pos* to *to_pos*.
    Moving costs 1, waiting costs 1.
    """
    return 1.0


def validate_aircraft_config(
    grid: GridConfig,
    aircraft_list: List[Aircraft],
) -> List[str]:
    """
    Validate aircraft configurations against the grid.

    Returns a list of error messages.  An empty list means all configs are valid.
    """
    errors: List[str] = []
    ids_seen: Set[str] = set()
    starts_seen: Set[Position] = set()
    goals_seen: Set[Position] = set()

    for ac in aircraft_list:
        aid = ac.aircraft_id

        # Duplicate aircraft IDs
        if aid in ids_seen:
            errors.append(f"{aid}: duplicate aircraft ID.")
        ids_seen.add(aid)

        # Out of bounds
        if not grid.in_bounds(ac.start):
            errors.append(f"{aid}: start {ac.start} is out of bounds.")
        if not grid.in_bounds(ac.goal):
            errors.append(f"{aid}: goal {ac.goal} is out of bounds.")

        # Blocked start / goal
        if ac.start in grid.restricted_cells:
            errors.append(f"{aid}: start {ac.start} is a restricted cell.")
        if ac.goal in grid.restricted_cells:
            errors.append(f"{aid}: goal {ac.goal} is a restricted cell.")

        # Duplicate starts
        if ac.start in starts_seen:
            errors.append(f"{aid}: start {ac.start} is shared with another aircraft.")
        starts_seen.add(ac.start)

        # Duplicate goals
        if ac.goal in goals_seen:
            errors.append(f"{aid}: goal {ac.goal} is shared with another aircraft.")
        goals_seen.add(ac.goal)

    # Flag shared endpoints across distinct aircraft (goal == another aircraft's start)
    for ac in aircraft_list:
        for other in aircraft_list:
            if ac.aircraft_id != other.aircraft_id and ac.goal == other.start:
                msg = f"Warning: {ac.aircraft_id}'s goal {ac.goal} coincides with {other.aircraft_id}'s start position."
                if msg not in errors:
                    errors.append(msg)

    return errors


def create_grid(
    width: int = 12,
    height: int = 12,
    restricted: Set[Position] | None = None,
) -> GridConfig:
    """Create a GridConfig with optional restricted cells."""
    if width < 1 or height < 1:
        raise ValueError(f"Grid dimensions must be positive, got ({width}, {height}).")
    return GridConfig(width=width, height=height, restricted_cells=restricted or set())
