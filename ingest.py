import requests
import pandas as pd
import boto3
import os

# --- 1. Pull recent complaints with coordinates from the city's API ---
URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
params = {
    "$limit": 50000,
    "$where": "latitude IS NOT NULL AND created_date > '2025-06-01'",
    "$select": "unique_key,created_date,complaint_type,descriptor,borough,latitude,longitude",
    "$order": "created_date DESC",
}
print("Pulling data from NYC 311 API...")
resp = requests.get(URL, params=params, timeout=120)
resp.raise_for_status()
df = pd.DataFrame(resp.json())

# --- 2. Clean up types so Parquet stores them properly ---
df["latitude"] = df["latitude"].astype(float)
df["longitude"] = df["longitude"].astype(float)
df["created_date"] = pd.to_datetime(df["created_date"])

print(f"\nPulled {len(df)} rows")
print(f"\nTop 10 complaint types:")
print(df["complaint_type"].value_counts().head(10))
print(f"\nSample rows:")
print(df[["complaint_type", "borough", "latitude", "longitude"]].head())

# --- 3. Save locally as Parquet (columnar format, compact, Athena loves it) ---
LOCAL_PATH = "nyc_311_complaints.parquet"
df.to_parquet(LOCAL_PATH, index=False)
print(f"\nSaved to {LOCAL_PATH} ({os.path.getsize(LOCAL_PATH) / 1e6:.1f} MB)")

# --- 4. Upload to your S3 bucket ---
BUCKET = "nyc-311-dashboard-aniket"  # change this if your bucket name is different
S3_KEY = "raw/nyc_311_complaints.parquet"

s3 = boto3.client("s3")
s3.upload_file(LOCAL_PATH, BUCKET, S3_KEY)
print(f"\nUploaded to s3://{BUCKET}/{S3_KEY}")
print("Done! Verify with: aws s3 ls s3://{}/raw/".format(BUCKET))
