"""
MOCK-BASED smoke test of the page code.  *** This is NOT a browser test. ***

Streamlit, streamlit-folium and Folium are replaced by simple stand-ins so the Python code of every page can be
executed end to end (including a pressed "Find route", a submitted blockage report and a run allocation) to catch
typos, wrong variable names and wrong data flow.  It cannot show whether the real widgets look or behave correctly.
The real application must still be checked by running:  streamlit run app.py

Run:  python -m tests.smoke_ui_stub
"""
import contextlib
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Fake:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Fake()
    def __getattr__(self, name): return Fake()
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter(())


PRESS = set()
LOG = []


class Col(Fake):
    """A column/container: widget calls are forwarded to the streamlit stand-in, as in real Streamlit."""
    def __getattr__(self, name):
        target = getattr(sys.modules["streamlit"], name, None)
        return target if callable(target) else Fake()


def make_streamlit():
    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.sidebar = Fake()
    st.column_config = Fake()

    def columns(spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [Col() for _ in range(n)]

    def selectbox(label, options, index=0, **k):
        options = list(options)
        key = k.get("key")
        if key and key in st.session_state and st.session_state[key] in options:
            return st.session_state[key]
        return options[index]

    def radio(label, options, index=0, **k): return list(options)[index]
    def button(label, **k): return label in PRESS
    def data_editor(df, **k): return df
    def text_area(*a, **k): return "stub description"
    def cache_resource(*a, **k):
        if a and callable(a[0]): return a[0]
        return lambda f: f
    def rerun(): LOG.append("rerun")
    def error(msg, *a, **k): LOG.append(("error", str(msg)))
    def warning(msg, *a, **k): LOG.append(("warning", str(msg)))
    def success(msg, *a, **k): LOG.append(("success", str(msg)))
    def info(msg, *a, **k): LOG.append(("info", str(msg)))

    for name, fn in dict(columns=columns, selectbox=selectbox, radio=radio, button=button, form_submit_button=button,
                         data_editor=data_editor, text_area=text_area, cache_resource=cache_resource, rerun=rerun,
                         error=error, warning=warning, success=success, info=info).items():
        setattr(st, name, fn)
    for name in ("markdown", "write", "caption", "dataframe", "pyplot", "set_page_config", "stop", "title", "header"):
        setattr(st, name, lambda *a, **k: None)
    for name in ("form", "expander", "spinner", "tabs", "container"):
        setattr(st, name, lambda *a, **k: Fake())
    return st


st_stub = make_streamlit()
sys.modules["streamlit"] = st_stub
sf = types.ModuleType("streamlit_folium"); sf.st_folium = lambda *a, **k: {}; sys.modules["streamlit_folium"] = sf
fo = types.ModuleType("folium"); fo.__getattr__ = lambda name: Fake(); sys.modules["folium"] = fo
for n in ("Map", "TileLayer", "GeoJson", "GeoJsonTooltip", "FeatureGroup", "Marker", "Icon", "Popup", "PolyLine",
          "CircleMarker", "LayerControl", "Element"):
    setattr(fo, n, Fake())

import state                                  # noqa: E402
from views import analytics, dashboard, flood_map, rerouting, resources, route   # noqa: E402
from core import config as cfg                # noqa: E402
from core import routing as rt                # noqa: E402


def run(name, fn, *args):
    LOG.clear()
    try:
        fn(*args)
        print(f"  ok    {name}")
    except Exception as exc:                  # noqa: BLE001
        import traceback; traceback.print_exc()
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
        return False
    return True


if __name__ == "__main__":
    data = state.load_all()
    ok = True
    ok &= run("Dashboard", dashboard.render, data)
    ok &= run("Flood map", flood_map.render, data)
    ok &= run("Route page (not pressed)", route.render, data)
    PRESS.add("Find route"); ok &= run("Route page (Find route, Dijkstra)", route.render, data)
    st_stub.radio = lambda label, options, index=0, **k: "Compare both" if "Compare both" in list(options) else list(options)[index]
    ok &= run("Route page (Compare both)", route.render, data)
    PRESS.clear()
    # --- reporting: pick a road on the default route, then press Submit
    d = rt.run_dijkstra(data["H"], 12497489526, 11050648635)
    st_stub.session_state["rr_sel"] = (d.path[27], d.path[28])
    PRESS.add("Submit Road Blockage Report")
    ok &= run("Rerouting (submit report)", rerouting.render, data)
    PRESS.clear()
    ok &= run("Rerouting (show stored result)", rerouting.render, data)
    out = st_stub.session_state.get("rr_out")
    print("        report status:", out["result"]["status"] if out else "NO RESULT STORED")
    ok &= bool(out and out["result"]["status"] == "rerouted")
    ok &= run("Resources (nothing selected)", resources.render, data)
    sel = data["areas"].copy(); sel["Evacuate"] = True; sel["People to evacuate"] = sel["Affected population"]
    st_stub.session_state["area_base"] = sel
    PRESS.add("Run Evacuation Allocation"); ok &= run("Resources (run allocation)", resources.render, data)
    PRESS.clear(); ok &= run("Resources (show results)", resources.render, data)
    ok &= run("Analytics", analytics.render, data)
    # clean up files written by the smoke test
    if os.path.exists(cfg.REPORTS_FILE): os.remove(cfg.REPORTS_FILE)
    print("\nSmoke test (mocks only):", "ALL PAGES RAN" if ok else "FAILURES")
    sys.exit(0 if ok else 1)
