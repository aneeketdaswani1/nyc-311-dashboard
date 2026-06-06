import streamlit as st
import pandas as pd
import pydeck as pdk
from pyathena import connect

# ---- Configuration ----
BUCKET = "nyc-311-dashboard-aniket"          # your S3 bucket
S3_STAGING = f"s3://{BUCKET}/athena-results/"
REGION = "us-east-1"
DATABASE = "nyc311"


# ---- Load data from Athena (cached so it only queries once) ----
@st.cache_data(ttl=600)
def load_data():
    """Pull all complaints from Athena. 50K rows loads in a few seconds."""
    conn = connect(s3_staging_dir=S3_STAGING, region_name=REGION)
    df = pd.read_sql(
        f"""SELECT latitude, longitude, complaint_type, descriptor,
                   borough, created_date
            FROM {DATABASE}.complaints""",
        conn,
    )
    df["created_date"] = pd.to_datetime(df["created_date"])
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
selected_types = st.sidebar.multiselect(
    "Complaint type (empty = all)", complaint_types
)

min_date = df_all["created_date"].min().date()
max_date = df_all["created_date"].max().date()
date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)


# ---- Apply filters in pandas (instant, no re-query) ----
df = df_all[df_all["borough"].isin(selected_boroughs)].copy()

if selected_types:
    df = df[df["complaint_type"].isin(selected_types)]

if len(date_range) == 2:
    df = df[
        (df["created_date"].dt.date >= date_range[0])
        & (df["created_date"].dt.date <= date_range[1])
    ]


# ---- Summary metrics ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total complaints", f"{len(df):,}")

if len(df) > 0:
    col2.metric("Top complaint", df["complaint_type"].value_counts().index[0])
    col3.metric("Busiest borough", df["borough"].value_counts().index[0])
    col4.metric(
        "Date span",
        f"{df['created_date'].dt.date.nunique()} days",
    )


# ---- 3D Hexbin map ----
if len(df) > 0:
    st.pydeck_chart(
        pdk.Deck(
            initial_view_state=pdk.ViewState(
                latitude=40.7128,
                longitude=-74.0060,
                zoom=10,
                pitch=45,
            ),
            layers=[
                pdk.Layer(
                    "HexagonLayer",
                    data=df[["latitude", "longitude"]],
                    get_position=["longitude", "latitude"],
                    radius=200,
                    elevation_scale=4,
                    elevation_range=[0, 1000],
                    pickable=True,
                    extruded=True,
                    coverage=1,
                ),
            ],
        ),
        use_container_width=True,
    )
else:
    st.warning("No complaints match the current filters.")


# ---- Breakdown charts ----
if len(df) > 0:
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("By complaint type")
        st.bar_chart(df["complaint_type"].value_counts().head(15))

    with col_right:
        st.subheader("By borough")
        st.bar_chart(df["borough"].value_counts())
