"""
NYC 311 Data Ingest — v2
=========================
Pulls 200K+ rows with resolution time, zip code, and status fields.
Paginates through the SODA API in 50K batches.
"""

import requests
import pandas as pd
import boto3
import os

URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
BUCKET = "nyc-311-dashboard-aniket"
S3_KEY = "raw/nyc_311_complaints.parquet"
BATCH_SIZE = 50000
TARGET_ROWS = 200000

# ---- Pull data in batches ----
all_rows = []
offset = 0

print(f"Pulling up to {TARGET_ROWS:,} rows from NYC 311 API...\n")

while len(all_rows) < TARGET_ROWS:
    params = {
        "$limit": BATCH_SIZE,
        "$offset": offset,
        "$where": "latitude IS NOT NULL",
        "$select": (
            "unique_key,created_date,closed_date,complaint_type,"
            "descriptor,borough,latitude,longitude,incident_zip,status"
        ),
        "$order": "created_date DESC",
    }
    print(f"  Batch {offset // BATCH_SIZE + 1}: fetching rows {offset}–{offset + BATCH_SIZE}...")
    resp = requests.get(URL, params=params, timeout=120)
    resp.raise_for_status()
    rows = resp.json()

    if not rows:
        break
    all_rows.extend(rows)
    offset += BATCH_SIZE

    if len(rows) < BATCH_SIZE:
        break  # last page

df = pd.DataFrame(all_rows)

# ---- Clean types ----
df["latitude"] = df["latitude"].astype(float)
df["longitude"] = df["longitude"].astype(float)
df["created_date"] = pd.to_datetime(df["created_date"])
df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")

print(f"\nPulled {len(df):,} rows")
print(f"Date range: {df['created_date'].min().date()} to {df['created_date'].max().date()}")
print(f"Boroughs: {df['borough'].nunique()}")
print(f"Zip codes: {df['incident_zip'].nunique()}")
print(f"Complaints with resolution: {df['closed_date'].notna().sum():,}")
print(f"\nTop 10 complaint types:")
print(df["complaint_type"].value_counts().head(10))

# ---- Save as Parquet ----
LOCAL_PATH = "nyc_311_complaints.parquet"
df.to_parquet(LOCAL_PATH, index=False)
print(f"\nSaved to {LOCAL_PATH} ({os.path.getsize(LOCAL_PATH) / 1e6:.1f} MB)")

# ---- Upload to S3 ----
s3 = boto3.client("s3")
s3.upload_file(LOCAL_PATH, BUCKET, S3_KEY)
print(f"Uploaded to s3://{BUCKET}/{S3_KEY}")
print("Done!")
