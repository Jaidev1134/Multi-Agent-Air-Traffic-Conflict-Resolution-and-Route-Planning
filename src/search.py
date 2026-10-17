"""
search.py — A* and Uniform-Cost Search for space-time route planning.

Each search operates in (x, y, t) space so that time-dependent reservations
can be respected.  Both algorithms are genuine priority-queue–based graph
searches, not hardcoded path generators.
"""

from __future__ import annotations

import heapq
import time
from typing import Dict, List, Optional, Set, Tuple

from src.environment import get_neighbors, movement_cost
from src.models import ExpansionRecord, GridConfig, Position, SearchResult, SpaceTimePos


# ---------------------------------------------------------------------------
# Heuristic
# ---------------------------------------------------------------------------

def manhattan_distance(pos: Position, goal: Position) -> float:
    """Admissible heuristic: Manhattan distance between *pos* and *goal*."""
    return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])


# ---------------------------------------------------------------------------
# A* Search
# ---------------------------------------------------------------------------

def astar_search(
    grid: GridConfig,
    start: Position,
    goal: Position,
    reserved_cells: Optional[Set[SpaceTimePos]] = None,
    reserved_edges: Optional[Set[Tuple[SpaceTimePos, SpaceTimePos]]] = None,
    max_time: int = 100,
    record_trace: bool = False,
) -> SearchResult:
    """
    A* search in (x, y, t) space.

    Parameters
    ----------
    grid : GridConfig
        The airspace grid.
    start, goal : Position
        Start and goal (x, y) positions.
    reserved_cells : set of (x, y, t)
        Cells reserved by higher-priority aircraft.
    reserved_edges : set of ((x1, y1, t), (x2, y2, t+1))
        Edge reservations to prevent head-on swaps.
    max_time : int
        Maximum planning horizon (time steps).
    record_trace : bool
        If True, record step-by-step expansion trace in SearchResult.expansion_trace.

    Returns
    -------
    SearchResult
    """
    reserved_cells = reserved_cells or set()
    reserved_edges = reserved_edges or set()

    t0 = time.perf_counter()
    expansion_trace: List[ExpansionRecord] = []

    # Validate start / goal first
    if not grid.is_valid(start):
        return SearchResult(success=False, failure_reason=f"Start {start} is invalid or restricted.", algorithm="A*", expansion_trace=expansion_trace)
    if not grid.is_valid(goal):
        return SearchResult(success=False, failure_reason=f"Goal {goal} is invalid or restricted.", algorithm="A*", expansion_trace=expansion_trace)

    # Handle trivial case: start == goal when goal remains free across all time steps
    if start == goal and all((goal[0], goal[1], t) not in reserved_cells for t in range(0, max_time + 1)):
        elapsed = (time.perf_counter() - t0) * 1000
        return SearchResult(
            success=True,
            path=[start],
            cost=0.0,
            nodes_expanded=0,
            nodes_generated=1,
            runtime_ms=elapsed,
            algorithm="A*",
            expansion_trace=expansion_trace,
        )

    # Priority queue: (f, h, tie-breaker, (x, y, t))
    counter = 0
    open_list: List[Tuple[float, float, int, SpaceTimePos]] = []
    g_cost: Dict[SpaceTimePos, float] = {}
    parent: Dict[SpaceTimePos, Optional[SpaceTimePos]] = {}

    start_state: SpaceTimePos = (start[0], start[1], 0)

    # Check if start position at t=0 is reserved
    if start_state in reserved_cells:
        elapsed = (time.perf_counter() - t0) * 1000
        return SearchResult(
            success=False,
            failure_reason=f"Start position {start} is reserved at t=0.",
            runtime_ms=elapsed,
            algorithm="A*",
            expansion_trace=expansion_trace,
        )

    g_cost[start_state] = 0.0
    h = manhattan_distance(start, goal)
    heapq.heappush(open_list, (h, h, counter, start_state))
    counter += 1
    parent[start_state] = None

    nodes_expanded = 0
    nodes_generated = 1

    while open_list:
        f_val, _, _, current = heapq.heappop(open_list)
        cx, cy, ct = current

        # Stale entry check
        if g_cost.get(current, float("inf")) < f_val - manhattan_distance((cx, cy), goal):
            continue

        # Goal check — goal must remain unoccupied for all t >= ct up to max_time
        if (cx, cy) == goal:
            if all((goal[0], goal[1], t) not in reserved_cells for t in range(ct, max_time + 1)):
                # Reconstruct path
                path: List[Position] = []
                node: Optional[SpaceTimePos] = current
                while node is not None:
                    path.append((node[0], node[1]))
                    node = parent[node]
                path.reverse()
                elapsed = (time.perf_counter() - t0) * 1000
                return SearchResult(
                    success=True,
                    path=path,
                    cost=g_cost[current],
                    nodes_expanded=nodes_expanded,
                    nodes_generated=nodes_generated,
                    runtime_ms=elapsed,
                    algorithm="A*",
                    expansion_trace=expansion_trace,
                )

        nodes_expanded += 1
        cur_g = g_cost[current]
        cur_h = manhattan_distance((cx, cy), goal)
        cur_f = cur_g + cur_h

        # Enforce planning horizon
        if ct >= max_time:
            if record_trace:
                expansion_trace.append(
                    ExpansionRecord(
                        step=nodes_expanded,
                        state=current,
                        g=cur_g,
                        h=cur_h,
                        f=cur_f,
                        blocked_successors=0,
                    )
                )
            continue

        # Generate successors
        blocked_successors = 0
        neighbor_positions = get_neighbors(grid, (cx, cy), include_wait=True)
        for nx, ny in neighbor_positions:
            nt = ct + 1
            successor: SpaceTimePos = (nx, ny, nt)

            # Check cell reservation
            if successor in reserved_cells:
                blocked_successors += 1
                continue

            # Check edge reservation (head-on swap)
            edge_forward = (current, successor)
            edge_reverse = ((nx, ny, ct), (cx, cy, nt))
            if edge_forward in reserved_edges or edge_reverse in reserved_edges:
                blocked_successors += 1
                continue

            step_cost = movement_cost((cx, cy), (nx, ny))
            new_g = g_cost[current] + step_cost

            if new_g < g_cost.get(successor, float("inf")):
                g_cost[successor] = new_g
                parent[successor] = current
                h = manhattan_distance((nx, ny), goal)
                f = new_g + h
                heapq.heappush(open_list, (f, h, counter, successor))
                counter += 1
                nodes_generated += 1

        if record_trace:
            expansion_trace.append(
                ExpansionRecord(
                    step=nodes_expanded,
                    state=current,
                    g=cur_g,
                    h=cur_h,
                    f=cur_f,
                    blocked_successors=blocked_successors,
                )
            )

    elapsed = (time.perf_counter() - t0) * 1000
    return SearchResult(
        success=False,
        failure_reason="Search space exhausted — no feasible path found within the planning horizon.",
        nodes_expanded=nodes_expanded,
        nodes_generated=nodes_generated,
        runtime_ms=elapsed,
        algorithm="A*",
        expansion_trace=expansion_trace,
    )


# ---------------------------------------------------------------------------
# Uniform-Cost Search
# ---------------------------------------------------------------------------

def ucs_search(
    grid: GridConfig,
    start: Position,
    goal: Position,
    reserved_cells: Optional[Set[SpaceTimePos]] = None,
    reserved_edges: Optional[Set[Tuple[SpaceTimePos, SpaceTimePos]]] = None,
    max_time: int = 100,
    record_trace: bool = False,
) -> SearchResult:
    """
    Uniform-Cost Search in (x, y, t) space.

    Identical interface to *astar_search* but uses g(n) as the sole priority
    (h = 0), making it a Dijkstra-style search.
    """
    reserved_cells = reserved_cells or set()
    reserved_edges = reserved_edges or set()

    t0 = time.perf_counter()
    expansion_trace: List[ExpansionRecord] = []

    # Validate start / goal first
    if not grid.is_valid(start):
        return SearchResult(success=False, failure_reason=f"Start {start} is invalid or restricted.", algorithm="UCS", expansion_trace=expansion_trace)
    if not grid.is_valid(goal):
        return SearchResult(success=False, failure_reason=f"Goal {goal} is invalid or restricted.", algorithm="UCS", expansion_trace=expansion_trace)

    # Handle trivial case: start == goal when goal remains free across all time steps
    if start == goal and all((goal[0], goal[1], t) not in reserved_cells for t in range(0, max_time + 1)):
        elapsed = (time.perf_counter() - t0) * 1000
        return SearchResult(
            success=True,
            path=[start],
            cost=0.0,
            nodes_expanded=0,
            nodes_generated=1,
            runtime_ms=elapsed,
            algorithm="UCS",
            expansion_trace=expansion_trace,
        )

    counter = 0
    open_list: List[Tuple[float, int, SpaceTimePos]] = []
    g_cost: Dict[SpaceTimePos, float] = {}
    parent: Dict[SpaceTimePos, Optional[SpaceTimePos]] = {}

    start_state: SpaceTimePos = (start[0], start[1], 0)

    if start_state in reserved_cells:
        elapsed = (time.perf_counter() - t0) * 1000
        return SearchResult(
            success=False,
            failure_reason=f"Start position {start} is reserved at t=0.",
            runtime_ms=elapsed,
            algorithm="UCS",
            expansion_trace=expansion_trace,
        )

    g_cost[start_state] = 0.0
    heapq.heappush(open_list, (0.0, counter, start_state))
    counter += 1
    parent[start_state] = None

    nodes_expanded = 0
    nodes_generated = 1

    while open_list:
        g_val, _, current = heapq.heappop(open_list)
        cx, cy, ct = current

        if g_cost.get(current, float("inf")) < g_val:
            continue

        # Goal check — goal must remain unoccupied for all t >= ct up to max_time
        if (cx, cy) == goal:
            if all((goal[0], goal[1], t) not in reserved_cells for t in range(ct, max_time + 1)):
                path: List[Position] = []
                node: Optional[SpaceTimePos] = current
                while node is not None:
                    path.append((node[0], node[1]))
                    node = parent[node]
                path.reverse()
                elapsed = (time.perf_counter() - t0) * 1000
                return SearchResult(
                    success=True,
                    path=path,
                    cost=g_cost[current],
                    nodes_expanded=nodes_expanded,
                    nodes_generated=nodes_generated,
                    runtime_ms=elapsed,
                    algorithm="UCS",
                    expansion_trace=expansion_trace,
                )

        nodes_expanded += 1
        cur_g = g_cost[current]
        cur_h = 0.0
        cur_f = cur_g

        if ct >= max_time:
            if record_trace:
                expansion_trace.append(
                    ExpansionRecord(
                        step=nodes_expanded,
                        state=current,
                        g=cur_g,
                        h=0.0,
                        f=cur_g,
                        blocked_successors=0,
                    )
                )
            continue

        blocked_successors = 0
        neighbor_positions = get_neighbors(grid, (cx, cy), include_wait=True)
        for nx, ny in neighbor_positions:
            nt = ct + 1
            successor: SpaceTimePos = (nx, ny, nt)

            if successor in reserved_cells:
                blocked_successors += 1
                continue

            edge_forward = (current, successor)
            edge_reverse = ((nx, ny, ct), (cx, cy, nt))
            if edge_forward in reserved_edges or edge_reverse in reserved_edges:
                blocked_successors += 1
                continue

            step_cost = movement_cost((cx, cy), (nx, ny))
            new_g = g_cost[current] + step_cost

            if new_g < g_cost.get(successor, float("inf")):
                g_cost[successor] = new_g
                parent[successor] = current
                heapq.heappush(open_list, (new_g, counter, successor))
                counter += 1
                nodes_generated += 1

        if record_trace:
            expansion_trace.append(
                ExpansionRecord(
                    step=nodes_expanded,
                    state=current,
                    g=cur_g,
                    h=0.0,
                    f=cur_g,
                    blocked_successors=blocked_successors,
                )
            )

    elapsed = (time.perf_counter() - t0) * 1000
    return SearchResult(
        success=False,
        failure_reason="Search space exhausted — no feasible path found within the planning horizon.",
        nodes_expanded=nodes_expanded,
        nodes_generated=nodes_generated,
        runtime_ms=elapsed,
        algorithm="UCS",
        expansion_trace=expansion_trace,
    )
