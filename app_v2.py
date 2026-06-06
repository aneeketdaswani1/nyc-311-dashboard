import streamlit as st
import pandas as pd
import pydeck as pdk
from pyathena import connect
from datetime import timedelta

# ---- Configuration ----
BUCKET = "nyc-311-dashboard-aniket"
S3_STAGING = f"s3://{BUCKET}/athena-results/"
REGION = "us-east-1"
DATABASE = "nyc311"

# Scatter plot color palette (top complaint types)
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

# Custom hex ramp: teal → yellow → red
HEX_COLORS = [
    [1, 152, 189],
    [73, 227, 206],
    [216, 254, 181],
    [254, 237, 177],
    [254, 173, 84],
    [209, 55, 78],
]


# ---- Data loading ----
@st.cache_data(ttl=600)
def load_data():
    """Pull all complaints from Athena once, then filter in pandas."""
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
    return df


# ---- Page setup ----
st.set_page_config(page_title="NYC 311 Dashboard", layout="wide")
st.title("NYC 311 Complaint Heatmap")
st.caption("Data from NYC Open Data | Stored in S3 | Queried via Athena")

with st.spinner("Querying Athena..."):
    df_all = load_data()


# ---- Sidebar filters ----
st.sidebar.header("Filters")

boroughs = sorted(df_all["borough"].dropna().unique())
selected_boroughs = st.sidebar.multiselect("Borough", boroughs, default=boroughs)

complaint_types = sorted(df_all["complaint_type"].dropna().unique())
selected_types = st.sidebar.multiselect("Complaint type (empty = all)", complaint_types)

min_date = df_all["created_date"].min().date()
max_date = df_all["created_date"].max().date()
date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

st.sidebar.divider()
map_layer = st.sidebar.radio(
    "Map layer",
    ["3D Hexbin", "Heatmap", "Scatter by type"],
)


# ---- Apply filters ----
df = df_all[df_all["borough"].isin(selected_boroughs)].copy()
if selected_types:
    df = df[df["complaint_type"].isin(selected_types)]
if len(date_range) == 2:
    df = df[(df["date"] >= date_range[0]) & (df["date"] <= date_range[1])]


# ---- KPI metrics with deltas ----
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
            delta_str = f"{delta_pct}% vs prior half"

col1.metric("Total complaints", f"{len(df):,}", delta=delta_str, delta_color="inverse")
if len(df) > 0:
    col2.metric("Top complaint", df["complaint_type"].value_counts().index[0])
    col3.metric("Busiest borough", df["borough"].value_counts().index[0])
    col4.metric("Date span", f"{df['date'].nunique()} days")


# ---- Map with layer toggle ----
if len(df) > 0:
    view = pdk.ViewState(
        latitude=40.7128, longitude=-74.0060, zoom=10, pitch=45,
    )
    tooltip = None

    if map_layer == "3D Hexbin":
        layer = pdk.Layer(
            "HexagonLayer",
            data=df[["latitude", "longitude"]],
            get_position=["longitude", "latitude"],
            radius=200,
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
        pdk.Deck(
            initial_view_state=view,
            layers=[layer],
            tooltip=tooltip,
        ),
        use_container_width=True,
    )
else:
    st.warning("No complaints match the current filters.")


# ---- Analytics tabs ----
if len(df) > 0:
    tab1, tab2, tab3 = st.tabs(
        ["Hourly pattern", "Daily trend by borough", "Complaint breakdown"]
    )

    with tab1:
        hourly = df["hour"].value_counts().sort_index()
        hourly.index = [f"{h:02d}:00" for h in hourly.index]
        st.bar_chart(hourly, use_container_width=True)
        st.caption(
            "When does NYC complain? Noise peaks late at night, "
            "parking and blocking issues spike in the morning."
        )

    with tab2:
        daily = (
            df.groupby(["date", "borough"])
            .size()
            .reset_index(name="count")
        )
        daily_pivot = daily.pivot(
            index="date", columns="borough", values="count"
        ).fillna(0)
        st.line_chart(daily_pivot, use_container_width=True)

    with tab3:
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("By complaint type")
            st.bar_chart(df["complaint_type"].value_counts().head(15))
        with col_right:
            st.subheader("By borough")
            st.bar_chart(df["borough"].value_counts())


# ---- Download filtered data ----
if len(df) > 0:
    st.divider()
    st.download_button(
        label="Download filtered data as CSV",
        data=df.drop(columns=["hour", "date"]).to_csv(index=False),
        file_name="nyc_311_filtered.csv",
        mime="text/csv",
    )
