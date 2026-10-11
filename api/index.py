
import json
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(title="eShopCo Telemetry API")

# --------------------------------------------------
# CORS configuration
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Telemetry data file
# --------------------------------------------------

DATA_FILE = Path(__file__).resolve().parent.parent / "telemetry.json"


class MetricsRequest(BaseModel):
    regions: list[str]
    threshold_ms: float = 180


# --------------------------------------------------
# Load telemetry records
# --------------------------------------------------

def load_records():
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            records = json.load(file)

        if not isinstance(records, list):
            raise ValueError(
                "Expected a JSON array of telemetry records."
            )

        return records

    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to load telemetry data: {exc}",
        ) from exc


# --------------------------------------------------
# Calculate 95th percentile using linear interpolation
# --------------------------------------------------

def percentile95(values):
    if not values:
        raise ValueError("Cannot calculate percentile of empty data.")

    values = sorted(values)

    position = (len(values) - 1) * 0.95
    lower = math.floor(position)
    upper = math.ceil(position)

    return values[lower] + (
        values[upper] - values[lower]
    ) * (position - lower)


# --------------------------------------------------
# POST endpoint
# --------------------------------------------------

@app.post("/")
def calculate_metrics(request: MetricsRequest):
    records = load_records()
    result = {}

    for region in request.regions:
        matching = [
            row
            for row in records
            if str(row.get("region", "")).lower()
            == region.lower()
        ]

        if not matching:
            raise HTTPException(
                status_code=404,
                detail=f"No records found for region: {region}",
            )

        try:
            latencies = [
                float(row["latency_ms"])
                for row in matching
            ]

            uptimes = [
                float(row["uptime_pct"])
                for row in matching
            ]

        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid telemetry record: {exc}",
            ) from exc

        result[region] = {
            "avg_latency": round(
                sum(latencies) / len(latencies), 2
            ),
            "p95_latency": round(
                percentile95(latencies), 2
            ),
            "avg_uptime": round(
                sum(uptimes) / len(uptimes), 4
            ),
            "breaches": sum(
                latency > request.threshold_ms
                for latency in latencies
            ),
        }

    return result
