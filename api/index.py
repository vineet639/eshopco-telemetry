import json
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(title="eShopCo Telemetry API")

# --------------------------------------------------
# CORS: always send the headers, and answer preflight
# --------------------------------------------------

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


@app.middleware("http")
async def add_cors(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=CORS_HEADERS)
    response = await call_next(request)
    response.headers.update(CORS_HEADERS)
    return response


# --------------------------------------------------
# Telemetry data file (bundled via includeFiles)
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "telemetry.json"
if not DATA_FILE.exists():
    DATA_FILE = Path.cwd() / "telemetry.json"


class MetricsRequest(BaseModel):
    regions: list[str]
    threshold_ms: float = 180


def load_records():
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            records = json.load(file)
        if not isinstance(records, list):
            raise ValueError("Expected a JSON array of telemetry records.")
        return records
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to load telemetry data: {exc}",
        ) from exc


# --------------------------------------------------
# 95th percentile (linear interpolation)
# --------------------------------------------------

def percentile95(values):
    if not values:
        raise ValueError("Cannot calculate percentile of empty data.")
    values = sorted(values)
    position = (len(values) - 1) * 0.95
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.get("/")
def health():
    return {"status": "ok", "usage": "POST {regions: [...], threshold_ms: N}"}


@app.post("/")
def calculate_metrics(request: MetricsRequest):
    records = load_records()
    result = {}

    for region in request.regions:
        matching = [
            row for row in records
            if str(row.get("region", "")).lower() == region.lower()
        ]

        if not matching:
            continue  # skip unknown regions instead of failing the request

        try:
            latencies = [float(row["latency_ms"]) for row in matching]
            uptimes = [float(row["uptime_pct"]) for row in matching]
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid telemetry record: {exc}",
            ) from exc

        result[region] = {
            "avg_latency": round(sum(latencies) / len(latencies), 4),
            "p95_latency": round(percentile95(latencies), 4),
            "avg_uptime": round(sum(uptimes) / len(uptimes), 4),
            "breaches": sum(l > request.threshold_ms for l in latencies),
        }

    return result
