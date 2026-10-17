"""
models.py — Core data structures for the Air Traffic Conflict Resolution simulation.

Defines Aircraft, Grid configuration, search states, search results,
conflict records, simulation events, and simulation state.
All coordinates use (x, y) convention consistently.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Set


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Position = Tuple[int, int]          # (x, y) on the grid
SpaceTimePos = Tuple[int, int, int] # (x, y, t)
Edge = Tuple[Position, Position]    # directed movement from one cell to another


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class AircraftStatus(enum.Enum):
    """Lifecycle status of an individual aircraft."""
    WAITING = "waiting"           # created but not yet planned
    PLANNED = "planned"           # route computed
    EN_ROUTE = "en_route"         # simulation running, aircraft moving
    ARRIVED = "arrived"           # reached destination
    FAILED = "failed"             # planning or execution failed


class SimulationState(enum.Enum):
    """Overall simulation lifecycle."""
    READY = "ready"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ConflictType(enum.Enum):
    """Types of conflicts between aircraft."""
    VERTEX = "vertex"             # two aircraft in the same cell at same time
    EDGE_SWAP = "edge_swap"       # two aircraft swap positions in same step
    RESTRICTED = "restricted"     # aircraft enters a restricted cell
    INVALID_MOVE = "invalid_move" # discontinuous or out-of-bounds movement


class EventType(enum.Enum):
    """Types of simulation events recorded in the event log."""
    ROUTE_PLANNED = "route_planned"
    CONFLICT_DETECTED = "conflict_detected"
    RESERVATION_REJECTED = "reservation_rejected"
    AIRCRAFT_WAITED = "aircraft_waited"
    ROUTE_REPLANNED = "route_replanned"
    DESTINATION_REACHED = "destination_reached"
    PLANNING_FAILED = "planning_failed"
    AIRCRAFT_MOVED = "aircraft_moved"
    SIMULATION_STARTED = "simulation_started"
    SIMULATION_COMPLETED = "simulation_completed"
    SIMULATION_FAILED = "simulation_failed"
    CONFLICT_RESOLVED = "conflict_resolved"
    PRIORITY_REORDER = "priority_reorder"
    WARNING = "warning"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ExpansionRecord:
    """Record of a single node expansion during search."""
    step: int
    state: Tuple[int, int, int]  # (x, y, t)
    g: float
    h: float
    f: float
    blocked_successors: int = 0


@dataclass
class SearchResult:
    """Result returned by a search algorithm (A* or UCS)."""
    success: bool
    path: List[Position] = field(default_factory=list)
    cost: float = float("inf")
    nodes_expanded: int = 0
    nodes_generated: int = 0
    runtime_ms: float = 0.0
    failure_reason: str = ""
    algorithm: str = ""
    expansion_trace: List[ExpansionRecord] = field(default_factory=list)

    @property
    def path_length(self) -> int:
        return len(self.path)


@dataclass
class Aircraft:
    """Represents a single aircraft agent in the simulation."""
    aircraft_id: str
    start: Position
    goal: Position
    priority: int = 0                                   # lower = higher priority
    color: str = "#3498db"
    status: AircraftStatus = AircraftStatus.WAITING

    # Planning results
    planned_path: List[Position] = field(default_factory=list)
    executed_path: List[Position] = field(default_factory=list)
    search_result: Optional[SearchResult] = None

    # Runtime state
    current_position: Optional[Position] = None
    arrival_time: Optional[int] = None
    waiting_time: int = 0
    route_cost: float = 0.0

    def __post_init__(self):
        if self.current_position is None:
            self.current_position = self.start

    def reset(self):
        """Reset aircraft to its initial state for re-planning."""
        self.status = AircraftStatus.WAITING
        self.planned_path = []
        self.executed_path = []
        self.search_result = None
        self.current_position = self.start
        self.arrival_time = None
        self.waiting_time = 0
        self.route_cost = 0.0


@dataclass
class GridConfig:
    """Configuration for the simulation grid / airspace."""
    width: int = 12
    height: int = 12
    restricted_cells: Set[Position] = field(default_factory=set)

    def in_bounds(self, pos: Position) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_blocked(self, pos: Position) -> bool:
        return pos in self.restricted_cells

    def is_valid(self, pos: Position) -> bool:
        return self.in_bounds(pos) and not self.is_blocked(pos)


@dataclass
class Conflict:
    """A detected conflict between two aircraft."""
    conflict_type: ConflictType
    time_step: int
    aircraft_a: str
    aircraft_b: str
    position_a: Optional[Position] = None
    position_b: Optional[Position] = None
    description: str = ""


@dataclass
class SimulationEvent:
    """A single event in the simulation log."""
    time_step: int
    aircraft_id: Optional[str]
    event_type: EventType
    position: Optional[Position]
    description: str


@dataclass
class SimulationMetrics:
    """Aggregate metrics from a simulation run."""
    aircraft_completed: int = 0
    aircraft_failed: int = 0
    total_route_cost: float = 0.0
    total_movements: int = 0
    total_waiting_time: int = 0
    makespan: int = 0
    conflicts_before_resolution: int = 0
    unresolved_conflicts: int = 0
    total_nodes_expanded: int = 0
    total_nodes_generated: int = 0
    total_search_runtime_ms: float = 0.0
    replanning_attempts: int = 0
    algorithm_used: str = ""

    def to_dict(self) -> Dict:
        return {
            "Aircraft Completed": self.aircraft_completed,
            "Aircraft Failed": self.aircraft_failed,
            "Total Route Cost": self.total_route_cost,
            "Total Movements": self.total_movements,
            "Total Waiting Time": self.total_waiting_time,
            "Makespan": self.makespan,
            "Conflicts Before Resolution": self.conflicts_before_resolution,
            "Unresolved Conflicts": self.unresolved_conflicts,
            "Total Nodes Expanded": self.total_nodes_expanded,
            "Total Nodes Generated": self.total_nodes_generated,
            "Total Search Runtime (ms)": round(self.total_search_runtime_ms, 3),
            "Replanning Attempts": self.replanning_attempts,
            "Algorithm": self.algorithm_used,
        }


@dataclass
class ComparisonRow:
    """One row of the A* vs UCS comparison table."""
    scenario_name: str
    algorithm: str
    success: bool
    path_cost: Optional[float]
    nodes_expanded: int
    nodes_generated: int
    runtime_ms: float
    waiting_time: Optional[int]
    makespan: Optional[int]
    conflicts_before: int
    conflicts_unresolved: int
