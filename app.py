"""
NYC 311 Dashboard — v4
=======================
Full-featured geospatial dashboard with resolution analysis,
zip code drill-down, and 7-day complaint forecast.
"""

import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
from pyathena import connect
from datetime import timedelta

# ---- Configuration ----
BUCKET = "nyc-311-dashboard-aniket"
S3_STAGING = f"s3://{BUCKET}/athena-results/"
REGION = "us-east-1"
DATABASE = "nyc311"

ACCENT = "#00D4AA"
CHART_COLORS = ["#00D4AA", "#FF6B6B", "#4ECDC4", "#FFE66D", "#A393EB", "#FF8A5C"]

TYPE_COLORS = {
    "Noise - Residential": [255, 99, 71],
    "Noise - Street/Sidewalk": [255, 165, 0],
    "Blocked Driveway": [30, 144, 255],
    "Illegal Parking": [138, 43, 226],
    "UNSANITARY CONDITION": [50, 205, 50],
    "Noise - Commercial": [255, 215, 0],
    "Noise - Vehicle": [255, 140, 0],
    "Abandoned Vehicle": [70, 130, 180],
    "Street Condition": [210, 105, 30],
    "Dirty Condition": [128, 128, 0],
}
DEFAULT_COLOR = [180, 180, 180]
HEX_COLORS = [
    [1, 152, 189], [73, 227, 206], [216, 254, 181],
    [254, 237, 177], [254, 173, 84], [209, 55, 78],
]


# ---- Theme ----
st.set_page_config(page_title="NYC 311 Dashboard", layout="wide")
st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid rgba(0, 212, 170, 0.2);
        border-radius: 12px; padding: 16px;
        box-shadow: 0 4px 15px rgba(0, 212, 170, 0.08);
    }
    div[data-testid="metric-container"] label { color: #8892b0 !important; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color: #e6f1ff !important; }
    section[data-testid="stSidebar"] { background-color: #0a0f1a; border-right: 1px solid #1a2744; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1a1a2e; border-radius: 8px;
        color: #8892b0; border: 1px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #16213e; border: 1px solid #00D4AA; color: #00D4AA !important;
    }
    .hero-title {
        background: linear-gradient(90deg, #00D4AA, #4ECDC4);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 2.5rem; font-weight: 800; margin-bottom: 0;
    }
    .hero-sub { color: #4a5568; font-size: 0.95rem; margin-top: 4px; }
    .stDownloadButton > button {
        background: linear-gradient(135deg, #00D4AA, #4ECDC4);
        color: #0E1117; border: none; font-weight: 600; border-radius: 8px;
    }
    hr { border-color: #1a2744 !important; }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


def style_fig(fig):
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892b0", size=12),
        xaxis=dict(gridcolor="#1a2744", zeroline=False),
        yaxis=dict(gridcolor="#1a2744", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#8892b0")),
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
            FROM {DATABASE}.complaints""",
        conn,
    )
    df["created_date"] = pd.to_datetime(df["created_date"])
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    df["hour"] = df["created_date"].dt.hour
    df["date"] = df["created_date"].dt.date
    df["day_name"] = df["created_date"].dt.day_name()
    df["resolution_hours"] = (
        (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    )
    return df


# ---- Header ----
st.markdown('<p class="hero-title">NYC 311 Complaints</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-sub">Real-time geospatial intelligence &nbsp;|&nbsp; '
    "S3 &rarr; Athena &rarr; Streamlit &nbsp;|&nbsp; Deployed on ECS Fargate</p>",
    unsafe_allow_html=True,
)
st.markdown("")

with st.spinner("Loading from Athena..."):
    df_all = load_data()


# ---- Sidebar ----
st.sidebar.markdown("### Filters")

boroughs = sorted(df_all["borough"].dropna().unique())
selected_boroughs = st.sidebar.multiselect("Borough", boroughs, default=boroughs)

complaint_types = sorted(df_all["complaint_type"].dropna().unique())
selected_types = st.sidebar.multiselect(
    "Complaint type", complaint_types, help="Leave empty to show all"
)

zip_codes = sorted(df_all["incident_zip"].dropna().unique())
selected_zips = st.sidebar.multiselect(
    "Zip code", zip_codes, help="Leave empty to show all"
)

min_date = df_all["created_date"].min().date()
max_date = df_all["created_date"].max().date()
date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date, max_value=max_date,
)

st.sidebar.divider()
st.sidebar.markdown("### Map Settings")
map_layer = st.sidebar.radio("Layer", ["3D Hexbin", "Heatmap", "Scatter by type"])
hex_radius = 200
if map_layer == "3D Hexbin":
    hex_radius = st.sidebar.slider("Hex radius (m)", 100, 500, 200, 50)


# ---- Apply filters ----
df = df_all[df_all["borough"].isin(selected_boroughs)].copy()
if selected_types:
    df = df[df["complaint_type"].isin(selected_types)]
if selected_zips:
    df = df[df["incident_zip"].isin(selected_zips)]
if len(date_range) == 2:
    df = df[(df["date"] >= date_range[0]) & (df["date"] <= date_range[1])]


# ---- KPI metrics ----
col1, col2, col3, col4, col5 = st.columns(5)

delta_str = None
if len(df) > 0 and len(date_range) == 2:
    total_days = (date_range[1] - date_range[0]).days
    if total_days >= 2:
        midpoint = date_range[0] + timedelta(days=total_days // 2)
        first_half = len(df[df["date"] <= midpoint])
        second_half = len(df[df["date"] > midpoint])
        if first_half > 0:
            delta_pct = round((second_half - first_half) / first_half * 100)
            delta_str = f"{delta_pct}% vs prior"

col1.metric("Total Complaints", f"{len(df):,}", delta=delta_str, delta_color="inverse")
if len(df) > 0:
    col2.metric("Top Complaint", df["complaint_type"].value_counts().index[0])
    col3.metric("Busiest Borough", df["borough"].value_counts().index[0])
    col4.metric("Date Span", f"{df['date'].nunique()} days")
    resolved = df["resolution_hours"].dropna()
    if len(resolved) > 0:
        col5.metric("Median Resolution", f"{resolved.median():.0f} hrs")
    else:
        col5.metric("Median Resolution", "N/A")

st.markdown("")


# ---- Map ----
if len(df) > 0:
    view = pdk.ViewState(latitude=40.7128, longitude=-74.0060, zoom=10, pitch=45)
    tooltip = None

    if map_layer == "3D Hexbin":
        layer = pdk.Layer(
            "HexagonLayer", data=df[["latitude", "longitude"]],
            get_position=["longitude", "latitude"], radius=hex_radius,
            elevation_scale=4, elevation_range=[0, 1000],
            pickable=True, extruded=True, coverage=1, color_range=HEX_COLORS,
        )
    elif map_layer == "Heatmap":
        layer = pdk.Layer(
            "HeatmapLayer", data=df[["latitude", "longitude"]],
            get_position=["longitude", "latitude"],
            radius_pixels=60, intensity=1, threshold=0.03,
        )
        view.pitch = 0
    else:
        df_plot = df[["latitude", "longitude", "complaint_type"]].copy()
        df_plot["r"] = df_plot["complaint_type"].map(lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[0])
        df_plot["g"] = df_plot["complaint_type"].map(lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[1])
        df_plot["b"] = df_plot["complaint_type"].map(lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[2])
        layer = pdk.Layer(
            "ScatterplotLayer", data=df_plot,
            get_position=["longitude", "latitude"], get_fill_color="[r, g, b]",
            get_radius=50, pickable=True, opacity=0.6,
        )
        view.pitch = 0
        tooltip = {"text": "{complaint_type}"}

    st.pydeck_chart(
        pdk.Deck(initial_view_state=view, layers=[layer], tooltip=tooltip),
        use_container_width=True,
    )
else:
    st.warning("No complaints match the current filters.")

st.divider()


# ---- Analytics tabs ----
if len(df) > 0:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Hourly", "Weekly Heatmap", "Trends",
        "Resolution Time", "Zip Codes", "Forecast",
    ])

    # -- Hourly --
    with tab1:
        hourly = df["hour"].value_counts().sort_index().reset_index()
        hourly.columns = ["Hour", "Complaints"]
        hourly["Label"] = hourly["Hour"].apply(lambda h: f"{h:02d}:00")
        fig = px.bar(hourly, x="Label", y="Complaints",
                     color_discrete_sequence=[ACCENT], template="plotly_dark")
        st.plotly_chart(style_fig(fig), use_container_width=True)

    # -- Weekly heatmap --
    with tab2:
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]
        heat = df.groupby(["day_name", "hour"]).size().reset_index(name="count")
        heat_pivot = heat.pivot(index="day_name", columns="hour", values="count").fillna(0).reindex(day_order)
        fig = px.imshow(heat_pivot,
                        labels=dict(x="Hour", y="Day", color="Complaints"),
                        color_continuous_scale=["#0E1117", "#00D4AA", "#FFE66D", "#FF6B6B"],
                        template="plotly_dark", aspect="auto")
        fig.update_xaxes(ticktext=[f"{h:02d}" for h in range(24)], tickvals=list(range(24)))
        st.plotly_chart(style_fig(fig), use_container_width=True)

    # -- Trends --
    with tab3:
        col_left, col_right = st.columns(2)
        with col_left:
            daily = df.groupby(["date", "borough"]).size().reset_index(name="count")
            fig = px.line(daily, x="date", y="count", color="borough",
                         template="plotly_dark", color_discrete_sequence=CHART_COLORS)
            fig.update_layout(title="Daily complaints by borough")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with col_right:
            tc = df["complaint_type"].value_counts().head(10).reset_index()
            tc.columns = ["Type", "Count"]
            fig = px.bar(tc, x="Count", y="Type", orientation="h",
                        template="plotly_dark", color_discrete_sequence=[ACCENT])
            fig.update_layout(title="Top 10 complaint types",
                            yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(style_fig(fig), use_container_width=True)

    # -- Resolution time --
    with tab4:
        resolved = df[df["resolution_hours"].notna() & (df["resolution_hours"] > 0)].copy()
        if len(resolved) > 0:
            col_r1, col_r2 = st.columns(2)

            with col_r1:
                res_by_type = (
                    resolved.groupby("complaint_type")["resolution_hours"]
                    .median()
                    .sort_values(ascending=True)
                    .tail(15)
                    .reset_index()
                )
                res_by_type.columns = ["Type", "Median Hours"]
                fig = px.bar(res_by_type, x="Median Hours", y="Type", orientation="h",
                            template="plotly_dark", color_discrete_sequence=["#FF6B6B"])
                fig.update_layout(title="Slowest to resolve (median hours)")
                st.plotly_chart(style_fig(fig), use_container_width=True)

            with col_r2:
                res_by_boro = (
                    resolved.groupby("borough")["resolution_hours"]
                    .median()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                res_by_boro.columns = ["Borough", "Median Hours"]
                fig = px.bar(res_by_boro, x="Borough", y="Median Hours",
                            template="plotly_dark", color_discrete_sequence=[ACCENT])
                fig.update_layout(title="Resolution time by borough")
                st.plotly_chart(style_fig(fig), use_container_width=True)

            st.caption(
                f"Based on {len(resolved):,} resolved complaints. "
                f"Overall median: {resolved['resolution_hours'].median():.1f} hours."
            )
        else:
            st.info("No resolution data available for the current filters.")

    # -- Zip codes --
    with tab5:
        zip_data = df[df["incident_zip"].notna()].copy()
        if len(zip_data) > 0:
            top_zips = (
                zip_data["incident_zip"]
                .value_counts()
                .head(20)
                .reset_index()
            )
            top_zips.columns = ["Zip Code", "Complaints"]
            fig = px.bar(top_zips, x="Complaints", y="Zip Code", orientation="h",
                        template="plotly_dark", color_discrete_sequence=[ACCENT])
            fig.update_layout(
                title="Top 20 zip codes by complaint volume",
                yaxis=dict(categoryorder="total ascending"),
            )
            st.plotly_chart(style_fig(fig), use_container_width=True)

            st.markdown("#### Zip code breakdown")
            zip_table = (
                zip_data.groupby("incident_zip")
                .agg(
                    complaints=("complaint_type", "count"),
                    top_type=("complaint_type", lambda x: x.value_counts().index[0]),
                    borough=("borough", "first"),
                )
                .sort_values("complaints", ascending=False)
                .head(25)
                .reset_index()
            )
            zip_table.columns = ["Zip Code", "Complaints", "Top Type", "Borough"]
            zip_table.index = range(1, len(zip_table) + 1)
            st.dataframe(zip_table, use_container_width=True)
        else:
            st.info("No zip code data available.")

    # -- Forecast --
    with tab6:
        daily_total = df.groupby("date").size().reset_index(name="count")
        daily_total = daily_total.sort_values("date")

        if len(daily_total) >= 3:
            # Convert dates to numeric for regression
            daily_total["day_num"] = (
                pd.to_datetime(daily_total["date"]) - pd.to_datetime(daily_total["date"].iloc[0])
            ).dt.days

            # Fit linear trend
            coeffs = np.polyfit(daily_total["day_num"], daily_total["count"], deg=1)
            slope, intercept = coeffs

            # Predict next 7 days
            last_day = daily_total["day_num"].iloc[-1]
            last_date = pd.to_datetime(daily_total["date"].iloc[-1])
            future_days = np.arange(last_day + 1, last_day + 8)
            future_dates = [last_date + timedelta(days=int(d - last_day)) for d in future_days]
            future_counts = np.maximum(slope * future_days + intercept, 0).astype(int)

            forecast_df = pd.DataFrame({
                "date": future_dates,
                "count": future_counts,
            })

            # Plot actual + forecast
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(daily_total["date"]),
                y=daily_total["count"],
                mode="lines+markers",
                name="Actual",
                line=dict(color=ACCENT, width=2),
                marker=dict(size=4),
            ))
            fig.add_trace(go.Scatter(
                x=forecast_df["date"],
                y=forecast_df["count"],
                mode="lines+markers",
                name="Forecast (7-day)",
                line=dict(color="#FF6B6B", width=2, dash="dash"),
                marker=dict(size=6, symbol="diamond"),
            ))
            # Trend line across all data
            all_days = np.concatenate([daily_total["day_num"].values, future_days])
            trend_vals = slope * all_days + intercept
            all_dates = list(pd.to_datetime(daily_total["date"])) + future_dates
            fig.add_trace(go.Scatter(
                x=all_dates, y=trend_vals,
                mode="lines", name="Trend",
                line=dict(color="#4a5568", width=1, dash="dot"),
            ))
            fig.update_layout(
                template="plotly_dark",
                title="Daily complaints — actual + 7-day forecast",
                xaxis_title="Date", yaxis_title="Complaints",
            )
            st.plotly_chart(style_fig(fig), use_container_width=True)

            trend_dir = "upward" if slope > 0 else "downward"
            avg_forecast = int(np.mean(future_counts))
            st.caption(
                f"Linear trend is {trend_dir} ({slope:+.1f} complaints/day). "
                f"Predicted average: ~{avg_forecast} complaints/day over the next week."
            )
        else:
            st.info("Need at least 3 days of data for forecasting.")

    # -- Auto insight --
    st.divider()
    if len(df) > 0:
        top_type = df["complaint_type"].value_counts().index[0]
        top_boro = df["borough"].value_counts().index[0]
        peak_hour = df["hour"].value_counts().index[0]
        resolved = df["resolution_hours"].dropna()
        res_note = ""
        if len(resolved) > 0:
            slowest = (
                df[df["resolution_hours"].notna()]
                .groupby("complaint_type")["resolution_hours"]
                .median()
                .idxmax()
            )
            res_note = f" *{slowest}* takes longest to resolve."
        st.markdown(
            f"**Key Insight:** {top_boro} leads with the most complaints, "
            f"driven by *{top_type}*. Peak hour is **{peak_hour:02d}:00**.{res_note}"
        )


# ---- Download ----
if len(df) > 0:
    st.divider()
    col_dl, col_info = st.columns([1, 3])
    with col_dl:
        st.download_button(
            "Download filtered data",
            data=df.drop(columns=["hour", "date", "day_name", "resolution_hours"], errors="ignore").to_csv(index=False),
            file_name="nyc_311_filtered.csv",
            mime="text/csv",
        )
    with col_info:
        st.caption(f"Exporting {len(df):,} records matching current filters")


# ---- Footer ----
st.divider()
st.markdown(
    "<div style='text-align:center; color:#4a5568; padding:12px 0;'>"
    "Built with Streamlit + pydeck + Plotly &nbsp;&bull;&nbsp; "
    "Data: NYC Open Data &nbsp;&bull;&nbsp; "
    "Cloud: AWS S3, Athena, ECS Fargate"
    "</div>",
    unsafe_allow_html=True,
)