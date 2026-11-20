"""
maps.py - Folium map builders for FLOODGUARD 2.0.

All roads come from the real OpenStreetMap network. Flood colours are based on SIMULATED depths.
"""
import folium

from core import config as cfg

ESRI_STREET = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
               "World_Street_Map/MapServer/tile/{z}/{y}/{x}")
STATUS_COLORS = {"safe": "#16a34a", "moderate": "#f59e0b", "blocked": "#dc2626"}
ROUTE_COLORS = {"original": "#1d4ed8", "alternative": "#7c3aed", "dijkstra": "#1d4ed8",
                "astar": "#0891b2", "blocked": "#000000"}


def create_base_map(center=cfg.MAP_CENTER, zoom=14, tiles=True):
    m = folium.Map(location=center, zoom_start=zoom, tiles=None, min_zoom=12, max_zoom=18,
                   control_scale=True)
    if tiles:
        folium.TileLayer(tiles=ESRI_STREET, attr="Tiles © Esri", name="Esri Street Map", max_zoom=18).add_to(m)
        folium.TileLayer("OpenStreetMap", name="OpenStreetMap", max_zoom=18, show=False).add_to(m)
    return m


# ----------------------------------------------------------------------------- flood layers
def build_flood_geojson(G):
    """Split the real road network into three GeoJSON collections by (simulated) flood status."""
    out = {"safe": [], "moderate": [], "blocked": []}
    for _, _, _, d in G.edges(keys=True, data=True):
        n = d.get("name")
        n = " / ".join(n) if isinstance(n, list) else n
        out[d["status"]].append({
            "type": "Feature",
            "geometry": {"type": "LineString",
                         "coordinates": [[round(lon, 5), round(lat, 5)] for lat, lon in d["geometry"]]},
            "properties": {"name": n or "Unnamed road", "flood_depth": d["flood_depth"],
                           "status": d["status"].capitalize(), "length_m": round(d["length"])}})
    return {s: {"type": "FeatureCollection", "features": f} for s, f in out.items()}


def add_flood_layers(m, geojson, weight=2.5, opacity=0.85, tooltips=True):
    labels = {"safe": f"Safe roads (below {cfg.MODERATE_CM} cm)",
              "moderate": f"Moderately affected ({cfg.MODERATE_CM}-{cfg.BLOCKED_CM - 1} cm)",
              "blocked": f"Blocked roads ({cfg.BLOCKED_CM} cm and above)"}
    for status in ("safe", "moderate", "blocked"):
        if not geojson[status]["features"]:
            continue
        group = folium.FeatureGroup(name=labels[status], show=True)
        kwargs = {}
        if tooltips:
            kwargs["tooltip"] = folium.GeoJsonTooltip(
                fields=["name", "flood_depth", "status", "length_m"],
                aliases=["Road:", "Flood depth, simulated (cm):", "Status:", "Length (m):"], sticky=True)
        folium.GeoJson(geojson[status],
                       style_function=lambda f, c=STATUS_COLORS[status]: {"color": c, "weight": weight, "opacity": opacity},
                       **kwargs).add_to(group)
        group.add_to(m)


def add_grey_network(m, G, weight=1, opacity=0.45):
    """Thin neutral road layer (used as a background on route pages)."""
    feats = [{"type": "Feature",
              "geometry": {"type": "LineString",
                           "coordinates": [[round(lon, 5), round(lat, 5)] for lat, lon in d["geometry"]]},
              "properties": {}} for _, _, _, d in G.edges(keys=True, data=True)]
    folium.GeoJson({"type": "FeatureCollection", "features": feats}, name="Road network (OSM)",
                   style_function=lambda f: {"color": "#64748b", "weight": weight, "opacity": opacity}).add_to(m)


# ----------------------------------------------------------------------------- markers
def add_areas(m, area_df, selected=None):
    group = folium.FeatureGroup(name="Affected areas (simulated)", show=True)
    for _, a in area_df.iterrows():
        mark = ""
        if selected and a["Area"] in selected:
            try:
                mark = f" - selected for evacuation: {int(a['People to evacuate'])}"
            except (TypeError, ValueError):       # empty cell in the editor
                mark = " - selected for evacuation"
        folium.Marker((a["lat"], a["lon"]),
                      tooltip=f"{a['Area']}: {int(a['Affected population'])} people affected (simulated){mark}",
                      popup=folium.Popup(f"<b>{a['Area']}</b><br>Severity: {a['Flood severity']}<br>"
                                         f"Population (simulated): {int(a['Affected population'])}<br>"
                                         f"Nearest road: {a['Nearest road (OSM)']}", max_width=260),
                      icon=folium.Icon(color="orange", icon="home", prefix="fa")).add_to(group)
    group.add_to(m)


def add_shelters(m, shelter_df, allocation=None):
    group = folium.FeatureGroup(name="Shelters (simulated)", show=True)
    used = {}
    if allocation is not None and len(allocation):
        used = allocation.groupby("Shelter")["People allocated"].sum().to_dict()
    for _, s in shelter_df.iterrows():
        extra = f"<br>Allocated this run: {used.get(s['Shelter'], 0)}" if allocation is not None else ""
        folium.Marker((s["lat"], s["lon"]),
                      tooltip=f"{s['Shelter']}: capacity {int(s['Total capacity'])} (simulated)",
                      popup=folium.Popup(f"<b>{s['Shelter']}</b><br>Capacity (simulated): {int(s['Total capacity'])}"
                                         f"{extra}<br>Nearest road: {s['Nearest road (OSM)']}", max_width=260),
                      icon=folium.Icon(color="blue", icon="plus-square", prefix="fa")).add_to(group)
    group.add_to(m)


def add_endpoint_markers(m, G, source, target, source_label="Start", target_label="Destination"):
    folium.Marker((G.nodes[source]["y"], G.nodes[source]["x"]), tooltip=source_label,
                  icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
    folium.Marker((G.nodes[target]["y"], G.nodes[target]["x"]), tooltip=target_label,
                  icon=folium.Icon(color="red", icon="flag", prefix="fa")).add_to(m)


# ----------------------------------------------------------------------------- routes
def add_route(m, coords, color, label, weight=6, opacity=0.9, dash=None):
    folium.PolyLine(coords, color=color, weight=weight, opacity=opacity, tooltip=label,
                    dash_array=dash).add_to(m)


def add_blocked_road(m, G, u, v, label="Reported blocked road"):
    edge = G[u][v] if G.has_edge(u, v) else G[v][u]
    d = edge[next(iter(edge))]
    folium.PolyLine(d["geometry"], color="#dc2626", weight=10, opacity=0.95, tooltip=label).add_to(m)
    mid = d["geometry"][len(d["geometry"]) // 2]
    folium.Marker(mid, tooltip=label, icon=folium.Icon(color="black", icon="ban", prefix="fa")).add_to(m)


def add_reports(m, reports):
    if not reports:
        return
    group = folium.FeatureGroup(name="Reported blockages (unverified)", show=True)
    for r in reports:
        folium.CircleMarker((r.lat, r.lon), radius=8, color="#000", fill=True, fill_color="#dc2626", fill_opacity=0.9,
                            tooltip=f"{r.road} - {r.reason} (unverified user report)").add_to(group)
    group.add_to(m)


def fit(m, coords):
    if coords:
        lats, lons = [c[0] for c in coords], [c[1] for c in coords]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30))


# ----------------------------------------------------------------------------- legend
def add_legend(m, items, title="Legend"):
    """items: list of (colour, label). Adds a small fixed legend box."""
    rows = "".join(f"<div style='margin:2px 0'><span style='display:inline-block;width:26px;height:5px;"
                   f"background:{c};margin-right:8px;vertical-align:middle'></span>{t}</div>" for c, t in items)
    html = ("<div style='position:fixed;bottom:28px;left:28px;z-index:9999;background:white;padding:10px 14px;"
            "border:1px solid #cbd5e1;border-radius:8px;font:13px sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.2)'>"
            f"<b>{title}</b>{rows}</div>")
    m.get_root().html.add_child(folium.Element(html))


FLOOD_LEGEND = [(STATUS_COLORS["safe"], "Safe road"), (STATUS_COLORS["moderate"], "Moderately affected road"),
                (STATUS_COLORS["blocked"], "Blocked road")]
