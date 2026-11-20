"""Page 3 - Route optimisation: Dijkstra and A* between two places."""
import streamlit as st

import maps
import ui
from core import routing as rt
from state import default_pair, locations


def render(data):
    G, H = data["G"], data["H"]
    ui.hero("Route Optimization", "Find the best flood-aware route between two locations")
    ui.badges("real", "sim")
    locs = locations(data)
    names = list(locs)
    d_start, d_dest = default_pair(locs)

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    start_name = c1.selectbox("Starting point", names, index=d_start)
    dest_name = c2.selectbox("Destination", names, index=d_dest)
    algo = c3.radio("Algorithm", ["Dijkstra", "A*", "Compare both"], horizontal=False)
    go = st.button("Find route", type="primary")

    source, target = locs[start_name], locs[dest_name]
    sig = (source, target, algo)
    if go:
        if source == target:
            st.session_state["route_res"] = {"sig": sig, "error": "Starting point and destination are the same. Please choose different places."}
        else:
            res = {"sig": sig, "error": "", "start": start_name, "dest": dest_name}
            res["dijkstra"] = rt.run_dijkstra(H, source, target) if algo in ("Dijkstra", "Compare both") else None
            res["astar"] = rt.run_astar(H, source, target) if algo in ("A*", "Compare both") else None
            if algo == "Compare both":
                res["bench"] = rt.benchmark_pair(H, source, target, repeats=10)
            st.session_state["route_res"] = res

    res = st.session_state.get("route_res")
    if not res:
        st.info("Choose a starting point and destination, then press **Find route**.")
        _map(data, None)
        return
    if res["sig"] != sig:
        st.info("Your selection has changed. Press **Find route** to update the result.")
    if res["error"]:
        st.error(res["error"])
        return

    routes = [r for r in (res["dijkstra"], res["astar"]) if r is not None]
    if not any(r.found for r in routes):
        st.error(routes[0].message or "No safe route is available between these locations.")
        st.caption("All roads connecting these places are classified as blocked in the simulated flood data.")
        _map(data, None)
        return

    main = next(r for r in routes if r.found)
    ui.section("Route result")
    ui.cards([("From", res["start"].split(" (")[0], "starting point", "blue"),
              ("To", res["dest"].split(" (")[0], "destination", "blue"),
              ("Route distance", ui.fmt_dist(main.distance_m), "along real roads", "green"),
              ("Route cost", f"{main.cost:,.0f}", "distance, moderate roads count x3", "orange"),
              ("Intersections", f"{main.intersections}", "on the route", "blue")])
    st.caption("Estimated travel time: not shown, because the notebook has no road speed or traffic data to calculate it from.")

    if res.get("bench") and res["bench"]["ok"]:
        b = res["bench"]
        ui.section("Dijkstra vs A*")
        import pandas as pd
        table = pd.DataFrame([
            {"Algorithm": "Dijkstra", "Distance": ui.fmt_dist(b["dijkstra"].distance_m), "Route cost": round(b["dijkstra"].cost, 2),
             "Intersections": b["dijkstra"].intersections, "Avg time (ms, 10 runs)": round(b["dijkstra_ms"], 2),
             "Nodes explored": b["dijkstra_expanded"]},
            {"Algorithm": "A*", "Distance": ui.fmt_dist(b["astar"].distance_m), "Route cost": round(b["astar"].cost, 2),
             "Intersections": b["astar"].intersections, "Avg time (ms, 10 runs)": round(b["astar_ms"], 2),
             "Nodes explored": b["astar_expanded"]}])
        ui.table(table)
        same = abs(b["dijkstra"].cost - b["astar"].cost) < 1e-6
        st.success("Both algorithms found a route of the same cost.") if same else st.warning("The two routes have different costs.")
    elif algo == "Compare both":
        st.warning("Comparison is not available for this pair.")

    _map(data, res)
    with st.expander("Route details (road by road)"):
        ui.table(rt.route_segments(H, main.path))


def _map(data, res):
    G, H = data["G"], data["H"]
    m = maps.create_base_map(zoom=14)
    maps.add_grey_network(m, G)
    legend = []
    coords_all = []
    if res and not res.get("error"):
        for key, label, colour, dash in (("dijkstra", "Dijkstra route", maps.ROUTE_COLORS["dijkstra"], None),
                                          ("astar", "A* route", "#f59e0b", "10 8")):
            r = res.get(key)
            if r is not None and r.found:
                coords = rt.path_coordinates(H, r.path)
                maps.add_route(m, coords, colour, label, weight=7 if key == "dijkstra" else 4, dash=dash)
                legend.append((colour, label))
                coords_all += coords
        main = next(r for r in (res.get("dijkstra"), res.get("astar")) if r is not None and r.found)
        maps.add_endpoint_markers(m, G, main.source, main.target, "Start", "Destination")
        maps.fit(m, coords_all)
    maps.add_areas(m, data["areas"])
    maps.add_shelters(m, data["shelters"])
    if legend:
        maps.add_legend(m, legend + [("#16a34a", "Start marker"), ("#dc2626", "Destination marker")], "Route")
    import folium
    folium.LayerControl(collapsed=True).add_to(m)
    ui.show_map(m, "route_map", height=560)
