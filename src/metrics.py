"""
metrics.py — Performance measurement and A* vs UCS comparison utilities.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from src.models import ComparisonRow, SimulationMetrics


def metrics_to_dataframe(metrics: SimulationMetrics) -> pd.DataFrame:
    """Convert a SimulationMetrics object to a single-row DataFrame."""
    return pd.DataFrame([metrics.to_dict()])


def comparison_table(rows: List[ComparisonRow]) -> pd.DataFrame:
    """Build a comparison DataFrame from ComparisonRow entries."""
    data = []
    for r in rows:
        data.append({
            "Scenario": r.scenario_name,
            "Algorithm": r.algorithm,
            "Success": r.success,
            "Path Cost": "N/A" if r.path_cost is None else r.path_cost,
            "Nodes Expanded": r.nodes_expanded,
            "Nodes Generated": r.nodes_generated,
            "Runtime (ms)": round(r.runtime_ms, 3),
            "Waiting Time": "N/A" if r.waiting_time is None else r.waiting_time,
            "Makespan": "N/A" if r.makespan is None else r.makespan,
            "Conflicts Before Coordination": r.conflicts_before,
            "Unresolved Conflicts After Coordination": r.conflicts_unresolved,
        })
    return pd.DataFrame(data)


def events_to_dataframe(events) -> pd.DataFrame:
    """Convert a list of SimulationEvent to a DataFrame for CSV export."""
    rows = []
    for e in events:
        rows.append({
            "Time Step": e.time_step,
            "Aircraft ID": e.aircraft_id or "",
            "Event Type": e.event_type.value,
            "Position": str(e.position) if e.position else "",
            "Description": e.description,
        })
    return pd.DataFrame(rows)
