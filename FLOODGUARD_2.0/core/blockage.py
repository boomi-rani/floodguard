"""
blockage.py - User-reported road blockages and dynamic rerouting.

Workflow (notebook cell 14, but driven by a USER REPORT instead of a random/middle road):
  1. user selects a real road and submits a report;
  2. the report is stored (local JSON file, status = UNVERIFIED);
  3. a COPY of the routing graph is made, the road is removed (both directions);
  4. the route is recomputed with the existing Dijkstra / A* functions.
The original graph is never modified.
"""
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from core import config as cfg
from core.network import road_name
from core.routing import run_algorithm


@dataclass
class BlockageReport:
    report_id: str
    u: int
    v: int
    road: str
    lat: float
    lon: float
    reason: str
    description: str
    reported_at: str
    status: str = "Unverified (user report)"


# ----------------------------------------------------------------------------- storage
def load_reports(path=cfg.REPORTS_FILE):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            return [BlockageReport(**r) for r in json.load(fh)]
    except (ValueError, TypeError, OSError):
        return []          # corrupt file -> start empty rather than crash


def save_reports(reports, path=cfg.REPORTS_FILE):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([asdict(r) for r in reports], fh, indent=2)


def create_report(G, u, v, reason, description="", path=cfg.REPORTS_FILE, store=True):
    """Validate and build a report for road u->v of the real network G. Returns the report."""
    if reason not in cfg.BLOCKAGE_REASONS:
        raise ValueError("Please choose a valid reason for the blockage.")
    if not G.has_edge(u, v) and not G.has_edge(v, u):
        raise ValueError("The selected road does not exist in the road network.")
    a, b = (u, v) if G.has_edge(u, v) else (v, u)
    key = next(iter(G[a][b]))
    name = road_name(G[a][b][key])
    lat = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2
    lon = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2
    report = BlockageReport(uuid.uuid4().hex[:8], int(u), int(v), name, lat, lon, reason,
                            (description or "").strip()[:300],
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if store:
        existing = load_reports(path)
        if any({r.u, r.v} == {report.u, report.v} for r in existing):
            raise ValueError("This road segment has already been reported.")
        save_reports(existing + [report], path)
    return report


def delete_report(report_id, path=cfg.REPORTS_FILE):
    save_reports([r for r in load_reports(path) if r.report_id != report_id], path)


def clear_reports(path=cfg.REPORTS_FILE):
    save_reports([], path)


# ----------------------------------------------------------------------------- graph handling
def block_road(H, u, v):
    """Return (working_copy, removed_edges). Both directions are removed when they exist."""
    H_work = H.copy()
    removed = []
    for a, b in ((u, v), (v, u)):
        if H_work.has_edge(a, b):
            H_work.remove_edge(a, b)
            removed.append((a, b))
    return H_work, removed


def build_working_graph(H, reports):
    """H minus every reported road (copy; H itself is untouched)."""
    H_work = H.copy()
    for r in reports:
        for a, b in ((r.u, r.v), (r.v, r.u)):
            if H_work.has_edge(a, b):
                H_work.remove_edge(a, b)
    return H_work


def process_report(H, source, target, report, algorithm="Dijkstra"):
    """
    Check whether the current route is affected by the report and, if so, find an alternative.
    Returns a dict (original, alternative, affected, removed_edges, message, difference...).
    """
    original = run_algorithm(H, source, target, algorithm)
    out = {"report": report, "original": original, "alternative": None, "affected": False,
           "removed_edges": [], "difference": None, "status": "", "message": ""}
    if not original.found:
        out.update(status="no_route", message=original.message)
        return out
    H_work, removed = block_road(H, report.u, report.v)
    out["removed_edges"] = removed
    if not removed:
        out.update(status="already_unavailable",
                   message="This road is already unavailable in the flood-aware network "
                           "(it is classified as blocked by the simulated flood data), so the route is unchanged.")
        out["alternative"] = original
        return out
    route_edges = set(original.edges())
    out["affected"] = any(e in route_edges for e in removed)
    if not out["affected"]:
        out.update(status="not_affected", alternative=original,
                   message="The reported road is not on the current route, so the route does not need to change.")
        return out
    alt = run_algorithm(H_work, source, target, algorithm)
    out["alternative"] = alt
    if not alt.found:
        out.update(status="no_alternative",
                   message="No alternative route is available after this blockage.")
        return out
    out["status"] = "rerouted"
    out["difference"] = {"distance_m": alt.distance_m - original.distance_m,
                         "cost": alt.cost - original.cost,
                         "intersections": alt.intersections - original.intersections}
    out["message"] = "The reported road is on the route. An alternative route was found."
    return out
