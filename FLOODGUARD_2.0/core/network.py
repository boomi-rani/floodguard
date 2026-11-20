"""
network.py - Road network, flood classification and flood-aware graph.

Reuses the notebook logic:
  * REAL data      : OpenStreetMap road network of Velachery (stored in data/).
  * SIMULATED data : random flood depth per directed edge (np.random.seed(42), 0-80 cm).
  * classify_road  : depth >= 70 blocked, >= 30 moderate, else safe  (notebook cell 12/13).
  * flood-aware graph H : blocked roads removed, moderate roads cost x3 (notebook cell 12/13).
OSMnx and Google Colab are NOT needed at run time.
"""
import json
import math
import os

import networkx as nx
import numpy as np
import pandas as pd

from core import config as cfg


# ----------------------------------------------------------------------------- distances
def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (same formula as ox.distance.great_circle)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * cfg.EARTH_RADIUS_M * math.asin(math.sqrt(a))


def nearest_node(G, lat, lon):
    """Snap a (lat, lon) point to the nearest road intersection."""
    ids = np.fromiter(G.nodes, dtype=np.int64, count=G.number_of_nodes())
    ys = np.array([G.nodes[n]["y"] for n in ids])
    xs = np.array([G.nodes[n]["x"] for n in ids])
    dy = np.radians(ys - lat)
    dx = np.radians(xs - lon) * math.cos(math.radians(lat))
    return int(ids[np.argmin(dx * dx + dy * dy)])


# ----------------------------------------------------------------------------- loading
def load_road_network(data_dir=cfg.DATA_DIR):
    """Load the saved OSM road network as a NetworkX MultiDiGraph (no flood status yet)."""
    nodes_df = pd.read_csv(os.path.join(data_dir, "velachery_nodes.csv"))
    with open(os.path.join(data_dir, "velachery_edges.geojson"), encoding="utf-8") as fh:
        features = json.load(fh)["features"]
    G = nx.MultiDiGraph(name="Velachery drive network", crs="EPSG:4326")
    for row in nodes_df.itertuples(index=False):
        G.add_node(int(row.node_id), y=float(row.lat), x=float(row.lon))
    for f in features:
        p = f["properties"]
        coords = [(lat, lon) for lon, lat in f["geometry"]["coordinates"]]
        G.add_edge(int(p["u"]), int(p["v"]), key=int(p["key"]),
                   length=float(p["length"]), flood_depth=int(p["flood_depth"]),
                   name=p.get("name"), highway=p.get("highway"),
                   oneway=bool(p.get("oneway")), geometry=coords)
    return G


def load_metadata(data_dir=cfg.DATA_DIR):
    with open(os.path.join(data_dir, "metadata.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_scenario(data_dir=cfg.DATA_DIR):
    with open(os.path.join(data_dir, "scenario.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------------------- flood status
def classify_road(depth, moderate_cm=cfg.MODERATE_CM, blocked_cm=cfg.BLOCKED_CM):
    if depth >= blocked_cm:
        return "blocked"
    if depth >= moderate_cm:
        return "moderate"
    return "safe"


def apply_flood_classification(G, moderate_cm=cfg.MODERATE_CM, blocked_cm=cfg.BLOCKED_CM):
    """Return a COPY of G in which every edge has a `status` (original G is untouched)."""
    if moderate_cm >= blocked_cm:
        raise ValueError("Moderate threshold must be lower than the blocked threshold.")
    G2 = G.copy()
    for _, _, _, d in G2.edges(keys=True, data=True):
        d["status"] = classify_road(d["flood_depth"], moderate_cm, blocked_cm)
    return G2


def build_flood_aware_graph(G, multiplier=cfg.MODERATE_COST_MULTIPLIER):
    """Notebook graph H: blocked roads skipped, moderate x3, cheapest parallel edge kept."""
    H = nx.DiGraph()
    H.add_nodes_from(G.nodes(data=True))
    for u, v, _, d in G.edges(keys=True, data=True):
        if d["status"] == "blocked":
            continue
        length = d["length"]
        cost = length * multiplier if d["status"] == "moderate" else length
        if not H.has_edge(u, v) or cost < H[u][v]["cost"]:
            H.add_edge(u, v, cost=cost, length=length, status=d["status"],
                       flood_depth=d["flood_depth"], name=d.get("name"),
                       highway=d.get("highway"), geometry=d["geometry"])
    return H


def build_networks(moderate_cm=cfg.MODERATE_CM, blocked_cm=cfg.BLOCKED_CM, data_dir=cfg.DATA_DIR):
    """Load files -> classify -> flood-aware graph. Returns (G, H)."""
    G = apply_flood_classification(load_road_network(data_dir), moderate_cm, blocked_cm)
    return G, build_flood_aware_graph(G)


# ----------------------------------------------------------------------------- statistics
def graph_statistics(G, H):
    status = pd.Series([d["status"] for _, _, d in G.edges(data=True)]).value_counts()
    return {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
            "safe": int(status.get("safe", 0)), "moderate": int(status.get("moderate", 0)),
            "blocked": int(status.get("blocked", 0)), "routable_edges": H.number_of_edges(),
            "total_km": sum(d["length"] for _, _, d in G.edges(data=True)) / 1000.0}


# ----------------------------------------------------------------------------- road lookup
class RoadIndex:
    """Find the nearest real road segment to a clicked point (used by the blockage report page)."""

    def __init__(self, G):
        pts, owners = [], []
        for u, v, k, d in G.edges(keys=True, data=True):
            for lat, lon in d["geometry"]:
                pts.append((lat, lon))
                owners.append((u, v, k))
        self._pts = np.array(pts)
        self._owners = owners
        self._G = G

    def nearest_edge(self, lat, lon):
        """Return (u, v, k, distance_m) of the road vertex closest to (lat, lon)."""
        dy = np.radians(self._pts[:, 0] - lat)
        dx = np.radians(self._pts[:, 1] - lon) * math.cos(math.radians(lat))
        i = int(np.argmin(dx * dx + dy * dy))
        dist = float(math.sqrt(dx[i] ** 2 + dy[i] ** 2) * cfg.EARTH_RADIUS_M)
        u, v, k = self._owners[i]
        return u, v, k, dist


def road_name(d):
    n = d.get("name")
    if isinstance(n, list):
        n = " / ".join(map(str, n))
    return n if n else "Unnamed road"


def nearest_road_name(G, node):
    """Name of a real OSM road touching an intersection (used to describe scenario locations)."""
    for _, _, d in list(G.out_edges(node, data=True)) + list(G.in_edges(node, data=True)):
        if d.get("name"):
            return road_name(d)
    return "Unnamed road"
