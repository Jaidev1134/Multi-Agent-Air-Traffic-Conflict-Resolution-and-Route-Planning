"""
simulation.py — Simulation lifecycle, movement execution, and safety checks.

Advances the simulation one time step at a time using pre-computed planned
paths.  Validates safety invariants after each step.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.conflict_detection import detect_conflicts
from src.coordinator import plan_all_aircraft, _get_search_fn
from src.environment import validate_aircraft_config
from src.models import (
    Aircraft,
    AircraftStatus,
    Conflict,
    EventType,
    GridConfig,
    SimulationEvent,
    SimulationMetrics,
    SimulationState,
)
from src.reservations import ReservationTable


class Simulation:
    """
    Manages the full simulation lifecycle: planning, execution, and evaluation.
    """

    def __init__(
        self,
        grid: GridConfig,
        aircraft_list: List[Aircraft],
        algorithm: str = "A*",
        max_time: int = 100,
        max_replan_attempts: int = 3,
        max_execution_steps: int = 200,
        record_trace: bool = False,
    ) -> None:
        self.grid = grid
        self.aircraft = list(aircraft_list)
        self.algorithm = algorithm
        self.max_time = max_time
        self.max_replan_attempts = max_replan_attempts
        self.max_execution_steps = max_execution_steps
        self.record_trace = record_trace

        # Validate aircraft configuration at creation
        raw_validation = validate_aircraft_config(self.grid, self.aircraft)
        self.validation_errors = [m for m in raw_validation if not m.startswith("Warning:")]
        self.validation_warnings = [m for m in raw_validation if m.startswith("Warning:")]

        # Simulation starts in READY state prior to planning unless hard validation errors exist
        self.state: SimulationState = SimulationState.READY if not self.validation_errors else SimulationState.FAILED
        self._has_planned: bool = False
        self.current_step: int = 0
        self.events: List[SimulationEvent] = []
        self.conflicts_before: List[Conflict] = []
        self.unresolved_conflicts: List[Conflict] = []
        self.reservation_table: Optional[ReservationTable] = None
        self.replan_count: int = 0

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan(self, record_trace: Optional[bool] = None) -> bool:
        """Run multi-agent planning. Returns True if planning succeeded without conflicts."""
        rec_trace = self.record_trace if record_trace is None else record_trace
        self.current_step = 0
        self.events = []
        for ac in self.aircraft:
            ac.reset()

        # Log validation warnings
        for w in self.validation_warnings:
            self.events.append(SimulationEvent(
                time_step=0,
                aircraft_id=None,
                event_type=EventType.WARNING,
                position=None,
                description=f"Validation: {w}",
            ))

        # Check for hard validation errors
        if self.validation_errors:
            self.state = SimulationState.FAILED
            for err in self.validation_errors:
                self.events.append(SimulationEvent(
                    time_step=0,
                    aircraft_id=None,
                    event_type=EventType.SIMULATION_FAILED,
                    position=None,
                    description=f"Configuration error: {err}",
                ))
            return False

        self.state = SimulationState.PLANNING

        # 1. Compute initial (independent) conflicts: plan each aircraft without reservations
        search_fn = _get_search_fn(self.algorithm)
        indep_aircraft: List[Aircraft] = []
        for ac in self.aircraft:
            clone = Aircraft(ac.aircraft_id, ac.start, ac.goal, ac.priority, ac.color)
            res = search_fn(grid=self.grid, start=ac.start, goal=ac.goal, max_time=self.max_time)
            if res.success:
                clone.planned_path = res.path
            indep_aircraft.append(clone)
        self.conflicts_before = detect_conflicts(indep_aircraft, self.grid)

        # 2. Run prioritized multi-agent coordination with reservation table and replanning
        events, conflicts, table, replan_count = plan_all_aircraft(
            grid=self.grid,
            aircraft_list=self.aircraft,
            algorithm=self.algorithm,
            max_time=self.max_time,
            max_replan_attempts=self.max_replan_attempts,
            record_trace=rec_trace,
        )
        self.events.extend(events)
        self.reservation_table = table
        self.replan_count = replan_count
        self.unresolved_conflicts = conflicts
        self._has_planned = True

        all_planned = all(ac.status == AircraftStatus.PLANNED for ac in self.aircraft)
        any_planned = any(ac.status == AircraftStatus.PLANNED for ac in self.aircraft)

        # Succeeded if zero unresolved conflicts and at least one flight is planned
        if not conflicts and any_planned:
            self.state = SimulationState.READY
            if not all_planned:
                failed_ids = [ac.aircraft_id for ac in self.aircraft if ac.status != AircraftStatus.PLANNED]
                self.events.append(SimulationEvent(
                    time_step=0,
                    aircraft_id=None,
                    event_type=EventType.WARNING,
                    position=None,
                    description=f"Partial planning: aircraft {failed_ids} failed, but remaining flights are conflict-free.",
                ))
            return True
        else:
            self.state = SimulationState.FAILED
            if conflicts:
                self.events.append(SimulationEvent(
                    time_step=0,
                    aircraft_id=None,
                    event_type=EventType.SIMULATION_FAILED,
                    position=None,
                    description=f"Planning failed: {len(conflicts)} unresolved conflict(s) remain.",
                ))
            elif not any_planned:
                self.events.append(SimulationEvent(
                    time_step=0,
                    aircraft_id=None,
                    event_type=EventType.SIMULATION_FAILED,
                    position=None,
                    description="Planning failed: no aircraft could find valid routes.",
                ))
            return False

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_full(self) -> None:
        """Run the entire simulation to completion."""
        # 1. Idempotent no-op if already finished or terminated after running
        if self.state == SimulationState.COMPLETED:
            return
        if self.state == SimulationState.FAILED and self.current_step > 0:
            return

        # 2. Reject if plan() was never called
        if not self._has_planned:
            self.state = SimulationState.FAILED
            if not any("routes have not been planned" in e.description for e in self.events):
                self.events.append(SimulationEvent(
                    time_step=self.current_step,
                    aircraft_id=None,
                    event_type=EventType.SIMULATION_FAILED,
                    position=None,
                    description="Cannot run simulation: routes have not been planned. Call plan() first.",
                ))
            return

        # 3. Reject if plan() failed or execution limit was reached
        if self.state == SimulationState.FAILED:
            if any("Cannot run simulation" in e.description for e in self.events):
                return
            if any("Execution limit" in e.description for e in self.events):
                desc = f"Cannot run simulation: execution limit ({self.max_execution_steps}) was reached."
            else:
                desc = "Cannot run simulation: route planning failed to find valid routes for all aircraft."
            self.events.append(SimulationEvent(
                time_step=self.current_step,
                aircraft_id=None,
                event_type=EventType.SIMULATION_FAILED,
                position=None,
                description=desc,
            ))
            return

        # 4. State must be READY or PAUSED
        if self.state not in (SimulationState.READY, SimulationState.PAUSED):
            self.state = SimulationState.FAILED
            if not any("simulation is in state" in e.description for e in self.events):
                self.events.append(SimulationEvent(
                    time_step=self.current_step,
                    aircraft_id=None,
                    event_type=EventType.SIMULATION_FAILED,
                    position=None,
                    description=f"Cannot run simulation: simulation is in state {self.state.value}.",
                ))
            return

        self.state = SimulationState.RUNNING
        self.events.append(SimulationEvent(
            time_step=self.current_step,
            aircraft_id=None,
            event_type=EventType.SIMULATION_STARTED,
            position=None,
            description="Simulation started.",
        ))

        # Initialize executed paths
        for ac in self.aircraft:
            if ac.status == AircraftStatus.PLANNED:
                # Handle start == goal at t=0
                if ac.start == ac.goal and len(ac.planned_path) == 1:
                    ac.status = AircraftStatus.ARRIVED
                    ac.arrival_time = 0
                    ac.executed_path = [ac.start]
                    ac.current_position = ac.goal
                    self.events.append(SimulationEvent(
                        time_step=0,
                        aircraft_id=ac.aircraft_id,
                        event_type=EventType.DESTINATION_REACHED,
                        position=ac.goal,
                        description=f"{ac.aircraft_id} reached destination {ac.goal} at t=0.",
                    ))
                else:
                    ac.status = AircraftStatus.EN_ROUTE
                    ac.executed_path = [ac.start]

        while not self._all_done() and self.current_step < self.max_execution_steps:
            self.step()

        if self._all_done():
            self.state = SimulationState.COMPLETED
            self.events.append(SimulationEvent(
                time_step=self.current_step,
                aircraft_id=None,
                event_type=EventType.SIMULATION_COMPLETED,
                position=None,
                description="All aircraft completed or failed.",
            ))
        else:
            self.state = SimulationState.FAILED
            # Mark any remaining EN_ROUTE or PLANNED aircraft as FAILED due to limit
            for ac in self.aircraft:
                if ac.status in (AircraftStatus.EN_ROUTE, AircraftStatus.PLANNED, AircraftStatus.WAITING):
                    ac.status = AircraftStatus.FAILED
                    self.events.append(SimulationEvent(
                        time_step=self.current_step,
                        aircraft_id=ac.aircraft_id,
                        event_type=EventType.SIMULATION_FAILED,
                        position=ac.current_position,
                        description=f"{ac.aircraft_id} failed: execution limit ({self.max_execution_steps}) reached.",
                    ))
            self.events.append(SimulationEvent(
                time_step=self.current_step,
                aircraft_id=None,
                event_type=EventType.SIMULATION_FAILED,
                position=None,
                description=f"Execution limit ({self.max_execution_steps}) reached.",
            ))

    def step(self) -> None:
        """Advance the simulation by one time step."""
        self.current_step += 1
        t = self.current_step

        for ac in self.aircraft:
            if ac.status != AircraftStatus.EN_ROUTE:
                continue

            if t < len(ac.planned_path):
                next_pos = ac.planned_path[t]
                prev_pos = ac.current_position

                if next_pos == prev_pos:
                    ac.waiting_time += 1
                    self.events.append(SimulationEvent(
                        time_step=t,
                        aircraft_id=ac.aircraft_id,
                        event_type=EventType.AIRCRAFT_WAITED,
                        position=next_pos,
                        description=f"{ac.aircraft_id} waited at {next_pos}.",
                    ))
                else:
                    self.events.append(SimulationEvent(
                        time_step=t,
                        aircraft_id=ac.aircraft_id,
                        event_type=EventType.AIRCRAFT_MOVED,
                        position=next_pos,
                        description=f"{ac.aircraft_id} moved from {prev_pos} to {next_pos}.",
                    ))

                ac.current_position = next_pos
                ac.executed_path.append(next_pos)

                # Check if arrived: ONLY when reaching the goal at the FINAL step of the plan
                if t == len(ac.planned_path) - 1 and next_pos == ac.goal:
                    ac.status = AircraftStatus.ARRIVED
                    ac.arrival_time = t
                    self.events.append(SimulationEvent(
                        time_step=t,
                        aircraft_id=ac.aircraft_id,
                        event_type=EventType.DESTINATION_REACHED,
                        position=next_pos,
                        description=f"{ac.aircraft_id} reached destination {next_pos} at t={t}.",
                    ))
            elif ac.current_position == ac.goal:
                ac.status = AircraftStatus.ARRIVED
                ac.arrival_time = t - 1
            else:
                # Path exhausted but not at goal
                ac.status = AircraftStatus.FAILED
                self.events.append(SimulationEvent(
                    time_step=t,
                    aircraft_id=ac.aircraft_id,
                    event_type=EventType.PLANNING_FAILED,
                    position=ac.current_position,
                    description=f"{ac.aircraft_id} path exhausted but not at goal.",
                ))

    def _all_done(self) -> bool:
        """Check if all aircraft have reached terminal state (arrived or failed)."""
        return all(
            ac.status in (AircraftStatus.ARRIVED, AircraftStatus.FAILED)
            for ac in self.aircraft
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def compute_metrics(self) -> SimulationMetrics:
        """Compute aggregate metrics from the current simulation state."""
        m = SimulationMetrics()
        m.algorithm_used = self.algorithm

        for ac in self.aircraft:
            if ac.status == AircraftStatus.ARRIVED:
                m.aircraft_completed += 1
                m.total_route_cost += ac.route_cost
                if ac.planned_path:
                    m.total_movements += len(ac.planned_path) - 1 - ac.waiting_time
                m.total_waiting_time += ac.waiting_time
                if ac.arrival_time is not None:
                    m.makespan = max(m.makespan, ac.arrival_time)
            elif ac.status == AircraftStatus.FAILED:
                m.aircraft_failed += 1

            if ac.search_result:
                m.total_nodes_expanded += ac.search_result.nodes_expanded
                m.total_nodes_generated += ac.search_result.nodes_generated
                m.total_search_runtime_ms += ac.search_result.runtime_ms

        if self.reservation_table and hasattr(self.reservation_table, "cumulative_nodes_expanded") and self.reservation_table.cumulative_nodes_expanded > 0:
            m.total_nodes_expanded = self.reservation_table.cumulative_nodes_expanded
            m.total_nodes_generated = self.reservation_table.cumulative_nodes_generated
            m.total_search_runtime_ms = self.reservation_table.cumulative_runtime_ms

        m.conflicts_before_resolution = len(self.conflicts_before)
        m.unresolved_conflicts = len(self.unresolved_conflicts)
        m.replanning_attempts = self.replan_count

        return m

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------

    def get_aircraft_positions_at(self, t: int) -> Dict[str, Optional[Tuple[int, int]]]:
        """Return the position of each aircraft at time step *t*."""
        positions: Dict[str, Optional[Tuple[int, int]]] = {}
        for ac in self.aircraft:
            if ac.planned_path and t < len(ac.planned_path):
                positions[ac.aircraft_id] = ac.planned_path[t]
            elif ac.planned_path:
                positions[ac.aircraft_id] = ac.planned_path[-1]
            else:
                positions[ac.aircraft_id] = ac.start
        return positions

    def get_max_path_length(self) -> int:
        """Return the length of the longest planned path."""
        return max((len(ac.planned_path) for ac in self.aircraft if ac.planned_path), default=0)
