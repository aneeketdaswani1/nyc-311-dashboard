import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
from pyathena import connect
from datetime import timedelta, datetime

# ---- Config ----
BUCKET = "nyc-311-dashboard-aniket"
S3_STAGING = f"s3://{BUCKET}/athena-results/"
REGION = "us-east-1"
DATABASE = "nyc311"

# Refined palette
C = {
    "teal": "#00D4AA", "cyan": "#4ECDC4", "coral": "#FF6B6B",
    "gold": "#FFE66D", "purple": "#A393EB", "orange": "#FF8A5C",
    "text": "#ccd6f6", "muted": "#8892b0", "dim": "#4a5568",
    "card": "#112240", "border": "rgba(0,212,170,0.15)",
    "grid": "#1a2744", "bg": "#0a192f",
}
CHART_SEQ = [C["teal"], C["coral"], C["cyan"], C["gold"], C["purple"], C["orange"]]

TYPE_COLORS = {
    "Noise - Residential": [255, 99, 71], "Noise - Street/Sidewalk": [255, 165, 0],
    "Blocked Driveway": [30, 144, 255], "Illegal Parking": [138, 43, 226],
    "UNSANITARY CONDITION": [50, 205, 50], "Noise - Commercial": [255, 215, 0],
    "Noise - Vehicle": [255, 140, 0], "Abandoned Vehicle": [70, 130, 180],
    "Street Condition": [210, 105, 30], "Dirty Condition": [128, 128, 0],
}
DEFAULT_COLOR = [180, 180, 180]
HEX_COLORS = [[1,152,189],[73,227,206],[216,254,181],[254,237,177],[254,173,84],[209,55,78]]


# ---- Theme ----
st.set_page_config(page_title="NYC 311 Dashboard", layout="wide")
st.markdown(f"""
<style>
    .block-container {{ padding-top: 1.5rem; }}
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #0a0f1a 0%, #0d1525 100%);
        border-right: 1px solid {C['grid']};
    }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
    .stTabs [data-baseweb="tab"] {{
        background: {C['card']}; border-radius: 8px;
        color: {C['muted']}; border: 1px solid transparent;
        padding: 8px 16px; font-size: 0.85rem;
    }}
    .stTabs [aria-selected="true"] {{
        background: #16213e; border: 1px solid {C['teal']};
        color: {C['teal']} !important; font-weight: 600;
    }}
    .stDownloadButton > button {{
        background: linear-gradient(135deg, {C['teal']}, {C['cyan']});
        color: #0a192f; border: none; font-weight: 600; border-radius: 8px;
    }}
    hr {{ border-color: {C['grid']} !important; }}
    .stDataFrame {{ border-radius: 8px; overflow: hidden; }}
    div[data-testid="metric-container"] {{ display: none; }}

    .kpi-grid {{ display: flex; gap: 16px; margin: 12px 0 20px 0; flex-wrap: wrap; }}
    .kpi-card {{
        flex: 1; min-width: 140px;
        background: linear-gradient(135deg, {C['card']} 0%, #16213e 100%);
        border: 1px solid {C['border']}; border-radius: 12px;
        padding: 18px 20px; text-align: center;
        box-shadow: 0 4px 20px rgba(0,212,170,0.06);
    }}
    .kpi-label {{ color: {C['muted']}; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; margin: 0; }}
    .kpi-value {{ color: {C['text']}; font-size: 1.6rem; font-weight: 700; margin: 6px 0 2px 0; }}
    .kpi-delta {{ font-size: 0.8rem; margin: 0; }}
    .kpi-up {{ color: {C['coral']}; }}
    .kpi-down {{ color: {C['teal']}; }}

    .header-banner {{
        background: linear-gradient(135deg, #0a192f 0%, #112240 50%, #1a3050 100%);
        border-radius: 16px; padding: 28px 32px; margin-bottom: 8px;
        border: 1px solid {C['border']};
    }}
    .header-title {{
        background: linear-gradient(90deg, {C['teal']}, {C['cyan']});
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 2.2rem; font-weight: 800; margin: 0; line-height: 1.2;
    }}
    .header-sub {{ color: {C['dim']}; font-size: 0.9rem; margin-top: 6px; }}
    .header-stats {{ display: flex; gap: 36px; margin-top: 18px; flex-wrap: wrap; }}
    .header-stat-val {{ color: {C['teal']}; font-size: 1.3rem; font-weight: 700; }}
    .header-stat-lbl {{ color: {C['dim']}; font-size: 0.75rem; display: block; margin-top: 2px; }}
</style>
""", unsafe_allow_html=True)


def sfig(fig):
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=C["muted"], size=12),
        xaxis=dict(gridcolor=C["grid"], zeroline=False),
        yaxis=dict(gridcolor=C["grid"], zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=C["muted"])),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# ---- Data ----
@st.cache_data(ttl=600)
def load_data():
    conn = connect(s3_staging_dir=S3_STAGING, region_name=REGION)
    df = pd.read_sql(
        f"""SELECT latitude, longitude, complaint_type, descriptor,
                   borough, created_date, closed_date, incident_zip, status
            FROM {DATABASE}.complaints""", conn)
    df["created_date"] = pd.to_datetime(df["created_date"])
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    df["hour"] = df["created_date"].dt.hour
    df["date"] = df["created_date"].dt.date
    df["day_name"] = df["created_date"].dt.day_name()
    df["resolution_hours"] = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    return df

with st.spinner("Loading from Athena..."):
    df_all = load_data()


# ---- Header banner ----
total = len(df_all)
date_min = df_all["created_date"].min().strftime("%b %d, %Y")
date_max = df_all["created_date"].max().strftime("%b %d, %Y")
n_zips = df_all["incident_zip"].nunique()

st.markdown(f"""
<div class="header-banner">
    <p class="header-title">NYC 311 Complaints</p>
    <p class="header-sub">Real-time geospatial intelligence &nbsp;&bull;&nbsp;
        S3 &rarr; Athena &rarr; Streamlit &nbsp;&bull;&nbsp; Deployed on ECS Fargate</p>
    <div class="header-stats">
        <div><span class="header-stat-val">{total:,}</span>
             <span class="header-stat-lbl">complaints analyzed</span></div>
        <div><span class="header-stat-val">{n_zips}</span>
             <span class="header-stat-lbl">zip codes covered</span></div>
        <div><span class="header-stat-val">{df_all['borough'].nunique()}</span>
             <span class="header-stat-lbl">boroughs</span></div>
        <div><span class="header-stat-val">{date_min} – {date_max}</span>
             <span class="header-stat-lbl">data range</span></div>
    </div>
</div>
""", unsafe_allow_html=True)


# ---- Sidebar ----
st.sidebar.markdown("### Filters")
boroughs = sorted(df_all["borough"].dropna().unique())
selected_boroughs = st.sidebar.multiselect("Borough", boroughs, default=boroughs)
complaint_types = sorted(df_all["complaint_type"].dropna().unique())
selected_types = st.sidebar.multiselect("Complaint type", complaint_types, help="Empty = all")
zip_codes = sorted(df_all["incident_zip"].dropna().unique())
selected_zips = st.sidebar.multiselect("Zip code", zip_codes, help="Empty = all")
min_d, max_d = df_all["created_date"].min().date(), df_all["created_date"].max().date()
date_range = st.sidebar.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)

st.sidebar.divider()
st.sidebar.markdown("### Map")
map_layer = st.sidebar.radio("Layer", ["3D Hexbin", "Heatmap", "Scatter"])
hex_r = st.sidebar.slider("Hex radius (m)", 100, 500, 200, 50) if map_layer == "3D Hexbin" else 200


# ---- Filter ----
df = df_all[df_all["borough"].isin(selected_boroughs)].copy()
if selected_types:
    df = df[df["complaint_type"].isin(selected_types)]
if selected_zips:
    df = df[df["incident_zip"].isin(selected_zips)]
if len(date_range) == 2:
    df = df[(df["date"] >= date_range[0]) & (df["date"] <= date_range[1])]


# ---- KPI cards ----
if len(df) > 0:
    delta_html = ""
    if len(date_range) == 2:
        td = (date_range[1] - date_range[0]).days
        if td >= 2:
            mid = date_range[0] + timedelta(days=td // 2)
            h1, h2 = len(df[df["date"] <= mid]), len(df[df["date"] > mid])
            if h1 > 0:
                dp = round((h2 - h1) / h1 * 100)
                cls = "kpi-up" if dp > 0 else "kpi-down"
                arrow = "&#9650;" if dp > 0 else "&#9660;"
                delta_html = f'<p class="kpi-delta {cls}">{arrow} {abs(dp)}% vs prior</p>'

    top_type = df["complaint_type"].value_counts().index[0]
    top_boro = df["borough"].value_counts().index[0]
    res = df["resolution_hours"].dropna()
    med_res = f"{res.median():.0f} hrs" if len(res) > 0 else "N/A"

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <p class="kpi-label">Total Complaints</p>
            <p class="kpi-value">{len(df):,}</p>{delta_html}
        </div>
        <div class="kpi-card">
            <p class="kpi-label">Top Complaint</p>
            <p class="kpi-value" style="font-size:1.1rem;">{top_type}</p>
        </div>
        <div class="kpi-card">
            <p class="kpi-label">Busiest Borough</p>
            <p class="kpi-value" style="font-size:1.2rem;">{top_boro}</p>
        </div>
        <div class="kpi-card">
            <p class="kpi-label">Median Resolution</p>
            <p class="kpi-value">{med_res}</p>
        </div>
        <div class="kpi-card">
            <p class="kpi-label">Date Span</p>
            <p class="kpi-value">{df['date'].nunique()} days</p>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ---- Map ----
if len(df) > 0:
    view = pdk.ViewState(latitude=40.7128, longitude=-74.0060, zoom=10, pitch=45)
    tooltip = None
    if map_layer == "3D Hexbin":
        layer = pdk.Layer("HexagonLayer", data=df[["latitude","longitude"]],
            get_position=["longitude","latitude"], radius=hex_r,
            elevation_scale=4, elevation_range=[0,1000],
            pickable=True, extruded=True, coverage=1, color_range=HEX_COLORS)
    elif map_layer == "Heatmap":
        layer = pdk.Layer("HeatmapLayer", data=df[["latitude","longitude"]],
            get_position=["longitude","latitude"], radius_pixels=60, intensity=1, threshold=0.03)
        view.pitch = 0
    else:
        dp = df[["latitude","longitude","complaint_type"]].copy()
        dp["r"] = dp["complaint_type"].map(lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[0])
        dp["g"] = dp["complaint_type"].map(lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[1])
        dp["b"] = dp["complaint_type"].map(lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[2])
        layer = pdk.Layer("ScatterplotLayer", data=dp,
            get_position=["longitude","latitude"], get_fill_color="[r,g,b]",
            get_radius=50, pickable=True, opacity=0.6)
        view.pitch = 0
        tooltip = {"text": "{complaint_type}"}
    st.pydeck_chart(pdk.Deck(initial_view_state=view, layers=[layer], tooltip=tooltip), use_container_width=True)
else:
    st.warning("No complaints match the current filters.")

st.divider()


# ---- Analytics ----
if len(df) > 0:
    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "Hourly", "Weekly Heatmap", "Trends",
        "Resolution Time", "Zip Codes", "Forecast", "Hotspots",
    ])

    with t1:
        h = df["hour"].value_counts().sort_index().reset_index()
        h.columns = ["Hour", "Complaints"]
        h["Label"] = h["Hour"].apply(lambda x: f"{x:02d}:00")
        fig = px.bar(h, x="Label", y="Complaints", color_discrete_sequence=[C["teal"]], template="plotly_dark")
        st.plotly_chart(sfig(fig), use_container_width=True)
        st.caption("Noise peaks after 10 PM. Parking and blocking issues spike in the morning.")

    with t2:
        days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        ht = df.groupby(["day_name","hour"]).size().reset_index(name="count")
        hp = ht.pivot(index="day_name", columns="hour", values="count").fillna(0).reindex(days)
        fig = px.imshow(hp, labels=dict(x="Hour",y="Day",color="Complaints"),
            color_continuous_scale=[C["bg"], C["teal"], C["gold"], C["coral"]],
            template="plotly_dark", aspect="auto")
        fig.update_xaxes(ticktext=[f"{i:02d}" for i in range(24)], tickvals=list(range(24)))
        st.plotly_chart(sfig(fig), use_container_width=True)

    with t3:
        c1, c2 = st.columns(2)
        with c1:
            dl = df.groupby(["date","borough"]).size().reset_index(name="count")
            fig = px.line(dl, x="date", y="count", color="borough",
                template="plotly_dark", color_discrete_sequence=CHART_SEQ)
            fig.update_layout(title="Daily complaints by borough")
            st.plotly_chart(sfig(fig), use_container_width=True)
        with c2:
            tc = df["complaint_type"].value_counts().head(10).reset_index()
            tc.columns = ["Type","Count"]
            fig = px.bar(tc, x="Count", y="Type", orientation="h",
                template="plotly_dark", color_discrete_sequence=[C["teal"]])
            fig.update_layout(title="Top 10 complaint types", yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(sfig(fig), use_container_width=True)

    with t4:
        rv = df[df["resolution_hours"].notna() & (df["resolution_hours"] > 0) & (df["resolution_hours"] < 8760)]
        if len(rv) > 0:
            c1, c2 = st.columns(2)
            with c1:
                rt = rv.groupby("complaint_type")["resolution_hours"].median().sort_values().tail(15).reset_index()
                rt.columns = ["Type","Median Hours"]
                fig = px.bar(rt, x="Median Hours", y="Type", orientation="h",
                    template="plotly_dark", color_discrete_sequence=[C["coral"]])
                fig.update_layout(title="Slowest to resolve (median hours)", yaxis=dict(categoryorder="total ascending"))
                st.plotly_chart(sfig(fig), use_container_width=True)
            with c2:
                rb = rv.groupby("borough")["resolution_hours"].median().sort_values(ascending=False).reset_index()
                rb.columns = ["Borough","Median Hours"]
                fig = px.bar(rb, x="Borough", y="Median Hours",
                    template="plotly_dark", color_discrete_sequence=[C["teal"]])
                fig.update_layout(title="Resolution time by borough")
                st.plotly_chart(sfig(fig), use_container_width=True)
            st.caption(f"Based on {len(rv):,} resolved complaints. Overall median: {rv['resolution_hours'].median():.1f} hours.")
        else:
            st.info("No resolution data available for current filters.")

    with t5:
        zd = df[df["incident_zip"].notna()]
        if len(zd) > 0:
            tz = zd["incident_zip"].value_counts().head(20).reset_index()
            tz.columns = ["Zip","Complaints"]
            fig = px.bar(tz, x="Complaints", y="Zip", orientation="h",
                template="plotly_dark", color_discrete_sequence=[C["cyan"]])
            fig.update_layout(title="Top 20 zip codes", yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(sfig(fig), use_container_width=True)
            ztbl = zd.groupby("incident_zip").agg(
                complaints=("complaint_type","count"),
                top_type=("complaint_type", lambda x: x.value_counts().index[0]),
                borough=("borough","first"),
            ).sort_values("complaints", ascending=False).head(25).reset_index()
            ztbl.columns = ["Zip Code","Complaints","Top Type","Borough"]
            ztbl.index = range(1, len(ztbl)+1)
            st.dataframe(ztbl, use_container_width=True)

    with t6:
        dt = df.groupby("date").size().reset_index(name="count").sort_values("date")
        if len(dt) >= 3:
            dt["day_num"] = (pd.to_datetime(dt["date"]) - pd.to_datetime(dt["date"].iloc[0])).dt.days
            coeffs = np.polyfit(dt["day_num"], dt["count"], deg=1)
            slope, intercept = coeffs
            residuals = dt["count"] - (slope * dt["day_num"] + intercept)
            std_err = residuals.std()

            last_day = dt["day_num"].iloc[-1]
            last_date = pd.to_datetime(dt["date"].iloc[-1])
            fut_days = np.arange(last_day+1, last_day+8)
            fut_dates = [last_date + timedelta(days=int(d - last_day)) for d in fut_days]
            fut_vals = np.maximum(slope * fut_days + intercept, 0)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=pd.to_datetime(dt["date"]), y=dt["count"],
                mode="lines+markers", name="Actual",
                line=dict(color=C["teal"], width=2), marker=dict(size=3)))
            fig.add_trace(go.Scatter(x=fut_dates, y=fut_vals,
                mode="lines+markers", name="Forecast",
                line=dict(color=C["coral"], width=2, dash="dash"), marker=dict(size=6, symbol="diamond")))
            fig.add_trace(go.Scatter(
                x=fut_dates + fut_dates[::-1],
                y=list(np.maximum(fut_vals + std_err, 0)) + list(np.maximum(fut_vals - std_err, 0))[::-1],
                fill="toself", fillcolor="rgba(255,107,107,0.1)",
                line=dict(width=0), name="Confidence band", showlegend=True))
            ad = list(pd.to_datetime(dt["date"])) + fut_dates
            fig.add_trace(go.Scatter(x=ad, y=slope*np.concatenate([dt["day_num"].values, fut_days])+intercept,
                mode="lines", name="Trend", line=dict(color=C["dim"], width=1, dash="dot")))
            fig.update_layout(template="plotly_dark", title="Daily complaints — actual + 7-day forecast",
                xaxis_title="Date", yaxis_title="Complaints")
            st.plotly_chart(sfig(fig), use_container_width=True)
            td = "upward" if slope > 0 else "downward"
            st.caption(f"Linear trend is {td} ({slope:+.1f}/day). Forecast avg: ~{int(np.mean(fut_vals))}/day. Band = 1 std dev.")
        else:
            st.info("Need 3+ days of data for forecasting.")

    with t7:
        dh = df.copy()
        dh["lat_r"] = dh["latitude"].round(3)
        dh["lng_r"] = dh["longitude"].round(3)
        hs = dh.groupby(["lat_r","lng_r","borough"]).agg(
            complaints=("complaint_type","count"),
            top_type=("complaint_type", lambda x: x.value_counts().index[0]),
        ).reset_index().sort_values("complaints", ascending=False).head(15)
        hs.columns = ["Latitude","Longitude","Borough","Complaints","Top Type"]
        hs.index = range(1, len(hs)+1)
        st.markdown("#### Complaint Hotspots")
        st.caption("Locations with highest density (rounded to ~1 block)")
        st.dataframe(hs, use_container_width=True)

    st.divider()
    top_t = df["complaint_type"].value_counts().index[0]
    top_b = df["borough"].value_counts().index[0]
    pk = df["hour"].value_counts().index[0]
    rn = ""
    rv2 = df[df["resolution_hours"].notna() & (df["resolution_hours"] > 0)]
    if len(rv2) > 0:
        sl = rv2.groupby("complaint_type")["resolution_hours"].median().idxmax()
        rn = f" *{sl}* takes longest to resolve."
    st.markdown(f"**Key Insight:** {top_b} leads with the most complaints, driven by *{top_t}*. Peak hour: **{pk:02d}:00**.{rn}")


# ---- Download ----
if len(df) > 0:
    st.divider()
    c1, c2 = st.columns([1, 3])
    with c1:
        st.download_button("Download filtered data",
            data=df.drop(columns=["hour","date","day_name","resolution_hours"], errors="ignore").to_csv(index=False),
            file_name="nyc_311_filtered.csv", mime="text/csv")
    with c2:
        st.caption(f"Exporting {len(df):,} records matching current filters")

st.divider()
st.markdown(f"""
<div style="text-align:center; color:{C['dim']}; padding:12px 0; font-size:0.85rem;">
    Built with Streamlit + pydeck + Plotly &bull; Data: NYC Open Data &bull; Cloud: AWS S3, Athena, ECS Fargate
    &bull; Last loaded: {datetime.now().strftime('%b %d, %Y %H:%M')}
</div>
""", unsafe_allow_html=True)