"""Page 2 - Interactive flood map of the real Velachery road network."""
import streamlit as st

import maps
import ui


def render(data):
    ui.hero("Interactive Flood Map", "Real Velachery roads coloured by simulated flood depth")
    ui.badges("real", "sim")
    st.caption("Hover over a road to see its name and simulated flood depth. Use the layer control (top right) "
               "to switch layers on or off.")
    m = maps.create_base_map(zoom=14)
    maps.add_flood_layers(m, data["flood_geojson"])
    maps.add_areas(m, data["areas"])
    maps.add_shelters(m, data["shelters"])
    maps.add_legend(m, maps.FLOOD_LEGEND + [("#f59e0b", "Marker: affected area"), ("#2563eb", "Marker: shelter")], "Legend")
    import folium
    folium.LayerControl(collapsed=True).add_to(m)
    ui.show_map(m, "flood_map", height=650)
    ui.note("Flood depths are random prototype values (np.random.seed(42), 0-80 cm), not live flood measurements.")
