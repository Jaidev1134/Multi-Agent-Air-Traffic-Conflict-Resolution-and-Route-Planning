"""
reservations.py — Space-time cell and transition reservation table.

Tracks which (x, y, t) cells are occupied and which directed edges
are reserved across time steps, so lower-priority aircraft can plan
around higher-priority ones.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from src.models import Position, SpaceTimePos


class ReservationTable:
    """
    Manages space-time reservations for multi-agent coordination.

    - Cell reservations:  (x, y, t) → aircraft_id
    - Edge reservations:  ((x1, y1, t), (x2, y2, t+1)) → aircraft_id
    """

    def __init__(self) -> None:
        self._cells: Dict[SpaceTimePos, str] = {}
        self._edges: Dict[Tuple[SpaceTimePos, SpaceTimePos], str] = {}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_cell_reserved(self, pos: SpaceTimePos) -> bool:
        return pos in self._cells

    def is_edge_reserved(self, from_st: SpaceTimePos, to_st: SpaceTimePos) -> bool:
        return (from_st, to_st) in self._edges

    def get_reserved_cells(self) -> Set[SpaceTimePos]:
        return set(self._cells.keys())

    def get_reserved_edges(self) -> Set[Tuple[SpaceTimePos, SpaceTimePos]]:
        return set(self._edges.keys())

    def cell_owner(self, pos: SpaceTimePos) -> Optional[str]:
        return self._cells.get(pos)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def reserve_path(
        self,
        aircraft_id: str,
        path: List[Position],
        max_time: int = 100,
    ) -> bool:
        """
        Reserve all cells, parked goal cells, and directed edges along *path*.

        Path is a sequence of (x, y) positions where the index is the
        time step. Once the aircraft reaches its goal (the final position
        in path at t_arr = len(path) - 1), the goal cell is reserved for all
        t from len(path) up to max_time to model aircraft parking at its destination.

        Returns True if all reservations succeeded, False if any cell was
        already reserved by a different aircraft (in which case no partial
        reservation is made).
        """
        if not path:
            return False

        # Pre-check
        new_cells: Dict[SpaceTimePos, str] = {}
        new_edges: Dict[Tuple[SpaceTimePos, SpaceTimePos], str] = {}

        # 1. Cells during transit (t = 0 .. len(path) - 1)
        for t, pos in enumerate(path):
            st = (pos[0], pos[1], t)
            if st in self._cells and self._cells[st] != aircraft_id:
                return False
            new_cells[st] = aircraft_id

        # 2. Parked goal cells (t = len(path) .. max_time)
        goal = path[-1]
        for t in range(len(path), max_time + 1):
            st = (goal[0], goal[1], t)
            if st in self._cells and self._cells[st] != aircraft_id:
                return False
            new_cells[st] = aircraft_id

        # 3. Directed transitions and reverse edges
        for t in range(len(path) - 1):
            from_st = (path[t][0], path[t][1], t)
            to_st = (path[t + 1][0], path[t + 1][1], t + 1)
            edge = (from_st, to_st)
            if edge in self._edges and self._edges[edge] != aircraft_id:
                return False
            new_edges[edge] = aircraft_id

            # Also reserve the reverse edge to block head-on swaps
            rev_edge_proper = (
                (path[t + 1][0], path[t + 1][1], t),
                (path[t][0], path[t][1], t + 1),
            )
            if rev_edge_proper in self._edges and self._edges[rev_edge_proper] != aircraft_id:
                return False
            new_edges[rev_edge_proper] = aircraft_id

        # Commit atomically
        self._cells.update(new_cells)
        self._edges.update(new_edges)
        return True

    def reserve_cell(self, aircraft_id: str, x: int, y: int, t: int) -> bool:
        """Reserve a single space-time cell (x, y, t) for aircraft_id."""
        st = (x, y, t)
        if st in self._cells and self._cells[st] != aircraft_id:
            return False
        self._cells[st] = aircraft_id
        return True

    def unreserve_aircraft(self, aircraft_id: str) -> None:
        """Remove all reservations belonging to *aircraft_id*."""
        self._cells = {k: v for k, v in self._cells.items() if v != aircraft_id}
        self._edges = {k: v for k, v in self._edges.items() if v != aircraft_id}

    def clear(self) -> None:
        """Remove all reservations."""
        self._cells.clear()
        self._edges.clear()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def summary(self) -> str:
        return (
            f"ReservationTable: {len(self._cells)} cell reservations, "
            f"{len(self._edges)} edge reservations"
        )
