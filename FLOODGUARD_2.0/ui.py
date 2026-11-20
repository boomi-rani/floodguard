"""ui.py - small Streamlit helpers (cards, headings, tables, charts) shared by all pages."""
import inspect
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt      # noqa: E402
import streamlit as st               # noqa: E402
from streamlit_folium import st_folium   # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PALETTE = {"blue": "#0b5394", "green": "#16a34a", "orange": "#f59e0b", "red": "#dc2626",
           "purple": "#7c3aed", "teal": "#0891b2", "grey": "#94a3b8"}


def load_css():
    with open(os.path.join(ROOT, "assets", "style.css"), encoding="utf-8") as fh:
        st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)


def hero(title, subtitle):
    st.markdown(f"<div class='fg-hero'><h1>{title}</h1><p>{subtitle}</p></div>", unsafe_allow_html=True)


def section(text, step=None):
    badge = f"<span class='fg-step'>{step}</span>" if step else ""
    st.markdown(f"<div class='fg-section'>{badge}{text}</div>", unsafe_allow_html=True)


def note(text):
    st.markdown(f"<div class='fg-note'>{text}</div>", unsafe_allow_html=True)


def badges(*kinds):
    labels = {"real": ("real", "REAL DATA: OpenStreetMap roads"),
              "sim": ("sim", "SIMULATED: flood depth, population, shelters, vehicles"),
              "unv": ("unv", "UNVERIFIED user reports")}
    st.markdown("".join(f"<span class='fg-badge {labels[k][0]}'>{labels[k][1]}</span>" for k in kinds),
                unsafe_allow_html=True)


def card(label, value, sub="", colour="blue"):
    cls = "" if colour == "blue" else colour
    return (f"<div class='fg-card {cls}'><div class='label'>{label}</div><div class='value'>{value}</div>"
            f"<div class='sub'>{sub}</div></div>")


def cards(items):
    """items: list of (label, value, sub, colour)."""
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        with col:
            st.markdown(card(*it), unsafe_allow_html=True)


def fmt_dist(m):
    return f"{m / 1000:.2f} km" if m >= 1000 else f"{m:.0f} m"


def _width_kwargs(func):
    return {"use_container_width": True} if "use_container_width" in inspect.signature(func).parameters else {}


def table(df, **kw):
    st.dataframe(df, hide_index=True, **_width_kwargs(st.dataframe), **kw)


def editor(df, **kw):
    return st.data_editor(df, hide_index=True, num_rows="fixed", **_width_kwargs(st.data_editor), **kw)


def show_map(m, key, height=560, returned=None):
    """Show a Folium map. returned=None -> clicks do not rerun the app; pass ['last_clicked'] to read clicks."""
    kwargs = {"height": height, "key": key, "returned_objects": returned or []}
    params = inspect.signature(st_folium).parameters
    if "use_container_width" in params:
        kwargs["use_container_width"] = True
    elif "width" in params:
        kwargs["width"] = 1200
    return st_folium(m, **kwargs)


# ----------------------------------------------------------------------------- charts
def _fig(w=5.6, h=3.2):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.25)
    return fig, ax


def show_fig(fig):
    fig.tight_layout()
    kw = {"use_container_width": True} if "use_container_width" in inspect.signature(st.pyplot).parameters else {}
    st.pyplot(fig, **kw)
    plt.close(fig)


def bar_chart(labels, values, colours, title, ylabel, fmt="%.1f"):
    fig, ax = _fig()
    bars = ax.bar(labels, values, color=colours, width=.55)
    ax.bar_label(bars, fmt=fmt, padding=2, fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, max(values) * 1.18 if max(values) > 0 else 1)
    show_fig(fig)


def grouped_bar(categories, series, title, ylabel):
    """series: {label: (values, colour)}."""
    import numpy as np
    fig, ax = _fig()
    x = np.arange(len(categories))
    w = .8 / len(series)
    for i, (label, (vals, colour)) in enumerate(series.items()):
        bars = ax.bar(x + i * w - .4 + w / 2, vals, w, label=label, color=colour)
        ax.bar_label(bars, fmt="%g", padding=2, fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    ax.set_ylabel(ylabel)
    ax.legend(frameon=False, fontsize=8)
    show_fig(fig)


def donut(labels, values, colours, title):
    fig, ax = plt.subplots(figsize=(4.4, 3.2))
    ax.pie(values, labels=None, colors=colours, startangle=90, wedgeprops=dict(width=.42, edgecolor="white"),
           autopct=lambda p: f"{p:.0f}%" if p > 4 else "", pctdistance=.79, textprops=dict(color="white", fontsize=9))
    ax.legend([f"{l} ({v:,})" for l, v in zip(labels, values)], loc="center left", bbox_to_anchor=(1, .5), frameon=False, fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    show_fig(fig)
