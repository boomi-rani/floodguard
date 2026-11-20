"""
FLOODGUARD 2.0 test suite.  Run from the project folder:

    python -m tests.test_floodguard         (plain Python, prints every check)
    python -m pytest tests -v               (if pytest is installed)

Tests the logic (network, routing, blockage reports, allocation).  The Streamlit pages and Folium maps
are NOT exercised here - see README ("Testing") for what is and is not covered.
"""
import hashlib
import json
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import allocation as al        # noqa: E402
from core import analytics as an         # noqa: E402
from core import blockage as bk          # noqa: E402
from core import config as cfg           # noqa: E402
from core import network as nw           # noqa: E402
from core import routing as rt           # noqa: E402

_G, _H = nw.build_networks()
_SC = nw.load_scenario()
SRC, DST = _SC["default_start"]["node"], _SC["default_destination"]["node"]


def fresh():
    return _G, _H.copy()


def area_df(evac=None):
    df = al.build_area_table(_G, _SC)
    for name, n in (evac or {"Area A": 40, "Area B": 35, "Area C": 25}).items():
        df.loc[df["Area"] == name, ["Evacuate", "People to evacuate"]] = [True, n]
    df["Evacuate"] = df["Evacuate"].astype(bool)
    return df


# ============================================================ A. legacy checks from the previous project (25)
def test_01_nodes(): assert nw.graph_statistics(_G, _H)["nodes"] == 4471
def test_02_edges(): assert nw.graph_statistics(_G, _H)["edges"] == 11452
def test_03_flood_aware_edges(): assert nw.graph_statistics(_G, _H)["routable_edges"] == 9886
def test_04_status_sum():
    s = nw.graph_statistics(_G, _H); assert s["safe"] + s["moderate"] + s["blocked"] == 11452
def test_05_first_thresholds():
    G1 = nw.apply_flood_classification(nw.load_road_network(), 20, 50)
    s = nw.graph_statistics(G1, nw.build_flood_aware_graph(G1))
    assert (s["blocked"], s["moderate"], s["safe"]) == (4415, 4191, 2846)
def test_06_start_node(): assert nw.nearest_node(_G, 12.9750, 80.2210) == SRC == 12497489526
def test_07_dest_node(): assert nw.nearest_node(_G, 12.9900, 80.2140) == DST == 11050648635
def test_08_dijkstra_54():
    d = rt.run_dijkstra(_H, SRC, DST); assert d.found and len(d.path) == 54
def test_09_dijkstra_cost(): assert round(rt.run_dijkstra(_H, SRC, DST).cost, 2) == 8886.24
def test_10_astar_equals_dijkstra():
    assert abs(rt.run_astar(_H, SRC, DST).cost - rt.run_dijkstra(_H, SRC, DST).cost) < 1e-6
def test_11_astar_explores_fewer():
    assert rt.nodes_expanded(_H, SRC, DST, True) < rt.nodes_expanded(_H, SRC, DST, False)
def test_12_notebook_blocked_road_77():
    d = rt.run_dijkstra(_H, SRC, DST); u, v = d.path[len(d.path) // 2], d.path[len(d.path) // 2 + 1]
    assert (u, v) == (2167149032, 2167027825)
    H2 = _H.copy(); H2.remove_edge(u, v)
    assert len(rt.run_dijkstra(H2, SRC, DST).path) == 77
def test_13_original_not_modified():
    H = _H.copy(); n = H.number_of_edges(); d = rt.run_dijkstra(H, SRC, DST)
    bk.block_road(H, d.path[10], d.path[11]); assert H.number_of_edges() == n and H.has_edge(d.path[10], d.path[11])
def test_14_alt_avoids_blocked():
    d = rt.run_dijkstra(_H, SRC, DST); u, v = d.path[27], d.path[28]
    H2, _ = bk.block_road(_H, u, v); alt = rt.run_dijkstra(H2, SRC, DST)
    assert (u, v) not in alt.edges() and (v, u) not in alt.edges()
def test_15_same_start_dest_rejected(): assert not rt.run_dijkstra(_H, SRC, SRC).found
def test_16_allocation_table():
    out = al.allocate_shelters(_H, [{"name": "Area A", "node": 12497489526, "people": 40},
                                    {"name": "Area B", "node": 338282602, "people": 35},
                                    {"name": "Area C", "node": 12483820630, "people": 25}],
                               [{"name": s["name"], "node": s["node"], "capacity": s["capacity"]} for s in _SC["shelters"]])
    rows = {(r[0], r[1]): r[2] for r in out["allocation"][["Affected area", "Shelter", "People allocated"]].itertuples(index=False)}
    assert rows == {("Area A", "Shelter 1"): 20, ("Area A", "Shelter 3"): 20, ("Area B", "Shelter 2"): 35, ("Area C", "Shelter 1"): 25}
    assert out["summary"]["sheltered"] == 100
def test_17_no_shelter_over_capacity():
    r = al.run_evacuation(_H, area_df(), al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))
    u = r["shelter"]["shelter_utilization"]; assert (u["Allocated"] <= u["Capacity"]).all()
def test_18_greedy_95_of_100():
    r = al.run_evacuation(_H, area_df(), al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))
    assert r["summary"]["with_vehicle"] == 95
def test_19_insufficient_vehicles_reported():
    r = al.run_evacuation(_H, area_df(), al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))
    assert len(r["vehicle"]["warnings"]) == 1 and r["vehicle"]["unserved"]["People without vehicle"].sum() == 5
def test_20_vehicle_capacity_never_exceeded():
    r = al.run_evacuation(_H, area_df(), al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))
    a = r["vehicle"]["assignments"]; assert (a["People assigned"] <= a["Capacity"]).all()
def test_21_small_shelter_reported_not_crash():
    out = al.allocate_shelters(_H, [{"name": "A", "node": 12497489526, "people": 40}, {"name": "B", "node": 338282602, "people": 35},
                                    {"name": "C", "node": 12483820630, "people": 25}],
                               [{"name": "S1", "node": 299879177, "capacity": 30}])
    assert out["summary"]["sheltered"] == 30 and out["summary"]["unsheltered"] == 70 and len(out["warnings"]) == 1
def test_22_greedy_matches_notebook_table():
    r = al.run_evacuation(_H, area_df(), al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))
    got = [(x[0], x[1], x[2], x[3]) for x in r["vehicle"]["assignments"][["Vehicle", "Affected area", "Shelter", "People assigned"]].itertuples(index=False)]
    assert got == [("Vehicle 1", "Area A", "Shelter 1", 20), ("Vehicle 2", "Area A", "Shelter 3", 20),
                   ("Vehicle 3", "Area B", "Shelter 2", 20), ("Vehicle 4", "Area B", "Shelter 2", 15),
                   ("Vehicle 5", "Area C", "Shelter 1", 20)]
def test_23_graph_load_roundtrip_counts():
    G2 = nw.load_road_network(); assert G2.number_of_nodes() == 4471 and G2.number_of_edges() == 11452
def test_24_moderate_cost_x3():
    for u, v, d in _H.edges(data=True):
        if d["status"] == "moderate": assert abs(d["cost"] - 3 * d["length"]) < 1e-9; break
def test_25_blocked_roads_absent():
    for u, v, k, d in _G.edges(keys=True, data=True):
        if d["status"] == "blocked" and not _H.has_edge(v, u) and not _H.has_edge(u, v): return
    raise AssertionError("expected at least one blocked road to be absent from H")


# ============================================================ B. new: user-reported blockages
def _route_edge(i=27):
    d = rt.run_dijkstra(_H, SRC, DST); return d, d.path[i], d.path[i + 1]

def test_30_report_on_route_gives_alternative():
    d, u, v = _route_edge(); rep = bk.create_report(_G, u, v, "Flooding", "water over road", store=False)
    o = bk.process_report(_H, SRC, DST, rep)
    assert o["status"] == "rerouted" and o["affected"] and o["alternative"].found
    assert o["difference"]["distance_m"] > 0 and o["difference"]["cost"] > 0
def test_31_both_directions_removed():
    d, u, v = _route_edge(); H2, removed = bk.block_road(_H, u, v)
    assert (u, v) in removed and ((v, u) in removed) == _H.has_edge(v, u)
    assert not H2.has_edge(u, v) and not H2.has_edge(v, u)
def test_32_original_graph_preserved_after_report():
    H = _H.copy(); before = (H.number_of_edges(), sorted(H.edges())[:50])
    d, u, v = _route_edge(); bk.process_report(H, SRC, DST, bk.create_report(_G, u, v, "Road damage", store=False))
    assert (H.number_of_edges(), sorted(H.edges())[:50]) == before and H.has_edge(u, v)
def test_33_report_off_route_not_affected():
    d = rt.run_dijkstra(_H, SRC, DST); on = set(d.edges()) | {(b, a) for a, b in d.edges()}
    for u, v in _H.edges():
        if (u, v) not in on:
            rep = bk.create_report(_G, u, v, "Other obstruction", store=False); break
    o = bk.process_report(_H, SRC, DST, rep)
    assert o["status"] == "not_affected" and not o["affected"] and o["alternative"].path == d.path
def test_34_flood_blocked_road_reported():
    for u, v, k, dd in _G.edges(keys=True, data=True):
        if dd["status"] == "blocked" and not _H.has_edge(u, v) and not _H.has_edge(v, u):
            o = bk.process_report(_H, SRC, DST, bk.create_report(_G, u, v, "Flooding", store=False)); break
    assert o["status"] == "already_unavailable"
def test_35_no_alternative_handled():
    # make the destination reachable only through one road, then report that road
    H = _H.copy(); into = list(H.in_edges(DST))
    for a, b in into[1:]: H.remove_edge(a, b)
    d = rt.run_dijkstra(H, SRC, DST)
    assert d.found, "test set-up failed: destination should still be reachable via one road"
    a, b = d.path[-2], d.path[-1]
    o = bk.process_report(H, SRC, DST, bk.create_report(_G, a, b, "Flooding", store=False))
    assert o["status"] == "no_alternative" and not o["alternative"].found and "No alternative" in o["message"]
def test_36_astar_also_works_for_reroute():
    d, u, v = _route_edge()
    o = bk.process_report(_H, SRC, DST, bk.create_report(_G, u, v, "Flooding", store=False), "A*")
    assert o["status"] == "rerouted" and abs(o["original"].cost - 8886.24) < 0.01
def test_37_report_storage_roundtrip_and_status():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "r.json"); d, u, v = _route_edge()
        rep = bk.create_report(_G, u, v, "Fallen tree or debris", "tree down", path=p)
        loaded = bk.load_reports(p)
        assert len(loaded) == 1 and loaded[0].status.startswith("Unverified") and loaded[0].reason == "Fallen tree or debris"
        try: bk.create_report(_G, u, v, "Flooding", path=p); raise AssertionError("duplicate accepted")
        except ValueError: pass
        bk.delete_report(rep.report_id, p); assert bk.load_reports(p) == []
def test_38_invalid_report_rejected():
    for args in [(1, 2, "Flooding"), (_H and next(iter(_H.edges()))[0], next(iter(_H.edges()))[1], "Made-up reason")]:
        try: bk.create_report(_G, *args, store=False); raise AssertionError("accepted")
        except ValueError: pass
def test_39_corrupt_report_file_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "r.json"); open(p, "w").write("{not json")
        assert bk.load_reports(p) == []
def test_40_working_graph_removes_reports():
    d, u, v = _route_edge(); rep = bk.create_report(_G, u, v, "Flooding", store=False)
    W = bk.build_working_graph(_H, [rep]); assert not W.has_edge(u, v) and _H.has_edge(u, v)


# ============================================================ C. new: allocation, selection and validation
def _run(evac=None, shelters=None, vehicles=None):
    sh = shelters if shelters is not None else al.build_shelter_table(_G, _SC)
    ve = vehicles if vehicles is not None else al.build_vehicle_table(_SC)
    return al.run_evacuation(_H, area_df(evac), sh, ve)

def test_50_partial_selection_only_selected_areas():
    r = _run({"Area B": 20}); a = r["shelter"]["allocation"]
    assert set(a["Affected area"]) == {"Area B"} and r["summary"]["total_people"] == 20 and r["summary"]["fully_allocated"]
def test_51_users_count_used_not_population():
    r = _run({"Area A": 10, "Area C": 5}); assert r["summary"]["total_people"] == 15
def test_52_over_population_rejected():
    r = _run({"Area A": 41}); assert not r["ok"] and "exceeds the affected population" in r["errors"][0]
def test_53_zero_negative_and_non_integer_rejected():
    assert not _run({"Area A": 0})["ok"] and not _run({"Area A": -3})["ok"]
    df = area_df(); df["People to evacuate"] = df["People to evacuate"].astype(float); df.loc[0, "People to evacuate"] = 2.5; assert not al.run_evacuation(_H, df, al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))["ok"]
    df.loc[0, "People to evacuate"] = None; assert not al.run_evacuation(_H, df, al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))["ok"]
def test_54_nothing_selected_rejected():
    r = al.run_evacuation(_H, al.build_area_table(_G, _SC), al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC))
    assert not r["ok"] and "Select at least one" in r["errors"][0]
def test_55_insufficient_shelter_capacity():
    sh = al.build_shelter_table(_G, _SC); sh["Total capacity"] = [20, 10, 10]
    r = _run(shelters=sh); s = r["summary"]
    assert s["sheltered"] == 40 and s["without_shelter"] == 60 and any("Shelter capacity is not enough" in w for w in r["warnings"])
    assert (r["shelter"]["shelter_utilization"]["Allocated"] <= [20, 10, 10]).all()
def test_56_insufficient_vehicle_capacity():
    ve = al.build_vehicle_table(_SC); ve["Vehicles to use"] = 2
    r = _run(vehicles=ve); assert r["summary"]["with_vehicle"] == 40 and r["summary"]["without_vehicle_total"] == 60
    assert any("Vehicle capacity is not enough" in w for w in r["warnings"]) and not r["summary"]["fully_allocated"]
def test_57_vehicle_quantity_over_available_rejected():
    ve = al.build_vehicle_table(_SC); ve["Vehicles to use"] = 6; r = _run(vehicles=ve)
    assert not r["ok"] and "exceeds the 5 vehicles available" in r["errors"][0]
def test_58_zero_vehicles_warns_not_crash():
    ve = al.build_vehicle_table(_SC); ve["Vehicles to use"] = 0; r = _run(vehicles=ve)
    assert r["ok"] and r["summary"]["with_vehicle"] == 0 and r["summary"]["sheltered"] == 100
def test_59_no_duplicate_allocation_rows():
    a = _run()["shelter"]["allocation"]; assert not a.duplicated(["Affected area", "Shelter"]).any()
def test_60_people_conserved():
    r = _run(); s = r["summary"]; assert s["sheltered"] + s["without_shelter"] == s["total_people"]
    assert r["vehicle"]["assignments"]["People assigned"].sum() + r["vehicle"]["unserved"]["People without vehicle"].sum() == s["sheltered"]
def test_61_repeat_run_same_result():
    a, b = _run()["shelter"]["allocation"], _run()["shelter"]["allocation"]; assert a.equals(b)
def test_62_tables_use_real_notebook_values():
    a, s, v = al.build_area_table(_G, _SC), al.build_shelter_table(_G, _SC), al.build_vehicle_table(_SC)
    assert list(a["Affected population"]) == [40, 35, 25] and list(s["Total capacity"]) == [45, 35, 40]
    assert list(v["Vehicles available"]) == [5] and list(v["Capacity per vehicle"]) == [20]
def test_63_area_severity_values_valid():
    assert set(al.build_area_table(_G, _SC)["Flood severity"]) <= {"Safe", "Moderate", "Blocked"}
def test_64_unreachable_area_reported():
    H = _H.copy(); H.remove_edges_from(list(H.out_edges(338282602)))
    out = al.allocate_shelters(H, [{"name": "B", "node": 338282602, "people": 35}],
                               [{"name": "S1", "node": 299879177, "capacity": 45}])
    assert out["summary"]["unsheltered"] == 35 and any("cannot reach any shelter" in w for w in out["warnings"])


# ============================================================ D. routing extras, analytics, data integrity
def test_70_no_route_message():
    H = _H.copy(); H.remove_edges_from(list(H.in_edges(DST)))
    r = rt.run_dijkstra(H, SRC, DST); assert not r.found and "No safe route" in r.message
    assert not rt.run_astar(H, SRC, DST).found
def test_71_unknown_node_handled():
    assert not rt.run_dijkstra(_H, 1, DST).found and not rt.run_astar(_H, SRC, 2).found
def test_72_route_distance_is_sum_of_lengths():
    d = rt.run_dijkstra(_H, SRC, DST); assert abs(d.distance_m - sum(_H[a][b]["length"] for a, b in d.edges())) < 1e-6
def test_73_route_comparison_table():
    c = an.route_comparison(_H, SRC, DST, repeats=3)
    assert c["ok"] and c["same_cost"] and list(c["table"]["Algorithm"]) == ["Dijkstra", "A*"]
    assert c["table"].loc[1, "Nodes explored"] < c["table"].loc[0, "Nodes explored"]
def test_74_rerouting_comparison_runs():
    t = an.rerouting_comparison(_G, _H, SRC, DST); assert len(t) >= 50 and set(t["Result"]) <= {"rerouted", "no_alternative", "already_unavailable", "not_affected"}
def test_75_random_pair_benchmark_same_costs():
    df = rt.benchmark_random_pairs(_H, n_pairs=3, repeats=1); assert len(df) == 3 and df["Same cost"].all()
def test_76_travel_time_not_fabricated(): assert rt.estimated_travel_time_min(1000) is None
def test_77_threshold_validation():
    try: nw.apply_flood_classification(_G, 70, 30); raise AssertionError("accepted")
    except ValueError: pass
def test_78_road_index_snaps_to_real_road():
    idx = nw.RoadIndex(_G); u, v, k, dist = idx.nearest_edge(12.9750, 80.2210)
    assert _G.has_edge(u, v) and dist < 100
def test_79_road_data_files_unchanged():
    """The four data files must be byte-identical to the ones taken from the previous project."""
    expected = {"metadata.json": "0bddbd38db8ad93f66dcf60cd3918471153f2ddf27c60a7c7d6ff10fdadd1a3e",
                "scenario.json": "69b50bb460c004d180df1f1064d437c0a44ba892368fd2efe7ed2623118ea003",
                "velachery_edges.geojson": "ee539e8a746cea65cbf2a37528d88d891705736c6a6b3b655889d8f2b9cabda5",
                "velachery_nodes.csv": "c3f27961ad87c20058c52570fad5c80b0436c55293783b24fbd12d1e35f7160b"}
    for name, h in expected.items():
        with open(os.path.join(cfg.DATA_DIR, name), "rb") as fh: assert hashlib.sha256(fh.read()).hexdigest() == h, name
def test_80_building_networks_does_not_change_source_graph():
    raw = nw.load_road_network(); nw.apply_flood_classification(raw)
    assert all("status" not in d for _, _, _, d in raw.edges(keys=True, data=True))


# ============================================================ plain-Python runner
if __name__ == "__main__":
    tests = sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"  PASS  {name}")
        except Exception as exc:                      # noqa: BLE001
            failed += 1; print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
