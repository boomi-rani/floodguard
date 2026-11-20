"""state.py - loads the saved data once and shares it between pages (read-only: copy before changing)."""
import streamlit as st

from core import allocation as al
from core import config as cfg
from core import network as nw
import maps


@st.cache_resource(show_spinner="Loading the Velachery road network...")
def load_all():
    G, H = nw.build_networks()
    scenario = nw.load_scenario()
    return {"G": G, "H": H, "scenario": scenario, "metadata": nw.load_metadata(),
            "stats": nw.graph_statistics(G, H), "road_index": nw.RoadIndex(G),
            "flood_geojson": maps.build_flood_geojson(G),
            "areas": al.build_area_table(G, scenario),
            "shelters": al.build_shelter_table(G, scenario),
            "vehicles": al.build_vehicle_table(scenario)}


def locations(data):
    """Named places a user can route between: affected areas and shelters (from the notebook scenario)."""
    out = {}
    for _, a in data["areas"].iterrows():
        out[f"{a['Area']} (affected area)"] = int(a["node"])
    for _, s in data["shelters"].iterrows():
        out[f"{s['Shelter']} (shelter)"] = int(s["node"])
    return out


def default_pair(locs):
    """Notebook default: Area A (start node 12497489526) -> Shelter 3 (destination node 11050648635)."""
    nodes = list(locs.values())
    return nodes.index(12497489526), nodes.index(11050648635)
