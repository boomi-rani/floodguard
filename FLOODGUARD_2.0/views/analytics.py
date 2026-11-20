"""Page 6 - Analytics and comparison (measured results, simulated scenario results, theory - kept separate)."""
import pandas as pd
import streamlit as st

import ui
from core import allocation as al
from core import analytics as an
from core import routing as rt
from state import default_pair, locations

# Printed by the original Colab notebook (cell 16) - shown for reference, not re-measured.
NOTEBOOK_TIMES = {"Dijkstra": 5.152, "A*": 13.404}      # ms, average of 10 runs on Colab


def render(data):
    G, H = data["G"], data["H"]
    ui.hero("Analytics and Comparison", "Algorithm performance, rerouting tests and resource utilisation")
    st.caption("Sections are labelled **Measured** (timed on this computer), **Simulated scenario** (based on simulated flood and resource data) "
               "or **Theory** (textbook complexity). Nothing on this page is made up.")
    locs = locations(data)
    d_start, d_dest = default_pair(locs)
    source, target = list(locs.values())[d_start], list(locs.values())[d_dest]

    # ---------------- 1. Dijkstra vs A* ----------------
    ui.section("1. Dijkstra vs A*  -  Measured")
    st.write("Default scenario route: Area A to Shelter 3 (the route used in the notebook). Each algorithm is run 10 times; the average time is shown.")
    if "an_route" not in st.session_state or st.button("Re-run measurement"):
        st.session_state["an_route"] = an.route_comparison(H, source, target, repeats=10)
    comp = st.session_state["an_route"]
    if not comp["ok"]:
        st.error(comp["message"])
    else:
        t = comp["table"].copy()
        ui.table(t.assign(**{"Avg time (ms)": t["Avg time (ms)"].round(3), "Route cost": t["Route cost"].round(2),
                              "Distance (m)": t["Distance (m)"].round(1)}))
        if comp["same_cost"]:
            st.success("Both algorithms found the same optimal route cost.")
        c1, c2, c3 = st.columns(3)
        with c1:
            ui.bar_chart(list(t["Algorithm"]), list(t["Avg time (ms)"]), [ui.PALETTE["blue"], ui.PALETTE["teal"]],
                         "Average execution time (measured)", "milliseconds", fmt="%.2f")
        with c2:
            ui.bar_chart(list(t["Algorithm"]), list(t["Nodes explored"]), [ui.PALETTE["blue"], ui.PALETTE["teal"]],
                         "Intersections explored", "nodes", fmt="%d")
        with c3:
            ui.bar_chart(list(t["Algorithm"]), list(t["Route cost"]), [ui.PALETTE["blue"], ui.PALETTE["teal"]],
                         "Route cost", "cost", fmt="%.0f")
        st.caption(f"Original notebook (Google Colab) result for reference: Dijkstra {NOTEBOOK_TIMES['Dijkstra']} ms, A* {NOTEBOOK_TIMES['A*']} ms. "
                   "A* explores fewer intersections, but in Python its heuristic adds work per step, so it is not necessarily faster in wall-clock time.")

    with st.expander("Benchmark on many random start/destination pairs (Measured, takes a few seconds)"):
        if st.button("Run benchmark (15 random pairs)"):
            with st.spinner("Running benchmark..."):
                st.session_state["an_bench"] = rt.benchmark_random_pairs(H, n_pairs=15, repeats=3)
        bench = st.session_state.get("an_bench")
        if bench is not None and len(bench):
            ui.cards([("Pairs tested", len(bench), "random, at least 1 km apart", "blue"),
                      ("Mean Dijkstra time", f"{bench['Dijkstra ms'].mean():.2f} ms", "", "blue"),
                      ("Mean A* time", f"{bench['A* ms'].mean():.2f} ms", "", "blue"),
                      ("Mean nodes explored", f"{bench['Dijkstra nodes explored'].mean():.0f} vs {bench['A* nodes explored'].mean():.0f}", "Dijkstra vs A*", "blue")])
            ui.table(bench.round(2))
            st.caption("Same cost on every pair: " + ("yes" if bench["Same cost"].all() else "NO - check results"))

    # ---------------- 2. Dynamic rerouting ----------------
    st.markdown("---")
    ui.section("2. Dynamic rerouting  -  Measured test on the simulated scenario")
    st.write("Test: block each road segment of the default route in turn (as if it had been reported) and recalculate the route. "
             "These are test cases, not real reports.")
    if "an_rr" not in st.session_state:
        with st.spinner("Testing blockages..."):
            st.session_state["an_rr"] = an.rerouting_comparison(G, H, source, target, "Dijkstra")
    rr = st.session_state["an_rr"]
    if len(rr):
        ok = rr[rr["Result"] == "rerouted"]
        none = rr[rr["Result"] == "no_alternative"]
        ui.cards([("Road segments tested", len(rr), "on the default route", "blue"),
                  ("Alternative route found", len(ok), "", "green"),
                  ("No alternative", len(none), "", "red" if len(none) else "green"),
                  ("Average extra distance", f"{ok['Extra distance (m)'].mean():.0f} m" if len(ok) else "-", "when rerouted", "orange")])
        if len(ok):
            fig, ax = ui._fig(8, 3)
            ax.bar(ok["Blocked segment #"], ok["Extra distance (m)"], color=ui.PALETTE["purple"])
            ax.set_title("Extra distance of the alternative route, by blocked segment", fontsize=11, fontweight="bold", loc="left")
            ax.set_xlabel("Blocked segment # on the route")
            ax.set_ylabel("Extra metres")
            ui.show_fig(fig)
        with st.expander("Details"):
            ui.table(rr.round(1))
    last = st.session_state.get("rr_out")
    if last:
        res = last["result"]
        st.markdown("**Your latest road blockage report (unverified)**")
        row = {"Road": res["report"].road, "Reason": res["report"].reason, "Result": res["status"]}
        if res["difference"]:
            row.update({"Extra distance (m)": round(res["difference"]["distance_m"]), "Extra cost": round(res["difference"]["cost"], 1)})
        ui.table(pd.DataFrame([row]))

    # ---------------- 3. Resource allocation ----------------
    st.markdown("---")
    ui.section("3. Resource allocation  -  Simulated scenario")
    stored = st.session_state.get("alloc_res")
    if stored and stored["out"]["ok"]:
        out, label = stored["out"], "Your latest allocation run (Resource Allocation page)"
    else:
        areas = data["areas"].copy()
        areas["Evacuate"] = True
        areas["People to evacuate"] = areas["Affected population"]
        out, label = al.run_evacuation(H, areas, data["shelters"], data["vehicles"]), "Default scenario: all areas, full population, all vehicles"
    st.caption(label)
    if out["ok"]:
        s = out["summary"]
        ui.cards([("People to evacuate", s["total_people"], "", "blue"), ("Allocated to shelters", s["sheltered"], "", "green"),
                  ("Assigned to vehicles", s["with_vehicle"], "", "green" if s["without_vehicle_total"] == 0 else "orange"),
                  ("Unassigned (shelter / vehicle)", f"{s['without_shelter']} / {s['without_vehicle_total']}", "", "red" if (s["without_shelter"] or s["without_vehicle_total"]) else "green")])
        su, vu = out["shelter"]["shelter_utilization"], out["vehicle"]["vehicle_utilization"]
        c1, c2 = st.columns(2)
        with c1:
            ui.grouped_bar(list(su["Shelter"]), {"Capacity": (list(su["Capacity"]), ui.PALETTE["grey"]), "Allocated": (list(su["Allocated"]), ui.PALETTE["blue"])},
                           "Shelter utilisation", "People")
            ui.table(su)
        with c2:
            if len(vu):
                ui.bar_chart(list(vu["Vehicle"]), list(vu["Utilisation %"]), [ui.PALETTE["teal"]] * len(vu), "Vehicle utilisation", "% of seats used", fmt="%.0f%%")
            ui.table(vu)
        for w in out["warnings"]:
            st.warning(w)
    else:
        st.info("; ".join(out["errors"]))

    # ---------------- 4. Theory ----------------
    st.markdown("---")
    ui.section("4. Theoretical complexity  -  Theory (not measured)")
    ui.table(pd.DataFrame([
        {"Algorithm": "Dijkstra (binary heap)", "Time complexity": "O((V + E) log V)", "Used for": "Shortest flood-aware route, rerouting"},
        {"Algorithm": "A*", "Time complexity": "Same worst case as Dijkstra; usually explores fewer nodes with a good heuristic", "Used for": "Shortest route with straight-line guidance"},
        {"Algorithm": "Minimum-Cost Flow", "Time complexity": "NetworkX uses the network simplex method; no tight bound is claimed here", "Used for": "People to shelters"},
        {"Algorithm": "Greedy vehicle assignment", "Time complexity": "O(groups + vehicles)", "Used for": "Vehicles to groups of people"}]))
    st.caption(f"For this network V = {data['stats']['nodes']:,} intersections and E = {data['stats']['routable_edges']:,} routable road connections.")
