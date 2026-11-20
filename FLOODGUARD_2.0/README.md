# FLOODGUARD 2.0
**Intelligent Flood Evacuation and Resource Allocation System Using Adaptive Graph Optimization**
Study area: Velachery, Chennai · Final-year Computer Science Engineering project

## 1. Overview
FLOODGUARD 2.0 is a Streamlit application built from the original Google Colab notebook
(`Flood_Evacuation_Project.ipynb`) and the earlier Streamlit project. It runs completely on your own computer and does not need Google Colab.
It reuses the notebook's real road network, flood classification, Dijkstra, A*, dynamic rerouting, Minimum-Cost Flow
shelter allocation and greedy vehicle assignment. The previous project was not modified.

### Real data vs simulated data
| Item | Type |
|---|---|
| Road network: 4,471 intersections, 11,452 road segments, shapes, names, lengths | **REAL** - OpenStreetMap (downloaded with OSMnx in the notebook) |
| Flood depth of every road (0-80 cm, `np.random.seed(42)`) | **SIMULATED** - random values, *not* flood measurements |
| Safe / moderate / blocked classes (30 cm / 70 cm thresholds, moderate roads cost x3) | Derived from the simulated depth |
| Affected areas and population, shelters and capacities, vehicles | **SIMULATED** prototype values from notebook cell 15 |
| Road blockage reports | **User input, UNVERIFIED** |

## 2. Features (six pages)
1. **Dashboard** - road counts by flood status, affected population, shelters, vehicles, area severity, map preview.
2. **Interactive Flood Map** - real roads in green / orange / red, affected areas, shelters, legend, tooltips.
3. **Route Optimization** - choose start and destination, run Dijkstra, A* or both; distance, cost, intersections, map.
4. **Dynamic Rerouting** - select a road (from the route list or by clicking the map), submit a blockage report
   (Flooding / Fallen tree or debris / Road damage / Other obstruction), and see the original route, the blocked road
   and the alternative route with the differences. The report blocks the road in both directions on a *copy* of the graph.
5. **Resource Allocation** - A Affected Areas -> B Shelters -> C Vehicles -> D Run Evacuation Allocation -> E Results.
   You choose which areas to evacuate and how many people; shelter capacity and vehicle quantities are validated;
   shortages are reported as warnings.
6. **Analytics and Comparison** - Dijkstra vs A* (measured), rerouting test, shelter and vehicle utilisation,
   theoretical complexity (clearly separated from measured results).

## 3. Technology stack
Python, Streamlit, NetworkX, Folium, streamlit-folium, Pandas, NumPy, Matplotlib. OSMnx is only needed if you want to
download a new road network; the saved network is in `data/`.

## 4. Folder structure
```
FLOODGUARD_2.0/
├── app.py                  Streamlit entry point + navigation
├── ui.py                   Cards, tables, charts, map display helpers
├── state.py                Loads the saved data once for all pages
├── maps.py                 Folium map builders
├── views/                  One file per page (dashboard, flood_map, route, rerouting, resources, analytics)
├── core/
│   ├── config.py           Constants from the notebook (centre, thresholds, x3 multiplier)
│   ├── network.py          Road network, flood classification, flood-aware graph
│   ├── routing.py          Dijkstra, A*, benchmarks, nodes explored
│   ├── blockage.py         User blockage reports + dynamic rerouting
│   ├── allocation.py       Minimum-Cost Flow, greedy vehicles, validation
│   └── analytics.py        Measured comparisons for the analytics page
├── data/
│   ├── velachery_nodes.csv, velachery_edges.geojson   real roads + simulated flood depth
│   ├── scenario.json, metadata.json                   simulated scenario, data provenance
│   └── blockage_reports.json                          created when the first report is submitted
├── tests/
│   ├── test_floodguard.py  62 logic tests (includes the previous project's 25 checks)
│   └── smoke_ui_stub.py    Mock-based page smoke test (NOT a browser test)
├── assets/                 style.css, logo.svg
├── .streamlit/config.toml  Light theme
├── requirements.txt
└── README.md
```

## 5. Windows setup
1. Install **Python 3.10, 3.11 or 3.12** from python.org and tick **"Add python.exe to PATH"**.
2. Unzip `FLOODGUARD_2.0.zip`, open **Command Prompt** and go into the folder:
   ```
   cd C:\path\to\FLOODGUARD_2.0
   ```
3. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
   (PowerShell: if activation is blocked run `Set-ExecutionPolicy -Scope Process Bypass` first. If `python` is not found, use `py -m venv venv`.)
4. Install the libraries:
   ```
   pip install -r requirements.txt
   ```
5. Run the tests (optional but recommended):
   ```
   python -m tests.test_floodguard
   python -m tests.smoke_ui_stub
   ```
6. Start the application:
   ```
   streamlit run app.py
   ```
   The browser opens at http://localhost:8501. Stop with `Ctrl + C`.

### Common problems
| Problem | Fix |
|---|---|
| `'streamlit' is not recognized` | Activate the venv, or run `python -m streamlit run app.py` |
| `ModuleNotFoundError` | Activate the venv, then `pip install -r requirements.txt` |
| `FileNotFoundError ... data` | Run the commands from inside the project folder; keep `data/` next to `app.py` |
| Map background is grey | Needs internet for the Esri tiles; switch to "OpenStreetMap" in the layer control |
| Port in use | `streamlit run app.py --server.port 8502` |

## 6. Testing - what is and is not covered
* `tests/test_floodguard.py` (62 tests): the previous project's 25 checks (4,471 nodes, 11,452 edges, 9,886 flood-aware edges,
  54-intersection Dijkstra route of cost 8886.24, 77-intersection alternative route, allocation table, 95 of 100 people with vehicles, ...),
  plus tests for user-reported blockages, partial evacuation selection, input validation, insufficient shelter / vehicle capacity,
  unreachable areas, "no alternative route", report storage, and a check that the four data files are byte-identical to the originals.
* `tests/smoke_ui_stub.py` runs the code of all six pages **with stand-ins for Streamlit and Folium**. It catches coding mistakes
  but does **not** prove the screens look or behave correctly in a browser.
* **Not tested:** the real Streamlit interface in a browser, real map rendering and map-click selection, Windows installation.
  Please run the app once and click through every page before your demonstration.

## 7. Known limitations (be upfront about these in your viva)
* The notebook has **no real town names, vehicle types, vehicle locations or shelter occupancy**. The app shows "Area A-C", "Shelter 1-3" and
  the nearest OpenStreetMap road name; vehicles are the notebook's 5 identical 20-passenger vehicles (grouped as one row with quantity 5).
* Flood depths are random, unrelated to terrain, and each *direction* of a street has its own random value (as in the notebook).
* Moderate roads cost x3 - a modelling assumption, not calibrated to real driving behaviour.
* Areas, shelters and vehicles were placed along one route in the notebook - illustrative, not real locations.
* **Travel time is not shown**: the notebook has no speed or traffic data to calculate it from.
* Blockage reports are **unverified** and stored in `data/blockage_reports.json` on this computer only: not shared between users, no
  authentication, no verification. Earlier reports are applied on the Dynamic Rerouting page only (not on the other pages).
* Vehicle assignment is the notebook's **basic greedy, one-trip** assignment, not a vehicle-routing optimiser; return trips and travel times are not modelled.
* In the measurements A* explores fewer intersections but can be slower in wall-clock time because the Python heuristic adds work per step.
* The notebook's first thresholds (20 / 50 cm) made the start unreachable; the app uses the notebook's final thresholds (30 / 70 cm).
