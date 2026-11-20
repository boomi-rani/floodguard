"""
routing.py - Dijkstra and A* route finding (notebook cells 9 and 16).

  * Dijkstra : nx.shortest_path(..., weight="cost", method="dijkstra")
  * A*       : nx.astar_path(..., heuristic=great-circle distance, weight="cost")
The heuristic never over-estimates (cost >= length >= straight line), so A* is optimal too.
"""
import heapq
import time
from dataclasses import dataclass, field
from typing import List, Optional

import networkx as nx
import numpy as np
import pandas as pd

from core.network import haversine_m


@dataclass
class RouteResult:
    algorithm: str
    source: int
    target: int
    found: bool
    path: List[int] = field(default_factory=list)
    cost: Optional[float] = None
    distance_m: Optional[float] = None
    time_ms: Optional[float] = None
    message: str = ""

    @property
    def intersections(self):
        return len(self.path)

    def edges(self):
        return list(zip(self.path[:-1], self.path[1:]))


def make_heuristic(H):
    def heuristic(a, b):
        na, nb = H.nodes[a], H.nodes[b]
        return haversine_m(na["y"], na["x"], nb["y"], nb["x"])
    return heuristic


def path_weight(H, path, weight="cost"):
    return sum(H[a][b][weight] for a, b in zip(path[:-1], path[1:]))


def _check_nodes(H, source, target):
    if source not in H or target not in H:
        return "Start or destination is not part of the road network."
    if source == target:
        return "Start and destination are the same intersection."
    return ""


def _run(H, source, target, name, finder):
    problem = _check_nodes(H, source, target)
    if problem:
        return RouteResult(name, source, target, False, message=problem)
    t0 = time.perf_counter()
    try:
        path = finder()
    except nx.NetworkXNoPath:
        return RouteResult(name, source, target, False, time_ms=(time.perf_counter() - t0) * 1000,
                           message="No safe route available between these locations.")
    ms = (time.perf_counter() - t0) * 1000
    return RouteResult(name, source, target, True, path, path_weight(H, path),
                       path_weight(H, path, "length"), ms)


def run_dijkstra(H, source, target):
    return _run(H, source, target, "Dijkstra",
                lambda: nx.shortest_path(H, source, target, weight="cost", method="dijkstra"))


def run_astar(H, source, target):
    return _run(H, source, target, "A*",
                lambda: nx.astar_path(H, source, target, heuristic=make_heuristic(H), weight="cost"))


def run_algorithm(H, source, target, algorithm):
    return run_astar(H, source, target) if algorithm == "A*" else run_dijkstra(H, source, target)


# ---- instrumented search: how many intersections does each algorithm expand? -------------
def nodes_expanded(H, source, target, use_astar):
    heuristic = make_heuristic(H) if use_astar else (lambda a, b: 0.0)
    best = {source: 0.0}
    heap = [(heuristic(source, target), 0.0, source)]
    closed = set()
    while heap:
        _, g, node = heapq.heappop(heap)
        if node in closed:
            continue
        closed.add(node)
        if node == target:
            return len(closed)
        for nxt, data in H[node].items():
            ng = g + data["cost"]
            if ng < best.get(nxt, float("inf")):
                best[nxt] = ng
                heapq.heappush(heap, (ng + heuristic(nxt, target), ng, nxt))
    return len(closed)


def benchmark_pair(H, source, target, repeats=10):
    """Average execution time over `repeats` runs (the notebook used 10)."""
    d_t, a_t = [], []
    d = a = None
    for _ in range(repeats):
        d, a = run_dijkstra(H, source, target), run_astar(H, source, target)
        if not (d.found and a.found):
            return {"ok": False, "message": d.message or a.message}
        d_t.append(d.time_ms)
        a_t.append(a.time_ms)
    return {"ok": True, "repeats": repeats, "dijkstra": d, "astar": a,
            "dijkstra_ms": float(np.mean(d_t)), "astar_ms": float(np.mean(a_t)),
            "dijkstra_expanded": nodes_expanded(H, source, target, False),
            "astar_expanded": nodes_expanded(H, source, target, True)}


def benchmark_random_pairs(H, n_pairs=15, repeats=3, seed=42, min_separation_m=1000):
    """Benchmark both algorithms on random reachable pairs (fairer than one pair)."""
    rng = np.random.default_rng(seed)
    core = sorted(max(nx.strongly_connected_components(H), key=len))
    rows, attempts = [], 0
    while len(rows) < n_pairs and attempts < n_pairs * 50:
        attempts += 1
        s, t = (int(x) for x in rng.choice(core, size=2, replace=False))
        na, nb = H.nodes[s], H.nodes[t]
        sep = haversine_m(na["y"], na["x"], nb["y"], nb["x"])
        if sep < min_separation_m:
            continue
        r = benchmark_pair(H, s, t, repeats)
        if not r["ok"]:
            continue
        rows.append({"Pair": len(rows) + 1, "Straight line (m)": round(sep),
                     "Dijkstra ms": r["dijkstra_ms"], "A* ms": r["astar_ms"],
                     "Dijkstra cost": r["dijkstra"].cost, "A* cost": r["astar"].cost,
                     "Dijkstra nodes explored": r["dijkstra_expanded"],
                     "A* nodes explored": r["astar_expanded"],
                     "Same cost": abs(r["dijkstra"].cost - r["astar"].cost) < 1e-6})
    return pd.DataFrame(rows)


# ---- helpers for tables and maps -----------------------------------------------------------
def route_segments(H, path):
    rows = []
    for i, (a, b) in enumerate(zip(path[:-1], path[1:]), start=1):
        d = H[a][b]
        n = d.get("name")
        rows.append({"#": i, "Road": (" / ".join(n) if isinstance(n, list) else n) or "Unnamed road",
                     "From node": a, "To node": b, "Length (m)": round(d["length"], 1),
                     "Flood status (simulated)": d["status"].capitalize(), "Cost": round(d["cost"], 1)})
    return pd.DataFrame(rows)


def path_coordinates(H, path):
    """(lat, lon) points following the real road shapes along a path."""
    coords = []
    for a, b in zip(path[:-1], path[1:]):
        pts = H[a][b]["geometry"]
        coords.extend(pts if not coords else pts[1:])
    return coords


def estimated_travel_time_min(distance_m, speed_kmh=None):
    """Travel time is NOT supported by the notebook data (no speed data) -> returns None."""
    return None
