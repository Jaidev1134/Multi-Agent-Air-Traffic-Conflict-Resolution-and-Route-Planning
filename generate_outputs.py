"""
generate_outputs.py — Runs all scenarios through A* and UCS,
generates output CSVs and summary metrics for the academic report and presentation.
"""

from __future__ import annotations

import os
import pandas as pd
from typing import List

from src.models import ComparisonRow, Aircraft
from src.scenarios import SCENARIO_REGISTRY
from src.simulation import Simulation
from src.metrics import comparison_table, events_to_dataframe, metrics_to_dataframe


def run_all_and_save():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    outputs_dir = os.path.join(base_dir, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)

    rows: List[ComparisonRow] = []
    all_events = []
    default_metrics = None

    print("Running experiments for all scenarios under A* and UCS...")

    for sname, (sfn, sdesc) in SCENARIO_REGISTRY.items():
        for algo in ["A*", "UCS"]:
            grid, aircraft = sfn()
            # Deep clone aircraft
            ac_clones = [
                Aircraft(a.aircraft_id, a.start, a.goal, a.priority, a.color)
                for a in aircraft
            ]
            sim = Simulation(grid, ac_clones, algorithm=algo, max_time=100, max_replan_attempts=3)
            sim.plan()
            sim.run_full()
            m = sim.compute_metrics()

            if sname == "7. Five Aircraft (Default)" and algo == "A*":
                default_metrics = m

            is_success = (m.aircraft_failed == 0 and m.aircraft_completed > 0)
            cost_val = None if (m.aircraft_completed == 0 and m.aircraft_failed > 0) else m.total_route_cost
            wait_val = None if (m.aircraft_completed == 0 and m.aircraft_failed > 0) else m.total_waiting_time
            make_val = None if (m.aircraft_completed == 0 and m.aircraft_failed > 0) else m.makespan
            rows.append(ComparisonRow(
                scenario_name=sname,
                algorithm=algo,
                success=is_success,
                path_cost=cost_val,
                nodes_expanded=m.total_nodes_expanded,
                nodes_generated=m.total_nodes_generated,
                runtime_ms=m.total_search_runtime_ms,
                waiting_time=wait_val,
                makespan=make_val,
                conflicts_before=m.conflicts_before_resolution,
                conflicts_unresolved=m.unresolved_conflicts,
            ))

            for e in sim.events:
                all_events.append({
                    "Scenario": sname,
                    "Algorithm": algo,
                    "Time Step": e.time_step,
                    "Aircraft ID": e.aircraft_id or "",
                    "Event Type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                    "Position": str(e.position) if e.position else "",
                    "Description": e.description,
                })

    df_comp = comparison_table(rows)
    df_comp.to_csv(os.path.join(outputs_dir, "comparison.csv"), index=False)
    print("Saved outputs/comparison.csv")

    if default_metrics:
        df_met = metrics_to_dataframe(default_metrics)
        df_met.to_csv(os.path.join(outputs_dir, "metrics.csv"), index=False)
        print("Saved outputs/metrics.csv")

    df_events = pd.DataFrame(all_events)
    df_events.to_csv(os.path.join(outputs_dir, "event_log.csv"), index=False)
    print("Saved outputs/event_log.csv")

    try:
        from generate_trace import generate_trace
        generate_trace()
    except Exception as exc:
        print(f"Warning: could not run generate_trace: {exc}")


if __name__ == "__main__":
    run_all_and_save()
