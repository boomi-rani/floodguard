"""Page 5 - Resource allocation: Affected Areas -> Shelters -> Vehicles -> Run -> Results."""
import folium
import pandas as pd
import streamlit as st

import maps
import ui
from core import allocation as al
from core import routing as rt

AREA_COLS = ["Area", "Nearest road (OSM)", "Flood severity", "Affected population", "Evacuate", "People to evacuate"]
SHELTER_COLS = ["Shelter", "Nearest road (OSM)", "Latitude", "Longitude", "Total capacity",
                "Currently allocated", "Remaining capacity"]
VEHICLE_COLS = ["Vehicle", "Location", "Vehicles available", "Capacity per vehicle",
                "Total passenger capacity", "Vehicles to use"]
SHELTER_COLOURS = ["#1d4ed8", "#7c3aed", "#0891b2", "#be185d", "#4d7c0f", "#c2410c"]


def render(data):
    H = data["H"]
    ui.hero("Resource Allocation", "Who needs evacuation, where they can go and how they get there")
    ui.badges("sim")
    st.caption("Affected population, shelters, shelter capacities and vehicles are simulated prototype values from the project notebook.")

    st.session_state.setdefault("area_ver", 0)
    st.session_state.setdefault("veh_ver", 0)
    st.session_state.setdefault("area_base", data["areas"].copy())

    # ================= A. AFFECTED AREAS =================
    ui.section("Affected areas", step="A")
    st.write("Tick the areas that need evacuation and enter how many people to evacuate from each.")
    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("Select all areas"):
        base = data["areas"].copy()
        base["Evacuate"] = True
        base["People to evacuate"] = base["Affected population"]
        st.session_state["area_base"] = base
        st.session_state["area_ver"] += 1
        st.rerun()
    if b2.button("Clear selection"):
        st.session_state["area_base"] = data["areas"].copy()
        st.session_state["area_ver"] += 1
        st.rerun()
    base = st.session_state["area_base"]
    edited = ui.editor(
        base[AREA_COLS], key=f"area_editor_{st.session_state['area_ver']}", column_order=AREA_COLS,
        disabled=["Area", "Nearest road (OSM)", "Flood severity", "Affected population"],
        column_config={
            "Area": st.column_config.TextColumn("Area / town"),
            "Nearest road (OSM)": st.column_config.TextColumn("Nearest road (OpenStreetMap)"),
            "Affected population": st.column_config.NumberColumn("Affected population", format="%d"),
            "Evacuate": st.column_config.CheckboxColumn("Evacuate?"),
            "People to evacuate": st.column_config.NumberColumn("People to evacuate", min_value=0, step=1, format="%d")})
    area_df = base.copy()
    area_df["Evacuate"] = edited["Evacuate"].values
    area_df["People to evacuate"] = edited["People to evacuate"].values
    area_errors = al.validate_areas(area_df)
    n_sel = int((area_df["Evacuate"] == True).sum())          # noqa: E712
    if area_errors and n_sel:
        for e in area_errors:
            st.error(e)
    elif n_sel:
        total_sel = int(pd.to_numeric(area_df.loc[area_df["Evacuate"] == True, "People to evacuate"]).sum())   # noqa: E712
        st.success(f"{n_sel} area(s) selected - {total_sel} people to evacuate.")
    else:
        st.info("No area selected yet.")
    ui.note("Area names (Area A-C) come from the notebook; it does not contain real town names. Flood severity is derived from "
            "the simulated flood depth of the deepest road at the area's location.")

    # ================= C (vehicles table state is needed for the sig) =================
    veh_base = data["vehicles"]

    # ================= B. SHELTERS =================
    st.markdown("---")
    ui.section("Shelters", step="B")
    st.write("Shelter capacity is fixed: no shelter is ever given more people than its capacity.")
    result = st.session_state.get("alloc_res")
    # vehicles editor lives in section C, but we need its values for the signature -> read from session state
    veh_df = _current_vehicle_df(veh_base)
    sig = _signature(area_df, veh_df)
    fresh = bool(result and result["sig"] == sig and result["out"]["ok"])
    shelters = data["shelters"].copy()
    if fresh:
        util = result["out"]["shelter"]["shelter_utilization"].set_index("Shelter")
        shelters["Currently allocated"] = shelters["Shelter"].map(util["Allocated"]).fillna(0).astype(int)
        shelters["Remaining capacity"] = shelters["Total capacity"] - shelters["Currently allocated"]
    ui.table(shelters[SHELTER_COLS])
    ui.note("'Currently allocated' is 0 until an allocation is run (the notebook has no existing shelter occupancy). "
            "Shelter names are from the notebook; no town names are available for them.")
    _shelter_map(data, area_df, shelters, result["out"]["shelter"]["allocation"] if fresh else None)

    # ================= C. VEHICLES =================
    st.markdown("---")
    ui.section("Vehicles", step="C")
    st.write("Confirm how many of the available vehicles will be used.")
    v_edit = ui.editor(
        veh_base[VEHICLE_COLS], key=f"veh_editor_{st.session_state['veh_ver']}", column_order=VEHICLE_COLS,
        disabled=["Vehicle", "Location", "Vehicles available", "Capacity per vehicle", "Total passenger capacity"],
        column_config={"Vehicles to use": st.column_config.NumberColumn("Vehicles to use", min_value=0, step=1, format="%d")})
    veh_df = veh_base.copy()
    veh_df["Vehicles to use"] = v_edit["Vehicles to use"].values
    veh_errors = al.validate_vehicles(veh_df)
    for e in veh_errors:
        st.error(e)
    ui.note("The notebook defines 5 vehicles of 20 passengers each (Vehicle 1-5). It has no vehicle types or locations, so none are shown.")
    sig = _signature(area_df, veh_df)

    # ================= D. RUN =================
    st.markdown("---")
    ui.section("Run evacuation allocation", step="D")
    st.write("Allocate the selected people to shelters (Minimum-Cost Flow) and assign vehicles (greedy assignment).")
    if st.button("Run Evacuation Allocation", type="primary"):
        out = al.run_evacuation(H, area_df, shelters_base(data), veh_df)
        st.session_state["alloc_res"] = {"sig": sig, "out": out}
        st.rerun()

    # ================= E. RESULTS =================
    st.markdown("---")
    ui.section("Final results", step="E")
    result = st.session_state.get("alloc_res")
    if not result:
        st.info("Select areas above and press **Run Evacuation Allocation** to see the results here.")
        return
    if result["sig"] != sig:
        st.warning("The selection has changed since the last run. Press **Run Evacuation Allocation** again to update the results.")
        return
    out = result["out"]
    if not out["ok"]:
        for e in out["errors"]:
            st.error(e)
        return
    _show_results(data, out, area_df, shelters)


def shelters_base(data):
    return data["shelters"]


def _current_vehicle_df(veh_base):
    """Vehicle table with the quantities currently typed into the editor (falls back to all available)."""
    df = veh_base.copy()
    state = st.session_state.get(f"veh_editor_{st.session_state['veh_ver']}")
    if isinstance(state, dict):
        for row, changes in state.get("edited_rows", {}).items():
            if "Vehicles to use" in changes:
                df.loc[df.index[int(row)], "Vehicles to use"] = changes["Vehicles to use"]
    return df


def _signature(area_df, veh_df):
    a = area_df[["Area", "Evacuate", "People to evacuate"]].astype(str).values.tolist()
    v = veh_df[["Vehicle", "Vehicles to use"]].astype(str).values.tolist()
    return str((a, v))


def _shelter_map(data, area_df, shelters, allocation):
    m = maps.create_base_map(zoom=14)
    maps.add_grey_network(m, data["G"], opacity=.35)
    selected = {r["Area"] for _, r in area_df.iterrows() if r["Evacuate"] is True or r["Evacuate"] == True}   # noqa: E712
    maps.add_areas(m, area_df, selected)
    maps.add_shelters(m, shelters, allocation)
    maps.add_legend(m, [("#f59e0b", "Affected area"), ("#2563eb", "Shelter")], "Map")
    folium.LayerControl(collapsed=True).add_to(m)
    ui.show_map(m, "res_map", height=380)


def _show_results(data, out, area_df, shelters):
    H = data["H"]
    s, so, vo = out["summary"], out["shelter"], out["vehicle"]
    ui.cards([("People requiring evacuation", s["total_people"], "selected by you", "blue"),
              ("Allocated to shelters", s["sheltered"], "of " + str(s["total_people"]), "green" if s["without_shelter"] == 0 else "orange"),
              ("Assigned to vehicles", s["with_vehicle"], "of " + str(s["sheltered"]) + " sheltered", "green" if s["without_vehicle_total"] == 0 else "orange"),
              ("Without shelter", s["without_shelter"], "no shelter place", "green" if s["without_shelter"] == 0 else "red"),
              ("Without vehicle", s["without_vehicle_total"], "no vehicle seat", "green" if s["without_vehicle_total"] == 0 else "red")])

    if s["fully_allocated"]:
        st.success(f"All {s['total_people']} people have a shelter place and a vehicle.")
    for w in out["warnings"]:
        st.warning(w)

    # ---- selected areas ----
    st.markdown("**Selected affected areas**")
    status = so["area_status"].rename(columns={"Affected area": "Area"})
    veh_by_area = vo["assignments"].groupby("Affected area")["People assigned"].sum() if len(vo["assignments"]) else pd.Series(dtype=int)
    status["With vehicle"] = status["Area"].map(veh_by_area).fillna(0).astype(int)
    status["Without vehicle"] = status["Sheltered"] - status["With vehicle"]
    sev = area_df.set_index("Area")
    status.insert(1, "Flood severity", status["Area"].map(sev["Flood severity"]))
    status.insert(2, "Affected population", status["Area"].map(sev["Affected population"]).astype(int))
    ui.table(status)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Shelter-wise population allocation**")
        if len(so["allocation"]):
            ui.table(so["allocation"][["Affected area", "Shelter", "People allocated", "Route cost per person"]])
        else:
            st.info("No one could be allocated to a shelter.")
        st.markdown("**Shelter capacity utilisation**")
        ui.table(so["shelter_utilization"])
        ui.grouped_bar(list(so["shelter_utilization"]["Shelter"]),
                       {"Capacity": (list(so["shelter_utilization"]["Capacity"]), ui.PALETTE["grey"]),
                        "Allocated": (list(so["shelter_utilization"]["Allocated"]), ui.PALETTE["blue"])},
                       "Shelter capacity vs people allocated", "People")
    with c2:
        st.markdown("**Vehicle-wise passenger assignment**")
        if len(vo["assignments"]):
            ui.table(vo["assignments"])
        else:
            st.info("No vehicles were assigned.")
        if len(vo["unserved"]):
            st.markdown("**People without a vehicle**")
            ui.table(vo["unserved"])
        st.markdown("**Vehicle utilisation**")
        ui.table(vo["vehicle_utilization"])
        if len(vo["vehicle_utilization"]):
            ui.bar_chart(list(vo["vehicle_utilization"]["Vehicle"]), list(vo["vehicle_utilization"]["Utilisation %"]),
                         [ui.PALETTE["blue"]] * len(vo["vehicle_utilization"]), "Vehicle utilisation", "% of seats used", fmt="%.0f%%")

    # ---- map of allocation routes ----
    st.markdown("**Allocation routes**")
    m = maps.create_base_map(zoom=14)
    maps.add_grey_network(m, data["G"], opacity=.35)
    names = list(shelters["Shelter"])
    legend = []
    area_nodes = area_df.set_index("Area")["node"]
    shel_nodes = shelters.set_index("Shelter")["node"]
    coords_all = []
    for _, r in so["allocation"].iterrows():
        res = rt.run_dijkstra(H, int(area_nodes[r["Affected area"]]), int(shel_nodes[r["Shelter"]]))
        if res.found:
            colour = SHELTER_COLOURS[names.index(r["Shelter"]) % len(SHELTER_COLOURS)]
            coords = rt.path_coordinates(H, res.path)
            maps.add_route(m, coords, colour, f"{r['Affected area']} -> {r['Shelter']}: {r['People allocated']} people", weight=5)
            coords_all += coords
            if (colour, r["Shelter"]) not in legend:
                legend.append((colour, f"Route to {r['Shelter']}"))
    selected = set(so["area_status"]["Affected area"])
    maps.add_areas(m, area_df, selected)
    maps.add_shelters(m, shelters, so["allocation"])
    maps.fit(m, coords_all)
    if legend:
        maps.add_legend(m, legend, "Allocation routes")
    folium.LayerControl(collapsed=True).add_to(m)
    ui.show_map(m, "res_result_map", height=460)

    with st.expander("How the allocation works"):
        st.markdown("- **Shelters:** every selected area is connected to every shelter it can reach by road; the cost is the cheapest "
                    "flood-aware route. A Minimum-Cost Flow assigns people so that total travel cost is lowest and no shelter exceeds its capacity.\n"
                    "- **Vehicles:** each group of people (area to shelter) is given the next free vehicle until the group is covered "
                    "or no vehicles are left. Each vehicle makes one trip and never carries more than its capacity.\n"
                    "- Travel times and return trips are not modelled, so this is a planning estimate, not a dispatch schedule.")
