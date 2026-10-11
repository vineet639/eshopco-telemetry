
import json
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="eShopCo Telemetry API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

DATA_FILE = Path(__file__).resolve().parent.parent / "telemetry.json"


class MetricsRequest(BaseModel):
    regions: list[str]
    threshold_ms: float = 180


def load_records():
    with DATA_FILE.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError("Expected a JSON array of telemetry records.")

    return records


def percentile95(values):
    values = sorted(values)
    position = (len(values) - 1) * 0.95
    lower = math.floor(position)
    upper = math.ceil(position)

    return values[lower] + (
        values[upper] - values[lower]
    ) * (position - lower)


@app.post("/")
def calculate_metrics(request: MetricsRequest):
    try:
        records = load_records()
        result = {}

        for region in request.regions:
            matching = [
                row for row in records
                if str(row.get("region", "")).lower()
                == region.lower()
            ]

            if not matching:
                raise HTTPException(
                    status_code=404,
                    detail=f"No records found for region: {region}"
                )

            latencies = [
                float(row["latency_ms"]) for row in matching
            ]

            uptimes = [
                float(row["uptime_pct"]) for row in matching
            ]

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

    except HTTPException:
        raise
    except (OSError, json.JSONDecodeError, KeyError,
            ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to process telemetry data: {exc}"
        ) from exc
