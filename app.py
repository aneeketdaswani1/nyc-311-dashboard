import streamlit as st
import pandas as pd
import pydeck as pdk
import plotly.express as px
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
    [1, 152, 189],
    [73, 227, 206],
    [216, 254, 181],
    [254, 237, 177],
    [254, 173, 84],
    [209, 55, 78],
]


# ---- Page config + custom CSS ----
st.set_page_config(page_title="NYC 311 Dashboard", layout="wide")

st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid rgba(0, 212, 170, 0.2);
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 15px rgba(0, 212, 170, 0.08);
    }
    div[data-testid="metric-container"] label {
        color: #8892b0 !important;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #e6f1ff !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #0a0f1a;
        border-right: 1px solid #1a2744;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1a1a2e;
        border-radius: 8px;
        color: #8892b0;
        border: 1px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #16213e;
        border: 1px solid #00D4AA;
        color: #00D4AA !important;
    }
    .hero-title {
        background: linear-gradient(90deg, #00D4AA, #4ECDC4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 800;
        margin-bottom: 0;
    }
    .hero-sub {
        color: #4a5568;
        font-size: 0.95rem;
        margin-top: 4px;
    }
    .stDownloadButton > button {
        background: linear-gradient(135deg, #00D4AA, #4ECDC4);
        color: #0E1117;
        border: none;
        font-weight: 600;
        border-radius: 8px;
    }
    hr { border-color: #1a2744 !important; }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


def style_fig(fig):
    """Apply consistent dark styling to all plotly charts."""
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892b0", size=12),
        xaxis=dict(gridcolor="#1a2744", zeroline=False),
        yaxis=dict(gridcolor="#1a2744", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#8892b0")),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# ---- Data loading ----
@st.cache_data(ttl=600)
def load_data():
    conn = connect(s3_staging_dir=S3_STAGING, region_name=REGION)
    df = pd.read_sql(
        f"""SELECT latitude, longitude, complaint_type, descriptor,
                   borough, created_date
            FROM {DATABASE}.complaints""",
        conn,
    )
    df["created_date"] = pd.to_datetime(df["created_date"])
    df["hour"] = df["created_date"].dt.hour
    df["date"] = df["created_date"].dt.date
    df["day_name"] = df["created_date"].dt.day_name()
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

min_date = df_all["created_date"].min().date()
max_date = df_all["created_date"].max().date()
date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
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
if len(date_range) == 2:
    df = df[(df["date"] >= date_range[0]) & (df["date"] <= date_range[1])]


# ---- KPI metrics ----
col1, col2, col3, col4 = st.columns(4)

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

st.markdown("")


# ---- Map ----
if len(df) > 0:
    view = pdk.ViewState(latitude=40.7128, longitude=-74.0060, zoom=10, pitch=45)
    tooltip = None

    if map_layer == "3D Hexbin":
        layer = pdk.Layer(
            "HexagonLayer",
            data=df[["latitude", "longitude"]],
            get_position=["longitude", "latitude"],
            radius=hex_radius,
            elevation_scale=4,
            elevation_range=[0, 1000],
            pickable=True,
            extruded=True,
            coverage=1,
            color_range=HEX_COLORS,
        )
    elif map_layer == "Heatmap":
        layer = pdk.Layer(
            "HeatmapLayer",
            data=df[["latitude", "longitude"]],
            get_position=["longitude", "latitude"],
            radius_pixels=60,
            intensity=1,
            threshold=0.03,
        )
        view.pitch = 0
    else:
        df_plot = df[["latitude", "longitude", "complaint_type"]].copy()
        df_plot["r"] = df_plot["complaint_type"].map(
            lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[0]
        )
        df_plot["g"] = df_plot["complaint_type"].map(
            lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[1]
        )
        df_plot["b"] = df_plot["complaint_type"].map(
            lambda t: TYPE_COLORS.get(t, DEFAULT_COLOR)[2]
        )
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df_plot,
            get_position=["longitude", "latitude"],
            get_fill_color="[r, g, b]",
            get_radius=50,
            pickable=True,
            opacity=0.6,
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
    tab1, tab2, tab3, tab4 = st.tabs([
        "Hourly Pattern", "Weekly Heatmap", "Trends", "Top Hotspots",
    ])

    with tab1:
        hourly = df["hour"].value_counts().sort_index().reset_index()
        hourly.columns = ["Hour", "Complaints"]
        hourly["Label"] = hourly["Hour"].apply(lambda h: f"{h:02d}:00")
        fig = px.bar(
            hourly, x="Label", y="Complaints",
            color_discrete_sequence=[ACCENT],
            template="plotly_dark",
        )
        st.plotly_chart(style_fig(fig), use_container_width=True)
        st.caption(
            "Noise complaints spike after 10 PM. "
            "Parking and blocking issues peak during morning hours."
        )

    with tab2:
        day_order = [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ]
        heat = (
            df.groupby(["day_name", "hour"]).size().reset_index(name="count")
        )
        heat_pivot = (
            heat.pivot(index="day_name", columns="hour", values="count")
            .fillna(0)
            .reindex(day_order)
        )
        fig = px.imshow(
            heat_pivot,
            labels=dict(x="Hour", y="Day", color="Complaints"),
            color_continuous_scale=["#0E1117", "#00D4AA", "#FFE66D", "#FF6B6B"],
            template="plotly_dark",
            aspect="auto",
        )
        fig.update_xaxes(
            ticktext=[f"{h:02d}" for h in range(24)],
            tickvals=list(range(24)),
        )
        st.plotly_chart(style_fig(fig), use_container_width=True)
        st.caption(
            "Spot the patterns: weekday noise vs weekend parking, "
            "quiet Sunday mornings, late-night hotspots."
        )

    with tab3:
        col_left, col_right = st.columns(2)
        with col_left:
            daily = (
                df.groupby(["date", "borough"]).size().reset_index(name="count")
            )
            fig = px.line(
                daily, x="date", y="count", color="borough",
                template="plotly_dark",
                color_discrete_sequence=CHART_COLORS,
            )
            fig.update_layout(title="Daily complaints by borough")
            st.plotly_chart(style_fig(fig), use_container_width=True)

        with col_right:
            type_counts = (
                df["complaint_type"].value_counts().head(10).reset_index()
            )
            type_counts.columns = ["Type", "Count"]
            fig = px.bar(
                type_counts, x="Count", y="Type", orientation="h",
                template="plotly_dark",
                color_discrete_sequence=[ACCENT],
            )
            fig.update_layout(
                title="Top 10 complaint types",
                yaxis=dict(categoryorder="total ascending"),
            )
            st.plotly_chart(style_fig(fig), use_container_width=True)

    with tab4:
        st.markdown("#### Complaint Hotspots")
        st.caption("Locations with the highest complaint density (rounded to ~1 block)")
        df_hs = df.copy()
        df_hs["lat_r"] = df_hs["latitude"].round(3)
        df_hs["lng_r"] = df_hs["longitude"].round(3)
        hotspots = (
            df_hs.groupby(["lat_r", "lng_r", "borough"])
            .agg(
                complaints=("complaint_type", "count"),
                top_type=(
                    "complaint_type",
                    lambda x: x.value_counts().index[0],
                ),
            )
            .reset_index()
            .sort_values("complaints", ascending=False)
            .head(15)
        )
        hotspots.columns = [
            "Latitude", "Longitude", "Borough", "Complaints", "Top Type",
        ]
        hotspots = hotspots.reset_index(drop=True)
        hotspots.index += 1
        st.dataframe(hotspots, use_container_width=True)

    # Auto-generated insight
    st.divider()
    top_type = df["complaint_type"].value_counts().index[0]
    top_boro = df["borough"].value_counts().index[0]
    peak_hour = df["hour"].value_counts().index[0]
    st.markdown(
        f"**Key Insight:** {top_boro} leads with the most complaints, "
        f"driven primarily by *{top_type}*. "
        f"Complaints peak around **{peak_hour:02d}:00**, "
        f"suggesting targeted enforcement during these hours could reduce volume."
    )


# ---- Download ----
if len(df) > 0:
    st.divider()
    col_dl, col_info = st.columns([1, 3])
    with col_dl:
        st.download_button(
            label="Download filtered data",
            data=df.drop(columns=["hour", "date", "day_name"]).to_csv(index=False),
            file_name="nyc_311_filtered.csv",
            mime="text/csv",
        )
    with col_info:
        st.caption(f"Exporting {len(df):,} records matching current filters")


# ---- Footer ----
st.divider()
st.markdown(
    "<div style='text-align:center; color:#4a5568; padding:12px 0;'>"
    "Built with Streamlit + pydeck &nbsp;&bull;&nbsp; "
    "Data: NYC Open Data &nbsp;&bull;&nbsp; "
    "Cloud: AWS S3, Athena, ECS Fargate"
    "</div>",
    unsafe_allow_html=True,
)
