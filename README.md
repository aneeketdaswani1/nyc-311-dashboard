# NYC 311 Complaint Heatmap

A cloud-native geospatial dashboard that visualizes 50,000+ NYC 311 service complaints as an interactive 3D heatmap. Built on AWS with a full data pipeline from ingestion to deployment.

![NYC 311 Dashboard](screenshots/dashboard.png)
<!-- Replace with your actual screenshot -->

## Live Demo

🔗 [**View the live dashboard**](YOUR_ECS_URL_HERE)
<!-- Replace with your ECS Express Mode URL -->

## Architecture

```
NYC 311 API → Ingest (Python/boto3) → S3 (Parquet) → Athena (SQL) → Streamlit + pydeck → ECS Fargate
```

| Component | Service | Purpose |
|-----------|---------|---------|
| Data Source | NYC Open Data SODA API | 50K+ geocoded complaint records |
| Storage | Amazon S3 | Raw Parquet files, partitioned |
| Query Engine | Amazon Athena | Serverless SQL over S3 |
| Dashboard | Streamlit + pydeck | Interactive 3D map + analytics |
| Auth | IAM Identity Center | SSO-based CLI credentials |
| Container | Docker + Amazon ECR | Image registry |
| Deployment | ECS Fargate (Express Mode) | Auto-scaling, HTTPS, ALB |

## Features

- **3D Hexbin Map** — density columns rising from NYC, colored teal-to-red by complaint volume
- **Layer Toggle** — switch between 3D hexbin, flat heatmap, and scatter plot colored by complaint type
- **Interactive Filters** — borough, complaint type, and date range with instant pandas filtering
- **Hourly Pattern Chart** — reveals when NYC complains most (noise peaks at night, parking in the morning)
- **Daily Trend by Borough** — time series showing complaint volume per borough over the date range
- **KPI Metrics with Deltas** — total complaints, top type, busiest borough, with trend arrows vs prior period
- **CSV Export** — one-click download of filtered data

## Tech Stack

**Data & ML:** Python, pandas, PyArrow, PyAthena

**Visualization:** Streamlit, pydeck (deck.gl), HexagonLayer / HeatmapLayer / ScatterplotLayer

**Cloud (AWS):** S3, Athena, IAM Identity Center, ECR, ECS Fargate, CloudWatch

**DevOps:** Docker, AWS CLI

## Quick Start

### Prerequisites
- AWS account with IAM Identity Center configured
- Python 3.11+
- Docker
- AWS CLI v2

### 1. Clone and install
```bash
git clone https://github.com/aneeketdaswani1/nyc-311-dashboard.git
cd nyc-311-dashboard
pip install -r requirements.txt
```

### 2. Configure AWS credentials
```bash
aws configure sso  # follow the prompts
export AWS_PROFILE=nyc311
```

### 3. Ingest data
```bash
python ingest.py
```
Pulls 50K recent complaints from the NYC 311 API, saves as Parquet, and uploads to S3.

### 4. Set up Athena
Run these in the Athena console:
```sql
CREATE DATABASE nyc311;

CREATE EXTERNAL TABLE nyc311.complaints (
    unique_key STRING,
    created_date TIMESTAMP,
    complaint_type STRING,
    descriptor STRING,
    borough STRING,
    latitude DOUBLE,
    longitude DOUBLE
)
STORED AS PARQUET
LOCATION 's3://YOUR-BUCKET/raw/'
TBLPROPERTIES ('parquet.compress'='SNAPPY');
```

### 5. Run locally
```bash
streamlit run app.py
```

### 6. Deploy to AWS
```bash
docker buildx build --platform linux/amd64 --load -t nyc-311-dashboard .
# Tag, push to ECR, deploy via ECS Express Mode
```

## Project Structure
```
├── app.py              # Streamlit dashboard (map, charts, filters)
├── ingest.py           # Data pipeline: API → Parquet → S3
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container config for ECS deployment
└── README.md
```

## Screenshots

<!-- Add your screenshots here -->
<!-- Suggested: 3D hexbin view, heatmap view, scatter view, hourly chart -->

## License

MIT
