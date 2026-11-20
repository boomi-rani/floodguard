"""
FLOODGUARD 2.0 - Intelligent Flood Evacuation and Resource Allocation System
Final-year project. Start with:   streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="FLOODGUARD 2.0", page_icon="🌊", layout="wide")

import ui                                   # noqa: E402
from state import load_all                  # noqa: E402
from views import analytics, dashboard, flood_map, rerouting, resources, route   # noqa: E402

PAGES = {
    "Dashboard": dashboard,
    "Interactive Flood Map": flood_map,
    "Route Optimization": route,
    "Dynamic Rerouting": rerouting,
    "Resource Allocation": resources,
    "Analytics and Comparison": analytics,
}


def main():
    ui.load_css()
    st.sidebar.markdown("## 🌊 FLOODGUARD 2.0")
    st.sidebar.caption("Flood evacuation and resource allocation · Velachery, Chennai")
    page = st.sidebar.radio("Navigation", list(PAGES), label_visibility="collapsed")
    st.sidebar.markdown("---")
    st.sidebar.caption("**Real data:** OpenStreetMap road network.\n\n"
                       "**Simulated data:** flood depths, affected population, shelters and vehicles. "
                       "These are not live measurements.")
    try:
        data = load_all()
    except FileNotFoundError as exc:
        st.error(f"A required data file is missing: {exc}. Keep the 'data' folder next to app.py.")
        st.stop()
    PAGES[page].render(data)


main()
