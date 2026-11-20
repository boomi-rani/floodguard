"""analytics.py - Measured results for the Analytics page (nothing here is invented)."""
import pandas as pd

from core import allocation as al
from core import routing as rt
from core.blockage import process_report, create_report


def route_comparison(H, source, target, repeats=10):
    """Dijkstra vs A* on one pair: measured time (average of `repeats` runs), cost, distance, nodes explored."""
    r = rt.benchmark_pair(H, source, target, repeats)
    if not r["ok"]:
        return {"ok": False, "message": r["message"]}
    d, a = r["dijkstra"], r["astar"]
    table = pd.DataFrame([
        {"Algorithm": "Dijkstra", "Avg time (ms)": r["dijkstra_ms"], "Route cost": d.cost,
         "Distance (m)": d.distance_m, "Intersections": d.intersections, "Nodes explored": r["dijkstra_expanded"]},
        {"Algorithm": "A*", "Avg time (ms)": r["astar_ms"], "Route cost": a.cost,
         "Distance (m)": a.distance_m, "Intersections": a.intersections, "Nodes explored": r["astar_expanded"]}])
    return {"ok": True, "table": table, "repeats": repeats, "same_cost": abs(d.cost - a.cost) < 1e-6,
            "dijkstra": d, "astar": a}


def rerouting_comparison(G, H, source, target, algorithm="Dijkstra"):
    """
    Reroute after blocking each road segment of the current route in turn (a measured test of how the
    network copes with a single blocked road; these are test cases, not real reports).
    """
    base = rt.run_algorithm(H, source, target, algorithm)
    if not base.found:
        return pd.DataFrame()
    rows, seen = [], set()
    for u, v in base.edges():
        if frozenset((u, v)) in seen:
            continue
        seen.add(frozenset((u, v)))
        rep = create_report(G, u, v, "Other obstruction", store=False)
        out = process_report(H, source, target, rep, algorithm)
        alt = out["alternative"]
        rows.append({"Blocked segment #": len(rows) + 1, "Road": rep.road, "Result": out["status"],
                     "Extra distance (m)": out["difference"]["distance_m"] if out["difference"] else None,
                     "Extra cost": out["difference"]["cost"] if out["difference"] else None,
                     "New intersections": alt.intersections if alt and alt.found else None})
    return pd.DataFrame(rows)
