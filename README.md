# Multi-Agent Air Traffic Conflict Resolution and Route Planning

**Course:** 23CSE401 — Fundamentals of Artificial Intelligence (Assignment 2)

An interactive airspace simulation demonstrating genuine AI search (A\* and UCS),
multi-agent coordination, collision detection, conflict resolution, and algorithm
comparison using prioritized space-time planning.

---

## 🎯 Project Overview

This project simulates multiple aircraft navigating a 2D grid-based airspace.
Each aircraft plans its route using **A\* Search** or **Uniform-Cost Search (UCS)**
in `(x, y, t)` space-time, and a coordination layer detects and resolves conflicts
(vertex collisions, head-on edge-swaps, and destination parking conflicts) using
prioritized planning with time-dependent reservations.

### Key Features

- **Genuine A\* and UCS** priority-queue implementations in $(x, y, t)$ space-time
- **Destination Parking Invariance** — destination cells are reserved through the horizon upon arrival to prevent late-arrival collisions
- **Multi-agent conflict detection** — independent validator for vertex, edge-swap, restricted-cell, and invalid-move conflicts
- **Prioritized space-time planning** with bounded replanning and deterministic tie-breaking
- **Interactive Streamlit dashboard** with real-time visualization and step-by-step playback
- **Algorithm comparison** (A\* vs UCS) with automated CSV logging and metrics tables
- **7 deterministic benchmark scenarios** including corridor bottleneck queuing and enclosed unreachable goals
- **67 automated tests** with pytest (100% pass rate)
- **Zero active collisions** across all executed benchmark scenarios

---

## 📋 Prerequisites

- **Python 3.11+** (tested with Python 3.12)
- **pip** (comes with Python)
- **Windows / macOS / Linux** (all scripts are cross-platform)

No GPU, external network connection (after install), ML weights, or paid APIs are required.

---

## 🚀 Installation & Setup

### 1. Create a virtual environment

```powershell
# Navigate to project directory
cd "FAI ASSINGMENT 2"
python -m venv .venv
```

### 2. Activate the virtual environment

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

---

## ▶️ Running the Application

### 1. Launch the Streamlit dashboard

```powershell
python -m streamlit run app.py
```
The app will open at `http://localhost:8501` in your browser.
 
### 2. Run the test suite (67 automated tests)
 
```powershell
python -m pytest -v
```
 
### 3. Generate benchmark metrics, traces, and CSV logs
 
```powershell
python generate_outputs.py
```
Runs all 7 scenarios across A\* and UCS, saving aggregate comparative results to `outputs/comparison.csv`, detailed per-aircraft metrics for Scenario 7 (A\*) to `outputs/metrics.csv`, all scenario events tagged with `Scenario` and `Algorithm` to `outputs/event_log.csv`, and generates the real search expansion trace to `outputs/trace_scenario2_AC-2_astar.csv` and `reports/trace_table.tex`.
 
You can also generate the trace standalone:
```powershell
python generate_trace.py
```

### 4. Build the PowerPoint presentation

```powershell
python presentation/make_presentation.py
```
Generates `presentation/presentation.pptx` with complete slides, benchmark tables, and architecture diagrams.

### 5. Compile the LaTeX academic report

```powershell
# Compile reports/report.tex using pdflatex (or upload report.tex to Overleaf)
pdflatex -output-directory=reports reports/report.tex
```

---

## 🗺️ How to Use

### Running Scenarios

1. **Select a scenario** from the sidebar dropdown
2. **Choose an algorithm** (A\* or UCS)
3. **Click "Plan"** to compute routes, or **"Run"** to plan and execute the simulation
4. **Use the time slider** to step through the simulation
5. **Click "A\* vs UCS Compare"** to run both algorithms on all scenarios

### Available Scenarios

| # | Scenario | Description |
|---|----------|-------------|
| 1 | Conflict-Free Routes | Two aircraft on separate rows — no conflicts (A\* expands 18 vs UCS 456) |
| 2 | Crossing Routes | Intersecting paths — in-air holding / wait action deconfliction |
| 3 | Unreachable Destination | Enclosed goal — planner safely proves infeasibility (8,372 states explored) |
| 4 | Narrow Corridor | Bidirectional bottleneck — lower-priority flights queue outside until cleared |
| 5 | Start Equals Goal | Trivial boundary case — aircraft already at destination |
| 6 | Head-On Collision | Opposite-direction aircraft — reverse-edge reservation forces lateral detour |
| 7 | Five Aircraft (Default) | Five aircraft on 12×12 grid with obstacles, destination parking, and 0 conflicts |

### Exporting Data

- **Metrics CSV** — from the 📈 Metrics tab (`outputs/metrics.csv`)
- **Event Log CSV** — from the 📋 Event Log tab (`outputs/event_log.csv`)
- **Comparison CSV** — from the ⚖️ A\* vs UCS tab (`outputs/comparison.csv`)

---

## 📁 Project Structure

```
FAI ASSINGMENT 2/
├── app.py                      # Streamlit dashboard entry point
├── generate_outputs.py         # Batch benchmark runner (exports CSVs)
├── generate_trace.py           # Real search expansion trace generator
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
├── .gitignore
│
├── src/                        # Core simulation modules
│   ├── __init__.py
│   ├── models.py               # Data structures (Aircraft, Grid, Conflict, etc.)
│   ├── environment.py          # Grid creation, movement ($b=5$), validation
│   ├── search.py               # A* and UCS implementations in (x, y, t) with tracing
│   ├── reservations.py         # Space-time reservation table (cells, edges, parking)
│   ├── conflict_detection.py   # Independent trajectory conflict validator
│   ├── coordinator.py          # Multi-agent prioritized planning & replanning
│   ├── simulation.py           # Simulation lifecycle and execution engine
│   ├── metrics.py              # Performance measurement and CSV exports
│   └── scenarios.py            # Deterministic scenario library
│
├── tests/                      # Automated test suite
│   ├── __init__.py
│   └── test_core.py            # 67 tests covering search, safety, invariants, traces, & edge cases
│
├── reports/                    # Academic report
│   ├── report.tex              # Comprehensive LaTeX source
│   ├── trace_table.tex         # Real measured trace LaTeX fragment (\input in report)
│   └── report.pdf              # Compiled 10-page academic report (pdflatex)
│
├── presentation/               # Presentation materials
│   ├── make_presentation.py    # Generates academic PowerPoint (reads comparison.csv)
│   └── presentation.pptx       # 10-slide academic presentation
│
├── data/                       # Scenario configurations
│   └── scenarios.json          # Machine-readable scenario definitions (loaded by src.scenarios)
│
└── outputs/                    # Generated CSV logs and metrics
    ├── comparison.csv          # Full A* vs UCS empirical comparison table
    ├── metrics.csv             # Detailed metrics for Scenario 7 (5-Aircraft Default, A*)
    ├── event_log.csv           # Chronological simulation event log with Scenario & Algorithm tags
    └── trace_scenario2_AC-2_astar.csv  # Real step-by-step search expansion trace
```

---

## 🔍 Algorithm Explanations

### Agent Architecture

- **Classification:** Goal-Based Cooperative Multi-Agent System with Centralized Prioritized Coordination.
- **Agent Nature:** Aircraft agents are goal-based with discrete unit transit costs; they submit route requests to a central coordinator rather than optimizing individual utility functions.

### A\* Search

- **Priority function:** $f(n) = g(n) + h(n)$
- **Heuristic:** Manhattan distance $|x - g_x| + |y - g_y|$
- **Guarantee:** Optimal path per individual search under fixed reservations (Manhattan distance is strictly admissible and consistent on a 4-connected grid with unit costs). Prioritized planning does not guarantee joint global optimality across all aircraft (Scenario 7: A* 90.0 vs UCS 89.0).
- **State space:** $(x, y, t)$ — position plus discrete time step
- **Branching factor:** $b = 5$ (Up, Down, Left, Right, and in-air Wait)
- **Graph search bound:** $O(W \cdot H \cdot T_{\max})$ distinct space-time states

### Uniform-Cost Search (UCS)

- **Priority function:** $g(n)$ (cost from start, equivalent to $h(n) = 0$)
- **Guarantee:** Optimal path per individual search under non-negative transition costs
- **Comparison:** Explores states isotropically in all directions; serves as unguided baseline to quantify heuristic pruning efficiency

### Multi-Agent Coordination & Parking Invariance

- **Method:** Prioritized space-time planning with reverse-edge locks and destination parking reservations.
- **Process:** Plan aircraft sequentially by priority rank (breaking ties deterministically by ID), reserve space-time positions, and replan on deadlock.
- **Destination Parking Invariant:** When an aircraft reaches its destination at time $t_{\text{arr}}$, the goal cell is reserved for all $t \in [t_{\text{arr}}, T_{\max}]$, ensuring lower-priority aircraft do not traverse or park on occupied goal cells.
- **Conflict types detected:** Vertex (same cell/time), Edge-swap (head-on), Restricted-cell, Invalid-move.
- **Conflict Metrics Definitions:**
  - `Conflicts Before Coordination`: Counts pairwise vertex collisions and edge-swaps per time step among independently planned, uncoordinated single-agent baseline paths.
  - `Unresolved Conflicts After Coordination`: Counts separation violations remaining in the final coordinated plan (strictly 0 across all benchmark scenarios).
- **Cost Reporting and N/A Policy:** When no route exists for any aircraft (such as in Scenario 3 where the destination is enclosed), Path Cost, Waiting Time, and Makespan are reported as `N/A`. When some aircraft succeed and others fail, the cost is the sum over the aircraft that successfully reached their goal. In Scenario 5 (Start Equals Goal), the route cost is legitimately `0.0`.
- **Partial Planning Execution Policy:** If an individual aircraft cannot reach its destination (e.g. enclosed goal), but remaining flights have zero mutual conflicts, the coordinator allows the conflict-free flights to execute while keeping the failed aircraft safely held at its departure cell (reserved across all time steps). If any unresolved conflicts remain among flights, the simulation strictly halts (`FAILED`).
- **Endpoint Warnings:** If an aircraft's goal coincides with another's start position, a non-blocking configuration warning is logged to guide airspace operators.
- **Replanning:** Priority permutation orderings explored up to `max_replan_attempts` times upon conflict or individual flight plan failure.

---

## ⚠️ Known Limitations

1. **Prioritized planning** is fundamentally incomplete: complex interlocking agent deadlocks cannot be resolved without joint-search techniques such as Conflict-Based Search (CBS).
2. **Planning horizon** is configurable but finite ($T_{\max}$) — problems requiring longer detours are reported as infeasible.
3. **Discrete cellular kinematics:** Continuous aircraft aerodynamics (turn radii, speeds, wind drift) are discretized to grid cell transitions.

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|---------|
| `ModuleNotFoundError` | Activate venv and run `python -m pip install -r requirements.txt` |
| Port 8501 in use | Run `python -m streamlit run app.py --server.port 8502` |
| Tests fail | Ensure you run from project root: `python -m pytest -v` |
| LaTeX compilation | Upload `reports/report.tex` to Overleaf or run `pdflatex reports/report.tex` |

---

## 📚 References

1. Hart, P.E., Nilsson, N.J., Raphael, B. (1968). "A Formal Basis for the Heuristic Determination of Minimum Cost Paths." *IEEE Transactions on Systems Science and Cybernetics*, 4(2):100–107.
2. Russell, S., Norvig, P. (2020). *Artificial Intelligence: A Modern Approach* (4th ed.). Pearson.
3. Silver, D. (2005). "Cooperative Pathfinding." *AIIDE*, 1:117–122.
4. Stern, R., et al. (2019). "Multi-Agent Pathfinding: Definitions, Variants, and Benchmarks." *Symposium on Combinatorial Search (SoCS)*.
5. Sharon, G., Stern, R., Felner, A., Sturtevant, N.R. (2015). "Conflict-Based Search for Optimal Multi-Agent Pathfinding." *Artificial Intelligence*, 219:40–66.
