"""
allocation.py - Evacuation resource allocation (notebook cell 15).

  * Shelter allocation : NetworkX Minimum-Cost Flow (nx.min_cost_flow); edge weight is the
                         cheapest flood-aware route cost (rounded), exactly like the notebook.
  * Vehicle assignment : the notebook's GREEDY one-trip assignment (each vehicle serves one
                         area->shelter group; vehicles are used in order until the group is covered).

Additions (not in the notebook): user-selected evacuation counts, input validation, an
"Unsheltered" overflow node so the flow stays solvable when shelters are too small, and shortage reports.
"""
import networkx as nx
import pandas as pd

from core.network import classify_road, nearest_road_name

UNSHELTERED_PENALTY = 10_000_000       # far larger than any real route cost


# ----------------------------------------------------------------------------- scenario tables
def area_severity(G, node):
    """Flood severity of an area = status of the deepest (simulated) road touching its intersection."""
    depths = [d["flood_depth"] for _, _, d in list(G.out_edges(node, data=True)) + list(G.in_edges(node, data=True))]
    return classify_road(max(depths)).capitalize() if depths else "Unknown"


def build_area_table(G, scenario):
    rows = []
    for a in scenario["affected_areas"]:
        rows.append({"Area": a["name"], "Nearest road (OSM)": nearest_road_name(G, a["node"]),
                     "Flood severity": area_severity(G, a["node"]), "Affected population": int(a["people"]),
                     "Evacuate": False, "People to evacuate": 0,
                     "node": a["node"], "lat": a["lat"], "lon": a["lon"]})
    return pd.DataFrame(rows)


def build_shelter_table(G, scenario):
    rows = []
    for s in scenario["shelters"]:
        rows.append({"Shelter": s["name"], "Nearest road (OSM)": nearest_road_name(G, s["node"]),
                     "Latitude": round(s["lat"], 5), "Longitude": round(s["lon"], 5),
                     "Total capacity": int(s["capacity"]), "Currently allocated": 0,
                     "Remaining capacity": int(s["capacity"]),
                     "node": s["node"], "lat": s["lat"], "lon": s["lon"]})
    return pd.DataFrame(rows)


def build_vehicle_table(scenario):
    """
    The notebook defines 5 individual vehicles (capacity 20 each) and no vehicle types or locations.
    Identical vehicles are grouped so a quantity can be chosen; no new vehicle data is invented.
    """
    groups = {}
    for v in scenario["vehicles"]:
        g = groups.setdefault(int(v["capacity"]), [])
        g.append(v["name"])
    rows = []
    for cap, names in sorted(groups.items()):
        rows.append({"Vehicle": f"Evacuation vehicle ({cap} passengers)", "Location": "Not specified in notebook",
                     "Vehicles available": len(names), "Capacity per vehicle": cap,
                     "Total passenger capacity": cap * len(names),
                     "Vehicles to use": len(names), "_names": names})
    return pd.DataFrame(rows)


def expand_vehicles(vehicle_df):
    """Turn the (confirmed) vehicle table into the individual vehicles the greedy algorithm uses."""
    out = []
    for _, r in vehicle_df.iterrows():
        for name in list(r["_names"])[: int(r["Vehicles to use"])]:
            out.append({"name": name, "capacity": int(r["Capacity per vehicle"])})
    return out


# ----------------------------------------------------------------------------- validation
def validate_areas(area_df):
    """Errors for the affected-areas table (selection and number of people)."""
    errors = []
    sel = area_df[area_df["Evacuate"] == True]          # noqa: E712
    if sel.empty:
        errors.append("Select at least one affected area to evacuate.")
    for _, r in sel.iterrows():
        n = r["People to evacuate"]
        if n is None or pd.isna(n) or float(n) != int(float(n)):
            errors.append(f"{r['Area']}: enter a whole number of people.")
            continue
        n = int(n)
        if n <= 0:
            errors.append(f"{r['Area']}: people to evacuate must be at least 1.")
        elif n > int(r["Affected population"]):
            errors.append(f"{r['Area']}: {n} people exceeds the affected population ({int(r['Affected population'])}).")
    return errors


def validate_vehicles(vehicle_df):
    """Errors for the vehicles table (quantities must not exceed what is available)."""
    errors = []
    for _, r in vehicle_df.iterrows():
        n = r["Vehicles to use"]
        if n is None or pd.isna(n) or float(n) != int(float(n)) or int(n) < 0:
            errors.append(f"{r['Vehicle']}: enter a whole number of vehicles (0 or more).")
        elif int(n) > int(r["Vehicles available"]):
            errors.append(f"{r['Vehicle']}: {int(n)} exceeds the {int(r['Vehicles available'])} vehicles available.")
    return errors


def validate_inputs(area_df, vehicle_df):
    """Return (errors, warnings). Errors block the run; warnings are informational."""
    errors = validate_areas(area_df) + validate_vehicles(vehicle_df)
    warns = []
    if not errors and int(pd.to_numeric(vehicle_df["Vehicles to use"]).sum()) == 0:
        warns.append("No vehicles selected - nobody will be assigned a vehicle.")
    return errors, warns


# ----------------------------------------------------------------------------- Minimum-Cost Flow
def _compute_costs(H, areas, shelters):
    costs = {}
    for a in areas:
        if a["node"] not in H:
            continue
        dist = nx.single_source_dijkstra_path_length(H, a["node"], weight="cost")
        for s in shelters:
            if s["node"] in dist:
                costs[(a["name"], s["name"])] = dist[s["node"]]
    return costs


def allocate_shelters(H, areas, shelters):
    """
    areas    : [{"name", "node", "people"}]   (people = number selected for evacuation)
    shelters : [{"name", "node", "capacity"}]
    """
    warnings = []
    areas = [a for a in areas if int(a["people"]) > 0]
    shelters = [s for s in shelters if int(s["capacity"]) > 0]
    total_people = sum(int(a["people"]) for a in areas)
    total_capacity = sum(int(s["capacity"]) for s in shelters)
    if not areas or not shelters:
        return {"ok": False, "message": "At least one area with people and one shelter with capacity is needed.",
                "allocation": pd.DataFrame(), "shelter_utilization": pd.DataFrame(),
                "area_status": pd.DataFrame(), "summary": {}, "warnings": []}

    costs = _compute_costs(H, areas, shelters)
    F = nx.DiGraph()
    F.add_node("Source", demand=-total_people)
    F.add_node("Destination", demand=total_people)
    F.add_node("Unsheltered", demand=0)
    F.add_edge("Unsheltered", "Destination", capacity=total_people, weight=0)
    for a in areas:
        an = "area::" + a["name"]
        F.add_node(an, demand=0)
        F.add_edge("Source", an, capacity=int(a["people"]), weight=0)
        F.add_edge(an, "Unsheltered", capacity=int(a["people"]), weight=UNSHELTERED_PENALTY)
    for s in shelters:
        sn = "shelter::" + s["name"]
        F.add_node(sn, demand=0)
        F.add_edge(sn, "Destination", capacity=int(s["capacity"]), weight=0)
    for (an, sn), cost in costs.items():
        people = next(int(a["people"]) for a in areas if a["name"] == an)
        F.add_edge("area::" + an, "shelter::" + sn, capacity=people, weight=max(1, round(cost)))
    flow = nx.min_cost_flow(F)

    rows, status_rows = [], []
    for a in areas:
        an = "area::" + a["name"]
        for s in shelters:
            n = int(flow[an].get("shelter::" + s["name"], 0))
            if n > 0:
                per = costs[(a["name"], s["name"])]
                rows.append({"Affected area": a["name"], "Shelter": s["name"], "People allocated": n,
                             "Route cost per person": round(per, 1), "Total route cost": round(per * n, 1)})
        left = int(flow[an].get("Unsheltered", 0))
        status_rows.append({"Affected area": a["name"], "People to evacuate": int(a["people"]),
                            "Sheltered": int(a["people"]) - left, "Without shelter": left})
        if not any((a["name"], s["name"]) in costs for s in shelters):
            warnings.append(f"{a['name']} cannot reach any shelter using safe or moderate roads.")

    cols = ["Affected area", "Shelter", "People allocated", "Route cost per person", "Total route cost"]
    allocation = pd.DataFrame(rows, columns=cols)
    used = allocation.groupby("Shelter")["People allocated"].sum() if len(allocation) else pd.Series(dtype=int)
    util = pd.DataFrame([{"Shelter": s["name"], "Capacity": int(s["capacity"]),
                          "Allocated": int(used.get(s["name"], 0)),
                          "Remaining": int(s["capacity"]) - int(used.get(s["name"], 0)),
                          "Utilisation %": round(100.0 * int(used.get(s["name"], 0)) / int(s["capacity"]), 1)}
                         for s in shelters])
    sheltered = int(allocation["People allocated"].sum()) if len(allocation) else 0
    unsheltered = total_people - sheltered
    if total_people > total_capacity:
        warnings.append(f"Shelter capacity is not enough: {total_people} people need shelter but only "
                        f"{total_capacity} places are available ({total_people - total_capacity} short).")
    elif unsheltered > 0:
        warnings.append(f"{unsheltered} people could not be sheltered because the shelters they can reach are "
                        "full or unreachable.")
    assert (util["Allocated"] <= util["Capacity"]).all(), "shelter capacity exceeded"
    return {"ok": True, "message": "", "allocation": allocation, "shelter_utilization": util,
            "area_status": pd.DataFrame(status_rows), "costs": costs, "warnings": warnings,
            "summary": {"total_people": total_people, "sheltered": sheltered, "unsheltered": unsheltered,
                        "total_capacity": total_capacity,
                        "total_cost": float(allocation["Total route cost"].sum()) if len(allocation) else 0.0}}


# ----------------------------------------------------------------------------- greedy vehicles
def assign_vehicles(allocation, vehicles):
    """Notebook greedy assignment (one trip per vehicle). Capacity is never exceeded."""
    vehicles = [v for v in vehicles if int(v["capacity"]) > 0]
    demands = [{"area": r["Affected area"], "shelter": r["Shelter"], "remaining": int(r["People allocated"])}
               for _, r in allocation.iterrows()] if len(allocation) else []
    rows, available = [], list(vehicles)
    for d in demands:
        while d["remaining"] > 0 and available:
            v = available.pop(0)
            n = min(d["remaining"], int(v["capacity"]))
            rows.append({"Vehicle": v["name"], "Affected area": d["area"], "Shelter": d["shelter"],
                         "People assigned": n, "Capacity": int(v["capacity"]),
                         "Utilisation %": round(100.0 * n / int(v["capacity"]), 1)})
            d["remaining"] -= n
    cols = ["Vehicle", "Affected area", "Shelter", "People assigned", "Capacity", "Utilisation %"]
    assignments = pd.DataFrame(rows, columns=cols)
    unserved = pd.DataFrame([{"Affected area": d["area"], "Shelter": d["shelter"],
                              "People without vehicle": d["remaining"]} for d in demands if d["remaining"] > 0],
                            columns=["Affected area", "Shelter", "People without vehicle"])
    used = set(assignments["Vehicle"]) if len(assignments) else set()
    util = pd.DataFrame([{"Vehicle": v["name"], "Capacity": int(v["capacity"]),
                          "People carried": int(assignments.loc[assignments["Vehicle"] == v["name"], "People assigned"].sum()),
                          "Used": v["name"] in used,
                          "Utilisation %": round(100.0 * assignments.loc[assignments["Vehicle"] == v["name"], "People assigned"].sum()
                                                 / int(v["capacity"]), 1)} for v in vehicles])
    if len(assignments):
        assert (assignments["People assigned"] <= assignments["Capacity"]).all(), "vehicle capacity exceeded"
    to_move = sum(d for d in (int(r["People allocated"]) for _, r in allocation.iterrows())) if len(allocation) else 0
    carried = int(assignments["People assigned"].sum()) if len(assignments) else 0
    warnings = []
    if to_move - carried > 0:
        warnings.append(f"Vehicle capacity is not enough: {to_move - carried} of {to_move} sheltered people "
                        "have no vehicle assigned.")
    return {"assignments": assignments, "vehicle_utilization": util, "unserved": unserved, "warnings": warnings,
            "summary": {"people_to_move": to_move, "people_assigned": carried, "without_vehicle": to_move - carried,
                        "vehicles": len(vehicles), "vehicle_capacity": sum(int(v["capacity"]) for v in vehicles)}}


# ----------------------------------------------------------------------------- one-call workflow
def run_evacuation(H, area_df, shelter_df, vehicle_df):
    """Validate -> Minimum-Cost Flow -> greedy vehicles. Returns a result dict (never raises on bad input)."""
    errors, warns = validate_inputs(area_df, vehicle_df)
    if errors:
        return {"ok": False, "errors": errors}
    sel = area_df[area_df["Evacuate"] == True]          # noqa: E712
    areas = [{"name": r["Area"], "node": int(r["node"]), "people": int(r["People to evacuate"])} for _, r in sel.iterrows()]
    shelters = [{"name": r["Shelter"], "node": int(r["node"]), "capacity": int(r["Total capacity"])}
                for _, r in shelter_df.iterrows()]
    shelter_out = allocate_shelters(H, areas, shelters)
    if not shelter_out["ok"]:
        return {"ok": False, "errors": [shelter_out["message"]]}
    vehicle_out = assign_vehicles(shelter_out["allocation"], expand_vehicles(vehicle_df))
    total = shelter_out["summary"]["total_people"]
    return {"ok": True, "errors": [], "selected": sel, "shelter": shelter_out, "vehicle": vehicle_out,
            "warnings": warns + shelter_out["warnings"] + vehicle_out["warnings"],
            "summary": {"total_people": total,
                        "sheltered": shelter_out["summary"]["sheltered"],
                        "without_shelter": shelter_out["summary"]["unsheltered"],
                        "with_vehicle": vehicle_out["summary"]["people_assigned"],
                        "without_vehicle_total": total - vehicle_out["summary"]["people_assigned"],
                        "fully_allocated": shelter_out["summary"]["sheltered"] == total
                        and vehicle_out["summary"]["people_assigned"] == total}}
