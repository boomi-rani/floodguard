"""Page 4 - Dynamic rerouting driven by USER-REPORTED road blockages (unverified)."""
import folium
import pandas as pd
import streamlit as st

import maps
import ui
from core import blockage as bk
from core import config as cfg
from core import routing as rt
from core.network import road_name
from state import default_pair, locations


def _edge_data(G, u, v):
    e = G[u][v] if G.has_edge(u, v) else G[v][u]
    return e[next(iter(e))]


def render(data):
    G, H, index = data["G"], data["H"], data["road_index"]
    ui.hero("Dynamic Rerouting", "Report a blocked road and get an alternative route")
    ui.badges("real", "unv")
    st.caption("Reports are saved in a local file on this computer (data/blockage_reports.json). They are **not shared with "
               "other users** and are **not verified** - this is a prototype, not a live multi-user reporting system.")

    prior = bk.load_reports()
    H_base = bk.build_working_graph(H, prior)          # copy: roads reported earlier are already unavailable
    if prior:
        st.warning(f"{len(prior)} earlier unverified report(s) are already applied to the network used on this page.")

    # ---- route to protect ----------------------------------------------------------------
    ui.section("Route to keep open")
    locs = locations(data)
    names = list(locs)
    d_start, d_dest = default_pair(locs)
    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    start_name = c1.selectbox("Starting point", names, index=d_start, key="rr_start")
    dest_name = c2.selectbox("Destination", names, index=d_dest, key="rr_dest")
    algo = c3.radio("Algorithm", ["Dijkstra", "A*"], horizontal=True, key="rr_algo")
    source, target = locs[start_name], locs[dest_name]
    if source == target:
        st.error("Starting point and destination are the same. Please choose different places.")
        return
    current = rt.run_algorithm(H_base, source, target, algo)
    if not current.found:
        st.error(current.message or "No route is currently available between these places.")
        return
    ui.cards([("Current route distance", ui.fmt_dist(current.distance_m), "", "green"),
              ("Route cost", f"{current.cost:,.0f}", "", "orange"),
              ("Intersections", f"{current.intersections}", "", "blue")])

    # ---- step 1: select road -------------------------------------------------------------
    ui.section("Select the blocked road", step=1)
    seg = rt.route_segments(H_base, current.path)
    seen, options = set(), {}
    for _, r in seg.iterrows():
        key = frozenset((r["From node"], r["To node"]))
        if key in seen:
            continue
        seen.add(key)
        options[f"#{r['#']}  {r['Road']}  ({r['Length (m)']:.0f} m)"] = (int(r["From node"]), int(r["To node"]))
    labels = ["- choose a road on the current route -"] + list(options)

    def _from_list():
        choice = st.session_state["rr_pick"]
        st.session_state["rr_sel"] = options.get(choice)

    st.selectbox("Road on the current route", labels, key="rr_pick", on_change=_from_list)
    st.caption("Or click directly on any road on the map below.")

    m = maps.create_base_map(zoom=14)
    maps.add_grey_network(m, G)
    maps.add_route(m, rt.path_coordinates(H_base, current.path), maps.ROUTE_COLORS["original"], "Current route", weight=6)
    maps.add_endpoint_markers(m, G, source, target)
    maps.add_reports(m, prior)
    sel = st.session_state.get("rr_sel")
    legend = [(maps.ROUTE_COLORS["original"], "Current route")]
    if sel:
        maps.add_blocked_road(m, G, sel[0], sel[1], "Selected road")
        legend.append(("#dc2626", "Selected road"))
    maps.add_legend(m, legend, "Map")
    out = ui.show_map(m, "rr_select_map", height=480, returned=["last_clicked"])
    click = (out or {}).get("last_clicked")
    if click and click != st.session_state.get("rr_last_click"):
        st.session_state["rr_last_click"] = click
        u, v, _, dist = index.nearest_edge(click["lat"], click["lng"])
        if dist <= 60:
            st.session_state["rr_sel"] = (u, v)
            st.rerun()
        else:
            st.warning("No road found close to where you clicked. Please click closer to a road.")

    sel = st.session_state.get("rr_sel")
    if not sel:
        st.info("Select a road using the list or by clicking the map to continue.")
    else:
        d = _edge_data(G, *sel)
        mid = d["geometry"][len(d["geometry"]) // 2]
        st.success(f"Selected road: **{road_name(d)}** - about {d['length']:.0f} m long "
                   f"(location {mid[0]:.5f}, {mid[1]:.5f})")

        # ---- step 2: report ---------------------------------------------------------------
        ui.section("Submit a blockage report", step=2)
        with st.form("report_form"):
            reason = st.radio("Reason for the blockage", cfg.BLOCKAGE_REASONS, horizontal=True)
            description = st.text_area("Description (optional)", max_chars=300, height=80,
                                       placeholder="e.g. Water above knee level near the junction")
            submitted = st.form_submit_button("Submit Road Blockage Report", type="primary")
        if submitted:
            try:
                report = bk.create_report(G, sel[0], sel[1], reason, description)
                result = bk.process_report(H_base, source, target, report, algo)     # step 3
                st.session_state["rr_out"] = {"result": result, "source": source, "target": target, "algo": algo}
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    _show_result(data, source, target)
    _show_reports(prior)


def _show_result(data, source_now, target_now):
    out = st.session_state.get("rr_out")
    if not out:
        return
    if (out["source"], out["target"]) != (source_now, target_now):
        st.info("The route selection changed since the last report. Select a road and submit a new report to see its result.")
        return
    G, H = data["G"], data["H"]       # H still holds every road shape, so both paths can be drawn
    res, source, target = out["result"], out["source"], out["target"]
    rep, orig, alt = res["report"], res["original"], res["alternative"]
    st.markdown("---")
    ui.section("Report processed", step=3)
    st.success(f"Report saved for **{rep.road}** - reason: {rep.reason}. Status: **{rep.status}**. "
               "The road is now unavailable in the working routing graph (both directions); the original graph is unchanged.")

    ui.section("Rerouting result", step=4)
    status = res["status"]
    if status == "rerouted":
        st.success(res["message"])
    elif status in ("not_affected", "already_unavailable"):
        st.info(res["message"])
    else:
        st.error(res["message"])

    if status == "rerouted":
        diff = res["difference"]
        table = pd.DataFrame([
            {"": "Original route", "Distance": ui.fmt_dist(orig.distance_m), "Route cost": round(orig.cost, 1), "Intersections": orig.intersections},
            {"": "Alternative route", "Distance": ui.fmt_dist(alt.distance_m), "Route cost": round(alt.cost, 1), "Intersections": alt.intersections},
            {"": "Difference", "Distance": f"{diff['distance_m']:+,.0f} m", "Route cost": f"{diff['cost']:+,.1f}", "Intersections": f"{diff['intersections']:+d}"}])
        ui.table(table)

    m = maps.create_base_map(zoom=14)
    maps.add_grey_network(m, G)
    coords = rt.path_coordinates(H, orig.path)
    maps.add_route(m, coords, maps.ROUTE_COLORS["original"], "Original route", weight=6, dash="10 8" if status == "rerouted" else None)
    legend = [(maps.ROUTE_COLORS["original"], "Original route")]
    if status == "rerouted":
        alt_coords = rt.path_coordinates(H, alt.path)
        maps.add_route(m, alt_coords, maps.ROUTE_COLORS["alternative"], "Alternative route", weight=7)
        legend.append((maps.ROUTE_COLORS["alternative"], "Alternative route"))
        coords = coords + alt_coords
    maps.add_blocked_road(m, G, rep.u, rep.v, f"Reported blocked road: {rep.road} (unverified)")
    legend.append(("#dc2626", "Reported blocked road"))
    maps.add_endpoint_markers(m, G, source, target)
    maps.fit(m, coords)
    maps.add_legend(m, legend, "Rerouting")
    ui.show_map(m, "rr_result_map", height=520)


def _show_reports(prior):
    reports = bk.load_reports()
    st.markdown("---")
    ui.section("Submitted reports")
    if not reports:
        st.caption("No reports have been submitted yet.")
        return
    ui.table(pd.DataFrame([{"ID": r.report_id, "Road": r.road, "Reason": r.reason, "Description": r.description,
                            "Reported at": r.reported_at, "Status": r.status} for r in reports]))
    c1, c2 = st.columns([2, 1])
    to_delete = c1.selectbox("Remove a report", ["-"] + [f"{r.report_id} - {r.road}" for r in reports], key="rr_del")
    if c1.button("Remove selected report") and to_delete != "-":
        bk.delete_report(to_delete.split(" - ")[0])
        st.session_state.pop("rr_out", None)
        st.rerun()
    if c2.button("Clear all reports"):
        bk.clear_reports()
        st.session_state.pop("rr_out", None)
        st.session_state.pop("rr_sel", None)
        st.rerun()
