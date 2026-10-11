
import csv
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="eShopCo Telemetry API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class MetricsRequest(BaseModel):
    regions: list[str]
    threshold_ms: float = Field(default=180)


def load_records():
    records = []

    for path in sorted(DATA_DIR.rglob("*.csv")):
        with path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            for row in csv.DictReader(file):
                records.append(row)

    if not records:
        raise RuntimeError(
            "No CSV telemetry records found in data/"
        )

    return records


def get_value(row, candidates):
    normalized = {
        key.strip().lower().replace(" ", "_"): value
        for key, value in row.items()
        if key is not None
    }

    for key in candidates:
        value = normalized.get(key)
        if value is not None and str(value).strip() != "":
            return value

    raise ValueError(
        f"Missing required column. Expected one of: {candidates}"
    )


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
                if str(get_value(
                    row, ["region", "region_name"]
                )).strip().lower() == region.strip().lower()
            ]

            if not matching:
                raise HTTPException(
                    status_code=404,
                    detail=f"No records found for region: {region}"
                )

            latencies = [
                float(get_value(
                    row,
                    ["latency_ms", "latency", "response_time_ms"]
                ))
                for row in matching
            ]

            uptimes = [
                float(get_value(
                    row, ["uptime", "uptime_pct", "uptime_percent"]
                ))
                for row in matching
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
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=500, detail=str(exc)
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read telemetry data."
        ) from exc
