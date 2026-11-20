"""Page 1 - Dashboard: overview of the current flood scenario."""
import streamlit as st

import maps
import ui


def render(data):
    G, stats, areas, shelters, vehicles = data["G"], data["stats"], data["areas"], data["shelters"], data["vehicles"]
    ui.hero("Dashboard", "Overview of the flood scenario for Velachery, Chennai")
    ui.badges("real", "sim")

    pop = int(areas["Affected population"].sum())
    cap = int(shelters["Total capacity"].sum())
    n_veh = int(vehicles["Vehicles available"].sum())
    veh_cap = int(vehicles["Total passenger capacity"].sum())

    ui.cards([("Road intersections", f"{stats['nodes']:,}", "OpenStreetMap", "blue"),
              ("Road segments", f"{stats['edges']:,}", "directed segments", "blue"),
              ("Safe roads", f"{stats['safe']:,}", "below 30 cm", "green"),
              ("Moderate roads", f"{stats['moderate']:,}", "30-69 cm", "orange"),
              ("Blocked roads", f"{stats['blocked']:,}", "70 cm and above", "red")])
    ui.cards([("Affected population", f"{pop:,}", f"{len(areas)} affected areas", "red"),
              ("Shelters", f"{len(shelters)}", f"total capacity {cap}", "blue"),
              ("Evacuation vehicles", f"{n_veh}", f"total capacity {veh_cap} passengers", "blue"),
              ("Shelter capacity vs population", f"{cap - pop:+d}", "spare places" if cap >= pop else "places short",
               "green" if cap >= pop else "red")])

    left, right = st.columns([1, 1.25])
    with left:
        ui.section("Road flood status")
        ui.donut(["Safe", "Moderate", "Blocked"], [stats["safe"], stats["moderate"], stats["blocked"]],
                 [ui.PALETTE["green"], ui.PALETTE["orange"], ui.PALETTE["red"]], "Road segments by flood status")
        ui.section("Flood severity of affected areas")
        ui.table(areas[["Area", "Flood severity", "Affected population"]])
        ui.note("Area severity = status of the deepest simulated road at that location.")
    with right:
        ui.section("Map preview")
        m = maps.create_base_map(zoom=13)
        maps.add_flood_layers(m, data["flood_geojson"], weight=1.6, tooltips=False)
        maps.add_areas(m, areas)
        maps.add_shelters(m, shelters)
        maps.add_legend(m, maps.FLOOD_LEGEND, "Road status")
        ui.show_map(m, "dash_map", height=470)
        ui.note("Open <b>Interactive Flood Map</b> for the full map with road details.")
