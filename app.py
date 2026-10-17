"""
app.py — Streamlit interactive dashboard for the
Multi-Agent Air Traffic Conflict Resolution and Route Planning simulation.

Launch:  python -m streamlit run app.py
"""

from __future__ import annotations

from typing import List, Tuple, Dict, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import streamlit as st

from src.models import (
    Aircraft,
    ComparisonRow,
    GridConfig,
)
from src.scenarios import SCENARIO_REGISTRY
from src.simulation import Simulation
from src.metrics import metrics_to_dataframe, comparison_table, events_to_dataframe
from src.conflict_detection import detect_conflicts


# ──────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ATC · Multi-Agent Air Traffic Conflict Resolution",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ──────────────────────────────────────────────────────────────────────
# Custom CSS for premium look
# ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #0e1117; }
    /* Metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1f2e 0%, #16192b 100%);
        border: 1px solid #2a2f42;
        border-radius: 12px;
        padding: 16px;
    }
    div[data-testid="stMetric"] label {
        color: #8892b0 !important;
        font-size: 0.85rem !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #ccd6f6 !important;
        font-size: 1.6rem !important;
    }
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a0f1a 0%, #111827 100%);
        border-right: 1px solid #1e293b;
    }
    /* Headers */
    h1, h2, h3 { color: #e2e8f0 !important; }
    /* Tables */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────
# Session state initialization
# ──────────────────────────────────────────────────────────────────────
if "sim" not in st.session_state:
    st.session_state.sim = None
if "sim_scenario_name" not in st.session_state:
    st.session_state.sim_scenario_name = ""
if "all_sims" not in st.session_state:
    st.session_state.all_sims = None
if "comparison_rows" not in st.session_state:
    st.session_state.comparison_rows = []


# ──────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ✈️ ATC Simulation")
    st.markdown("**Multi-Agent Air Traffic Conflict Resolution**")
    st.divider()

    algorithm = st.selectbox("🔍 Algorithm", ["A*", "UCS"], index=0)

    scenario_name = st.selectbox(
        "📋 Scenario",
        list(SCENARIO_REGISTRY.keys()),
        index=0,
    )
    scenario_fn, scenario_desc = SCENARIO_REGISTRY[scenario_name]
    st.caption(scenario_desc)

    st.divider()
    max_time = st.slider("⏱ Planning Horizon", 20, 200, 100, step=10)
    max_replan = st.slider("🔄 Max Replan Attempts", 1, 10, 3)
    max_exec = st.slider("🏁 Max Execution Steps", 50, 500, 200, step=50)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        btn_plan = st.button("🗺️ Plan", use_container_width=True)
    with col2:
        btn_run = st.button("▶️ Run", use_container_width=True)

    btn_run_all = st.button("🧪 Run All Scenarios", use_container_width=True)
    btn_compare = st.button("📊 A* vs UCS Compare", use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# Visualization helpers
# ──────────────────────────────────────────────────────────────────────

def draw_airspace(
    grid: GridConfig,
    aircraft_list: List[Aircraft],
    title: str = "Airspace",
    time_step: Optional[int] = None,
) -> plt.Figure:
    """Draw the airspace grid with aircraft paths and positions."""
    fig, ax = plt.subplots(1, 1, figsize=(10, 10), facecolor="#0e1117")
    ax.set_facecolor("#0e1117")

    w, h = grid.width, grid.height

    # Grid lines
    for x in range(w + 1):
        ax.axvline(x, color="#1e293b", linewidth=0.5)
    for y in range(h + 1):
        ax.axhline(y, color="#1e293b", linewidth=0.5)

    # Restricted cells
    for rx, ry in grid.restricted_cells:
        rect = plt.Rectangle((rx, ry), 1, 1, facecolor="#ef4444", alpha=0.35, edgecolor="#ef4444", linewidth=0.5)
        ax.add_patch(rect)

    # Aircraft paths and positions
    legend_handles = []
    for ac in aircraft_list:
        color = ac.color

        # Planned path (faint dashed guide)
        if ac.planned_path:
            xs = [p[0] + 0.5 for p in ac.planned_path]
            ys = [p[1] + 0.5 for p in ac.planned_path]
            ax.plot(xs, ys, color=color, linewidth=1.5, alpha=0.35, linestyle="--")

        # Dynamic executed trail up to time_step
        trail_source = ac.executed_path if ac.executed_path else ac.planned_path
        if trail_source:
            if time_step is not None:
                step_limit = min(time_step + 1, len(trail_source))
                visible_trail = trail_source[:step_limit]
            else:
                visible_trail = trail_source
            if len(visible_trail) > 1:
                xs = [p[0] + 0.5 for p in visible_trail]
                ys = [p[1] + 0.5 for p in visible_trail]
                ax.plot(xs, ys, color=color, linewidth=3, alpha=0.9)

        # Start marker
        ax.plot(ac.start[0] + 0.5, ac.start[1] + 0.5, "s", color=color, markersize=14, markeredgecolor="white", markeredgewidth=1.5)

        # Goal marker
        ax.plot(ac.goal[0] + 0.5, ac.goal[1] + 0.5, "*", color=color, markersize=18, markeredgecolor="white", markeredgewidth=1)

        # Current position at time_step
        if time_step is not None and ac.planned_path:
            t = min(time_step, len(ac.planned_path) - 1)
            cp = ac.planned_path[t]
        else:
            cp = ac.current_position or ac.start
        ax.plot(cp[0] + 0.5, cp[1] + 0.5, "o", color=color, markersize=20, alpha=0.9, markeredgecolor="white", markeredgewidth=2)
        ax.annotate(ac.aircraft_id, (cp[0] + 0.5, cp[1] + 0.5), color="white", fontsize=7, ha="center", va="center", fontweight="bold")

        legend_handles.append(mpatches.Patch(color=color, label=f"{ac.aircraft_id} ({ac.status.value})"))

    # Restricted legend
    legend_handles.append(mpatches.Patch(color="#ef4444", alpha=0.35, label="Restricted"))

    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.set_xlabel("X", color="#8892b0", fontsize=12)
    ax.set_ylabel("Y", color="#8892b0", fontsize=12)
    ax.set_title(title, color="#e2e8f0", fontsize=16, pad=15, fontweight="bold")
    ax.tick_params(colors="#64748b")
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8,
              facecolor="#1a1f2e", edgecolor="#2a2f42", labelcolor="#ccd6f6")
    ax.invert_yaxis()

    fig.tight_layout()
    return fig


def draw_comparison_charts(df: pd.DataFrame) -> plt.Figure:
    """Draw comparison bar charts for A* vs UCS."""
    metrics_to_plot = ["Nodes Expanded", "Runtime (ms)", "Path Cost"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor="#0e1117")

    for ax, metric in zip(axes, metrics_to_plot):
        ax.set_facecolor("#0e1117")
        scenarios = df["Scenario"].unique()
        x = np.arange(len(scenarios))
        width = 0.35

        astar_vals = []
        ucs_vals = []
        for s in scenarios:
            a_row = df[(df["Scenario"] == s) & (df["Algorithm"] == "A*")]
            u_row = df[(df["Scenario"] == s) & (df["Algorithm"] == "UCS")]
            val_a = pd.to_numeric(a_row[metric].values[0], errors='coerce') if len(a_row) > 0 else 0
            val_u = pd.to_numeric(u_row[metric].values[0], errors='coerce') if len(u_row) > 0 else 0
            astar_vals.append(0 if pd.isna(val_a) else float(val_a))
            ucs_vals.append(0 if pd.isna(val_u) else float(val_u))

        bars1 = ax.bar(x - width / 2, astar_vals, width, label="A*", color="#3b82f6", alpha=0.85)
        bars2 = ax.bar(x + width / 2, ucs_vals, width, label="UCS", color="#f59e0b", alpha=0.85)

        ax.set_title(metric, color="#e2e8f0", fontsize=12, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([s.split(". ")[1] if ". " in s else s for s in scenarios],
                           rotation=30, ha="right", fontsize=8, color="#8892b0")
        ax.tick_params(colors="#64748b")
        ax.legend(fontsize=8, facecolor="#1a1f2e", edgecolor="#2a2f42", labelcolor="#ccd6f6")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#2a2f42")
        ax.spines["left"].set_color("#2a2f42")

    fig.tight_layout()
    return fig


# ──────────────────────────────────────────────────────────────────────
# Core actions
# ──────────────────────────────────────────────────────────────────────

def _run_scenario(scenario_name, scenario_fn, algo, mt, mr, me):
    """Run a single scenario and return the Simulation object."""
    grid, aircraft = scenario_fn()
    aircraft = [Aircraft(a.aircraft_id, a.start, a.goal, a.priority, a.color) for a in aircraft]
    sim = Simulation(grid, aircraft, algorithm=algo, max_time=mt,
                     max_replan_attempts=mr, max_execution_steps=me)
    sim.plan()
    sim.run_full()
    return sim


# ──────────────────────────────────────────────────────────────────────
# Handle buttons
# ──────────────────────────────────────────────────────────────────────

if btn_plan:
    st.session_state.all_sims = None
    grid, aircraft = scenario_fn()
    aircraft = [Aircraft(a.aircraft_id, a.start, a.goal, a.priority, a.color) for a in aircraft]
    sim = Simulation(grid, aircraft, algorithm=algorithm, max_time=max_time,
                     max_replan_attempts=max_replan, max_execution_steps=max_exec)
    sim.plan()
    st.session_state.sim = sim
    st.session_state.sim_scenario_name = scenario_name

if btn_run:
    st.session_state.all_sims = None
    # If already planned for this exact scenario and algorithm, run execution directly
    if (st.session_state.sim is not None
        and st.session_state.sim_scenario_name == scenario_name
        and st.session_state.sim.algorithm == algorithm
        and st.session_state.sim._has_planned):
        st.session_state.sim.run_full()
    else:
        grid, aircraft = scenario_fn()
        aircraft = [Aircraft(a.aircraft_id, a.start, a.goal, a.priority, a.color) for a in aircraft]
        sim = Simulation(grid, aircraft, algorithm=algorithm, max_time=max_time,
                         max_replan_attempts=max_replan, max_execution_steps=max_exec)
        sim.plan()
        sim.run_full()
        st.session_state.sim = sim
        st.session_state.sim_scenario_name = scenario_name

if btn_run_all:
    all_sims = {}
    for sname, (sfn, sdesc) in SCENARIO_REGISTRY.items():
        all_sims[sname] = _run_scenario(sname, sfn, algorithm, max_time, max_replan, max_exec)
    st.session_state.all_sims = all_sims
    first_name = list(all_sims.keys())[0]
    st.session_state.sim = all_sims[first_name]
    st.session_state.sim_scenario_name = first_name

if btn_compare:
    st.session_state.all_sims = None
    rows: List[ComparisonRow] = []
    for sname, (sfn, sdesc) in SCENARIO_REGISTRY.items():
        for algo in ["A*", "UCS"]:
            sim = _run_scenario(sname, sfn, algo, max_time, max_replan, max_exec)
            m = sim.compute_metrics()
            is_success = m.aircraft_failed == 0 and m.aircraft_completed > 0
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
    st.session_state.comparison_rows = rows
    sfn0, _ = list(SCENARIO_REGISTRY.values())[0]
    first_name = list(SCENARIO_REGISTRY.keys())[0]
    st.session_state.sim = _run_scenario(first_name, sfn0, algorithm, max_time, max_replan, max_exec)
    st.session_state.sim_scenario_name = first_name


# ══════════════════════════════════════════════════════════════════════
# MAIN DISPLAY
# ══════════════════════════════════════════════════════════════════════

# Title bar
st.markdown("""
<div style="text-align:center; padding: 1.5rem 0 0.5rem 0;">
    <h1 style="margin:0; font-size:2.2rem; background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
               -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
        ✈️ Multi-Agent Air Traffic Conflict Resolution
    </h1>
    <p style="color:#8892b0; margin-top:0.3rem; font-size:1rem;">
        23CSE401 — Fundamentals of Artificial Intelligence · A* &amp; UCS Route Planning with Space-Time Coordination
    </p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────
# Tab layout
# ──────────────────────────────────────────────────────────────────────
tab_viz, tab_metrics, tab_compare, tab_log, tab_about = st.tabs(
    ["🗺️ Airspace", "📈 Metrics", "⚖️ A* vs UCS", "📋 Event Log", "ℹ️ About"]
)

sim: Optional[Simulation] = st.session_state.sim

# ──────────────────────────────────────────────────────────────────────
# TAB: Airspace Visualization
# ──────────────────────────────────────────────────────────────────────
with tab_viz:
    if sim is None:
        st.info("👈 Select a scenario and click **Plan** or **Run** to begin.")
    else:
        active_scenario = st.session_state.sim_scenario_name or scenario_name
        st.markdown(f"**Scenario:** {active_scenario}  ·  **Algorithm:** {sim.algorithm}  ·  **State:** `{sim.state.value}`")

        # Time slider with unique key per scenario/algorithm/length to prevent state range crashes
        max_t = sim.get_max_path_length()
        slider_key = f"t_slider_{active_scenario}_{sim.algorithm}_{max_t}"
        if max_t > 1:
            t_step = st.slider("Time Step", 0, max_t - 1, max_t - 1, key=slider_key)
        else:
            t_step = 0

        fig = draw_airspace(sim.grid, sim.aircraft, title=f"Airspace — {active_scenario}", time_step=t_step)
        st.pyplot(fig)
        plt.close(fig)

        # Aircraft details table
        st.markdown("### Aircraft Details")
        ac_data = []
        for ac in sim.aircraft:
            ac_data.append({
                "ID": ac.aircraft_id,
                "Start": str(ac.start),
                "Goal": str(ac.goal),
                "Priority": ac.priority,
                "Status": ac.status.value,
                "Route Cost": ac.route_cost,
                "Waiting Time": ac.waiting_time,
                "Arrival Time": str(ac.arrival_time) if ac.arrival_time is not None else "—",
                "Path Length": len(ac.planned_path),
                "Nodes Expanded": ac.search_result.nodes_expanded if ac.search_result else 0,
            })
        st.dataframe(pd.DataFrame(ac_data), use_container_width=True, hide_index=True)

        # Batch Run All Scenarios Table (if run_all was clicked)
        if st.session_state.all_sims is not None:
            st.divider()
            st.markdown("### 🧪 Batch Benchmark: All Scenarios Summary")
            summary_data = []
            for sname, s_obj in st.session_state.all_sims.items():
                sm = s_obj.compute_metrics()
                summary_data.append({
                    "Scenario": sname,
                    "Algorithm": s_obj.algorithm,
                    "Status": s_obj.state.value,
                    "Completed": sm.aircraft_completed,
                    "Failed": sm.aircraft_failed,
                    "Route Cost": sm.total_route_cost if sm.aircraft_completed > 0 else "N/A",
                    "Expanded": sm.total_nodes_expanded,
                    "Wait Steps": sm.total_waiting_time if sm.aircraft_completed > 0 else "N/A",
                    "Makespan": sm.makespan if sm.aircraft_completed > 0 else "N/A",
                    "Conflicts (before)": sm.conflicts_before_resolution,
                    "Unresolved": sm.unresolved_conflicts,
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────────────────────────────
# TAB: Metrics
# ──────────────────────────────────────────────────────────────────────
with tab_metrics:
    if sim is None:
        st.info("Run a scenario to see metrics.")
    else:
        m = sim.compute_metrics()
        st.markdown("### 📊 Performance Metrics")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("✅ Completed", m.aircraft_completed)
        c2.metric("❌ Failed", m.aircraft_failed)
        c3.metric("💰 Total Cost", f"{m.total_route_cost:.1f}")
        c4.metric("⏱ Makespan", m.makespan)

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("🚶 Movements", m.total_movements)
        c6.metric("⏳ Waiting", m.total_waiting_time)
        c7.metric("⚠️ Conflicts (before)", m.conflicts_before_resolution)
        c8.metric("🚨 Unresolved", m.unresolved_conflicts)

        c9, c10, c11, c12 = st.columns(4)
        c9.metric("🔍 Nodes Expanded", m.total_nodes_expanded)
        c10.metric("🌐 Nodes Generated", m.total_nodes_generated)
        c11.metric("⚡ Search Time", f"{m.total_search_runtime_ms:.2f} ms")
        c12.metric("🔄 Replanning", m.replanning_attempts)

        st.divider()
        st.markdown("### Metric Definitions")
        st.markdown("""
        | Metric | Definition |
        |--------|-----------|
        | **Completed** | Aircraft that reached their destination |
        | **Failed** | Aircraft where planning or execution failed |
        | **Total Cost** | Sum of all planned route costs (each step = 1) |
        | **Makespan** | Time step when the last successful aircraft arrived |
        | **Movements** | Total number of movement steps (excluding waits) |
        | **Waiting** | Total time steps spent waiting in place |
        | **Conflicts (before)** | Conflicts detected before coordination resolved them |
        | **Unresolved** | Conflicts remaining after all replanning attempts |
        | **Nodes Expanded** | Total search nodes expanded across all aircraft |
        | **Nodes Generated** | Total search nodes generated (put in open list) |
        | **Search Time** | Wall-clock time spent in search algorithms |
        | **Replanning** | Number of priority-reorder replanning attempts |
        """)

        # CSV export
        st.divider()
        st.markdown("### 📥 Export")
        df_metrics = metrics_to_dataframe(m)
        csv_metrics = df_metrics.to_csv(index=False)
        st.download_button("Download Metrics CSV", csv_metrics, "metrics.csv", "text/csv")

# ──────────────────────────────────────────────────────────────────────
# TAB: A* vs UCS Comparison
# ──────────────────────────────────────────────────────────────────────
with tab_compare:
    if not st.session_state.comparison_rows:
        st.info("Click **A* vs UCS Compare** in the sidebar to run both algorithms across all scenarios.")
    else:
        rows = st.session_state.comparison_rows
        df = comparison_table(rows)
        st.markdown("### ⚖️ Algorithm Comparison Table")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("### 📊 Comparison Charts")
        fig = draw_comparison_charts(df)
        st.pyplot(fig)
        plt.close(fig)

        st.divider()
        st.markdown("""
        > **Note:** Runtime measurements depend on the machine and environment.
        > A\\* uses Manhattan distance as an admissible heuristic, which reduces
        > node expansions compared to UCS (Dijkstra) while guaranteeing optimal
        > paths under uniform costs.
        """)

        csv_comp = df.to_csv(index=False)
        st.download_button("Download Comparison CSV", csv_comp, "comparison.csv", "text/csv")

# ──────────────────────────────────────────────────────────────────────
# TAB: Event Log
# ──────────────────────────────────────────────────────────────────────
with tab_log:
    if sim is None or not sim.events:
        st.info("Run a scenario to see the event log.")
    else:
        st.markdown("### 📋 Simulation Event Log")
        df_events = events_to_dataframe(sim.events)
        st.dataframe(df_events, use_container_width=True, hide_index=True, height=500)

        csv_events = df_events.to_csv(index=False)
        st.download_button("Download Event Log CSV", csv_events, "event_log.csv", "text/csv")

# ──────────────────────────────────────────────────────────────────────
# TAB: About
# ──────────────────────────────────────────────────────────────────────
with tab_about:
    st.markdown("""
    ## About This Project

    **Multi-Agent Air Traffic Conflict Resolution and Route Planning**

    Course: **23CSE401 — Fundamentals of Artificial Intelligence**

    ---

    ### 🎯 Objective
    Demonstrate genuine AI search, multi-agent coordination, conflict detection/resolution,
    and algorithm comparison through an interactive airspace simulation.

    ### 🔍 Algorithms
    - **A\\* Search**: Priority queue–based graph search using f(n) = g(n) + h(n) with
      Manhattan distance heuristic. Operates in (x, y, t) space-time.
    - **Uniform-Cost Search (UCS)**: Dijkstra-style search using g(n) only. Serves as
      the comparison baseline.

    ### 🤝 Multi-Agent Coordination
    - **Prioritized space-time planning**: Aircraft planned in priority order, each
      reserving future cell occupancies and transitions.
    - **Conflict detection**: Independent validation for vertex conflicts, edge-swap
      conflicts, restricted-cell violations, and invalid moves.
    - **Bounded replanning**: Alternative priority orders tried when conflicts persist.

    ### ⚠️ Limitations
    - Prioritized planning is **not guaranteed** to find a solution for every feasible
      multi-agent problem, even when one exists.
    - Runtime measurements depend on the specific machine and environment.
    - The simulation uses a configurable planning horizon; problems requiring longer
      horizons may be reported as infeasible.

    ### 📐 Complexity
    | Component | Complexity |
    |-----------|-----------|
    | A\\* / UCS search | O(b^d) worst case, where b = branching factor, d = depth |
    | Manhattan heuristic | Reduces exploration in practice but doesn't change worst case |
    | Space-time expansion | Multiplies state space by planning horizon T |
    | Pairwise conflict check | O(k² · T) for k aircraft over T time steps |
    | Prioritized planning (k aircraft) | k sequential searches with growing reservations |
    | Replanning | Up to max_replan_attempts × full planning cycle |

    ---

    *Built with Python, Streamlit, Matplotlib, and Pandas. No ML models, GPUs, or external APIs required.*
    """)
