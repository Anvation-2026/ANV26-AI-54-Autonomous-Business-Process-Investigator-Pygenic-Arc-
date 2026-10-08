"""Reproducible synthetic business data and known-ground-truth scenarios."""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCENARIOS = {
    "BAD_DEPLOY": "New application version causes checkout errors",
    "PAYMENT_GATEWAY_OUTAGE": "One payment gateway fails while others remain healthy",
    "PRICING_ERROR": "Price update causes revenue and profit degradation",
    "CAMPAIGN_SURGE": "Demand surge increases load and processing time",
    "DATA_PIPELINE_BUG": "Metrics report a phantom drop while transactions remain healthy",
}
SCHEMA = {
    "business_metrics.csv": ["timestamp", "orders", "revenue", "profit", "error_rate", "processing_time_sec", "conversion_rate", "order_completion_rate"],
    "transactions.csv": ["txn_id", "ts", "customer_id", "amount", "payment_method", "gateway", "app_version", "status", "failure_code", "region"],
    "tickets.csv": ["ticket_id", "ts", "category", "text", "severity", "region", "app_version"],
    "logs.csv": ["ts", "service", "level", "message", "source"],
    "process_events.csv": ["ts", "event_type", "actor", "details"],
    "historical_cases.json": ["case_id", "symptoms", "root_cause", "fix", "outcome", "lessons"],
}


@dataclass(frozen=True)
class GroundTruth:
    scenario: str
    start_ts: str
    severity: str
    root_cause: str
    noisy_signal: str
    red_herring: str


def _hours(start: datetime, count: int = 30 * 24) -> list[datetime]:
    return [start + timedelta(hours=offset) for offset in range(count)]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _historical_cases() -> list[dict[str, Any]]:
    return [
        {"case_id": f"INC-{index:03d}", "symptoms": ["checkout conversion decline", "error rate increase"], "root_cause": cause, "fix": fix, "outcome": "KPI recovered after controlled verification", "lessons": "Use transaction-level evidence with lag-aware monitoring signals."}
        for index, (cause, fix) in enumerate([
            ("BAD_DEPLOY", "Rollback the affected application version and add canary checks"),
            ("PAYMENT_GATEWAY_OUTAGE", "Route traffic away from the failing gateway"),
            ("PRICING_ERROR", "Correct the price configuration and replay affected orders"),
            ("CAMPAIGN_SURGE", "Scale capacity and throttle non-critical background work"),
            ("DATA_PIPELINE_BUG", "Repair the metric transformation and backfill the window"),
        ], 1)
    ] * 3


def generate_dataset(output_dir: str | Path, scenario: str = "BAD_DEPLOY", severity: str = "high", seed: int = 7) -> GroundTruth:
    """Generate 30 days of hourly data, inject one scenario, and write ground truth."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    start = datetime(2026, 9, 9, tzinfo=timezone.utc)
    timestamps = _hours(start)
    incident_index = len(timestamps) - 30
    incident_start = timestamps[incident_index]
    baseline_metrics: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        hour_factor = 1 + 0.16 * math.sin(timestamp.hour / 24 * math.tau)
        weekend_factor = 0.82 if timestamp.weekday() >= 5 else 1
        orders = max(1, int(rng.gauss(1000 * hour_factor * weekend_factor, 42)))
        baseline_metrics.append({
            "timestamp": timestamp.isoformat(), "orders": orders, "revenue": round(orders * rng.gauss(72, 2), 2),
            "profit": round(orders * rng.gauss(19, 0.8), 2), "error_rate": round(max(0.1, rng.gauss(2.2, 0.35)), 2),
            "processing_time_sec": round(max(0.2, rng.gauss(0.42, 0.04)), 3), "conversion_rate": round(rng.gauss(8.2, 0.25), 2),
            "order_completion_rate": round(rng.gauss(94.8, 0.7), 2),
        })
    gateways = ["stripe", "adyen", "razorpay"]
    regions = ["us-east", "eu-west", "ap-south"]
    transactions: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    process_events = [
        {"ts": (incident_start - timedelta(minutes=25)).isoformat(), "event_type": "deploy", "actor": "release-bot", "details": "red-herring deploy: documentation-only change"},
        {"ts": (incident_start - timedelta(minutes=18)).isoformat(), "event_type": "config_change", "actor": "ops-user", "details": "red-herring: dashboard label change"},
    ]
    for index, row in enumerate(baseline_metrics):
        if index >= incident_index:
            _inject_metrics(row, scenario, severity)
        gateway = gateways[index % len(gateways)]
        status = "success"
        failure_code = ""
        app_version = "v1.4.2"
        if index >= incident_index and scenario == "BAD_DEPLOY":
            app_version, status, failure_code = "v1.5.0", "failed", "CHECKOUT_500"
        elif index >= incident_index and scenario == "PAYMENT_GATEWAY_OUTAGE" and gateway == "stripe":
            status, failure_code = "failed", "GATEWAY_TIMEOUT"
        elif index >= incident_index and scenario == "DATA_PIPELINE_BUG":
            status = "success"
        transactions.append({"txn_id": f"TX-{index:06d}", "ts": row["timestamp"], "customer_id": f"C-{index % 500:04d}", "amount": round(rng.uniform(18, 240), 2), "payment_method": "card", "gateway": gateway, "app_version": app_version, "status": status, "failure_code": failure_code, "region": regions[index % len(regions)]})
        if index >= incident_index and index % 7 == 0:
            tickets.append({"ticket_id": f"T-{index:05d}", "ts": row["timestamp"], "category": "checkout", "text": "Checkout failed or transaction timed out", "severity": "high", "region": regions[index % len(regions)], "app_version": app_version})
            logs.append({"ts": row["timestamp"], "service": "checkout-service", "level": "ERROR", "message": "order_failed payment timeout", "source": "app"})
    # Every scenario has a lagging healthy signal and a plausible but unrelated event.
    logs.append({"ts": (incident_start + timedelta(minutes=12)).isoformat(), "service": "monitoring", "level": "INFO", "message": "ALL SYSTEMS HEALTHY (monitoring window is delayed)", "source": "monitoring"})
    process_events.append({"ts": (incident_start - timedelta(minutes=9)).isoformat(), "event_type": "campaign_start", "actor": "marketing-bot", "details": "red-herring campaign started in a non-affected segment"})
    for row in baseline_metrics:
        for field in ("profit", "processing_time_sec", "conversion_rate", "order_completion_rate"):
            if rng.random() < 0.05:
                row[field] = ""
    _write_csv(destination / "business_metrics.csv", baseline_metrics, SCHEMA["business_metrics.csv"])
    _write_csv(destination / "transactions.csv", transactions, SCHEMA["transactions.csv"])
    _write_csv(destination / "tickets.csv", tickets, SCHEMA["tickets.csv"])
    _write_csv(destination / "logs.csv", logs, SCHEMA["logs.csv"])
    _write_csv(destination / "process_events.csv", process_events, SCHEMA["process_events.csv"])
    (destination / "historical_cases.json").write_text(json.dumps(_historical_cases(), indent=2), encoding="utf-8")
    truth = GroundTruth(scenario, incident_start.isoformat(), severity, scenario, "lagging monitoring log says all systems healthy", "unrelated deploy/config/campaign event")
    (destination / "ground_truth.json").write_text(json.dumps(asdict(truth), indent=2), encoding="utf-8")
    return truth


def _inject_metrics(row: dict[str, Any], scenario: str, severity: str) -> None:
    multiplier = 1.0 if severity == "high" else 0.55
    if scenario == "BAD_DEPLOY":
        row["error_rate"] = round(14 * multiplier, 2); row["order_completion_rate"] = round(62 + 10 * (1 - multiplier), 2); row["processing_time_sec"] = round(1.4 * multiplier + 0.42, 3)
    elif scenario == "PAYMENT_GATEWAY_OUTAGE":
        row["error_rate"] = round(11 * multiplier, 2); row["order_completion_rate"] = round(65 + 8 * (1 - multiplier), 2); row["processing_time_sec"] = round(1.25 * multiplier + 0.42, 3)
    elif scenario == "PRICING_ERROR":
        row["orders"] = int(row["orders"] * 1.18); row["profit"] = round(float(row["profit"]) * (0.45 + 0.25 * (1 - multiplier)), 2); row["revenue"] = round(float(row["revenue"]) * 0.72, 2)
    elif scenario == "CAMPAIGN_SURGE":
        row["orders"] = int(row["orders"] * (1.45 + 0.15 * multiplier)); row["processing_time_sec"] = round(0.9 * multiplier + 0.42, 3); row["error_rate"] = round(5 * multiplier, 2)
    elif scenario == "DATA_PIPELINE_BUG":
        row["order_completion_rate"] = round(61 + 8 * (1 - multiplier), 2)

