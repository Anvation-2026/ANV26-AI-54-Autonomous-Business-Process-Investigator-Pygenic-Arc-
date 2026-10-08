"""Pygenic Arc: explainable business-process investigation MVP.

The core pipeline is intentionally deterministic and runnable with Python's
standard library. Optional production integrations can replace the providers
without changing the API contract.
"""

from __future__ import annotations

import json
import math
import mimetypes
import os
import statistics
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agents.graph import run_investigation_graph
from rag import retrieve_cases

ROOT = Path(__file__).parent
DATA = ROOT / "data"
INCOMING = ROOT / "incoming"
INVESTIGATION_ID = "INV-2026-1008-001"
BACKEND_VERSION = "2026.10.08-strict"
CHECKPOINTS = ROOT / "checkpoints.json"
REVIEWS: dict[str, dict] = {}
UPLOADS: dict[str, dict] = {}
MONITOR_STATE = {
    "running": False,
    "source": str(INCOMING),
    "files_seen": 0,
    "last_file": None,
    "last_event": None,
    "last_error": None,
    "anomaly_detected": False,
    "last_checked_at": None,
}


def _load_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


_load_env()
INCOMING.mkdir(exist_ok=True)


def ingest_upload(filename: str, content: str) -> dict:
    if not filename or not isinstance(content, str) or not content.strip():
        raise ValueError("filename and text content are required")
    if not filename.lower().endswith((".csv", ".json")):
        raise ValueError("Only CSV and JSON files are supported")
    try:
        parsed = json.loads(content) if filename.lower().endswith(".json") else content.splitlines()
    except json.JSONDecodeError as error:
        raise ValueError("The JSON file is invalid") from error
    if filename.lower().endswith(".csv"):
        import csv
        from io import StringIO
        rows = list(csv.DictReader(StringIO(content)))
        if not rows or not rows[0]:
            raise ValueError("CSV must contain a header row and at least one data row")
        record_count = len(rows)
        file_type = "CSV"
    elif isinstance(parsed, list):
        if not parsed or not all(isinstance(row, dict) for row in parsed):
            raise ValueError("JSON must contain a non-empty array of objects")
        record_count = len(parsed)
        file_type = "JSON"
    elif isinstance(parsed, dict):
        record_count = 1
        file_type = "JSON"
    else:
        raise ValueError("JSON must contain an object or an array of objects")
    UPLOADS[filename] = {
        "type": file_type,
        "records": record_count,
        "content": content,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"accepted": True, "filename": filename, "type": file_type, "records": record_count}


def monitor_loop() -> None:
    seen: dict[str, int] = {}
    MONITOR_STATE["running"] = True
    while True:
        try:
            MONITOR_STATE["last_checked_at"] = datetime.now(timezone.utc).isoformat()
            for path in INCOMING.iterdir():
                if not path.is_file() or path.suffix.lower() not in (".csv", ".json"):
                    continue
                modified = path.stat().st_mtime_ns
                if seen.get(path.name) == modified:
                    continue
                seen[path.name] = modified
                try:
                    result = ingest_upload(path.name, path.read_text(encoding="utf-8"))
                    report = investigate()
                    MONITOR_STATE.update({
                        "files_seen": len(seen),
                        "last_file": path.name,
                        "last_event": {"type": "file_ingested", **result, "at": datetime.now(timezone.utc).isoformat()},
                        "last_error": None,
                        "anomaly_detected": bool(report.get("anomalies")),
                    })
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                    MONITOR_STATE.update({
                        "files_seen": len(seen),
                        "last_file": path.name,
                        "last_error": {"file": path.name, "message": str(error), "at": datetime.now(timezone.utc).isoformat()},
                    })
        except OSError as error:
            MONITOR_STATE["last_error"] = {"message": str(error), "at": datetime.now(timezone.utc).isoformat()}
        time.sleep(2)


def pct_change(current: float, baseline: float) -> float:
    return round((current - baseline) / baseline * 100, 1)


def _csv(name: str) -> list[dict[str, str]]:
    import csv

    path = DATA / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _cases() -> list[dict]:
    path = DATA / "historical_cases.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _uploaded_records() -> list[dict]:
    import csv
    from io import StringIO

    records = []
    for filename, item in UPLOADS.items():
        content = item["content"]
        if item["type"] == "JSON":
            parsed = json.loads(content)
            rows = parsed if isinstance(parsed, list) else [parsed]
        else:
            rows = list(csv.DictReader(StringIO(content)))
        for row in rows:
            records.append({"source": filename, "data": row if isinstance(row, dict) else {"value": row}})
    return records


def uploaded_investigation() -> dict:
    records = _uploaded_records()
    if not records:
        return {"id": INVESTIGATION_ID, "ready": False, "status": "insufficient_evidence", "uploads": [], "message": "Uploaded files contain no readable records."}
    numeric_values: dict[str, list[float]] = {}
    for record in records:
        for key, value in record["data"].items():
            try:
                numeric_values.setdefault(str(key), []).append(float(value))
            except (TypeError, ValueError):
                continue
    anomalies = []
    for field, field_values in numeric_values.items():
        if len(field_values) < 2:
            continue
        mean = statistics.mean(field_values)
        deviation = statistics.pstdev(field_values)
        if deviation == 0:
            continue
        index = max(range(len(field_values)), key=lambda position: abs(field_values[position] - mean))
        value = field_values[index]
        z_score = abs(value - mean) / deviation
        score = min(99, round(50 + z_score * 20))
        severity = "HIGH" if score >= 80 else "MEDIUM" if score >= 65 else "LOW"
        source = next((record["source"] for record in records if str(field) in record["data"] and str(record["data"][field]) == str(value)), "uploaded data")
        anomalies.append({
            "id": f"ANOM-{len(anomalies) + 1:03d}",
            "metric": field,
            "value": round(value, 4),
            "average": round(mean, 4),
            "standard_deviation": round(deviation, 4),
            "score": score,
            "severity": severity,
            "source": source,
            "description": f"{field} reached {value:g}, compared with an average of {mean:.2f}.",
        })
    anomalies.sort(key=lambda item: item["score"], reverse=True)
    numeric_values = {key: values for key, values in numeric_values.items() if values}
    if not numeric_values:
        return {"id": INVESTIGATION_ID, "ready": False, "status": "insufficient_evidence", "uploads": [{"name": name, "type": item["type"], "records": item["records"]} for name, item in UPLOADS.items()], "message": "No numeric fields were found. Upload measurable metrics, transaction values, rates, durations, counts, or other numeric evidence."}
    if not anomalies:
        return {
            "id": INVESTIGATION_ID,
            "ready": False,
            "status": "insufficient_evidence",
            "uploads": [{"name": name, "type": item["type"], "records": item["records"]} for name, item in UPLOADS.items()],
            "message": "No statistically detectable anomaly was found in the uploaded numeric fields.",
        }
    metric = max(numeric_values, key=lambda key: len(numeric_values[key]))
    values = numeric_values[metric]
    low, high = min(values), max(values)
    average = statistics.mean(values)
    spread = pct_change(high, low) if low else 0
    evidence = []
    for index, (filename, item) in enumerate(UPLOADS.items(), 1):
        fields = sorted({str(key) for record in records if record["source"] == filename for key in record["data"]})
        evidence.append({
            "id": f"E-{index:03d}",
            "source": filename,
            "timestamp": item.get("added_at", datetime.now(timezone.utc).isoformat()),
            "description": f"Uploaded {item['records']} records from {filename}; fields: {', '.join(fields[:8]) or 'unstructured values'}.",
            "severity": "medium",
            "relevance_score": round(max(0.5, 1 - (index - 1) * 0.08), 2),
            "supports": ["uploaded_data_pattern"],
        })
    causes = [
        {"id": "data_pattern", "name": "Observed data pattern", "score": 72, "evidence_ids": [item["id"] for item in evidence[:3]], "explanation": f"The uploaded records show a {metric} range from {low:g} to {high:g}; this is the strongest measurable signal in the supplied data.", "agent": "Hybrid RCA Agent"},
        {"id": "process_or_system", "name": "Process or system issue", "score": 51, "evidence_ids": [item["id"] for item in evidence], "explanation": "The files contain operational records, but no causal system logs were supplied to distinguish process, application, or provider causes.", "agent": "Hybrid RCA Agent"},
        {"id": "data_quality", "name": "Data quality or sampling issue", "score": 34, "evidence_ids": [item["id"] for item in evidence], "explanation": "A broader baseline, timestamps, and status labels are needed to confirm whether the observed spread is an anomaly or normal variation.", "agent": "Hybrid RCA Agent"},
    ]
    anomaly_description = f"Uploaded data contains {len(records)} records and a {metric} range from {low:g} to {high:g}."
    retrieval_query = " ".join([
        anomaly_description,
        metric,
        " ".join(item["description"] for item in evidence),
    ])
    retrieval = retrieve_cases(DATA / "historical_cases.json", retrieval_query, limit=3)
    historical_cases = retrieval["matches"]
    agents = [
        {"name": "Anomaly Detection Agent", "input": "Uploaded numeric fields", "output": f"Compared {metric} values using mean, population standard deviation, and deviation score."},
        {"name": "Evidence Collection Agent", "input": "Uploaded CSV/JSON records", "output": f"Collected {len(evidence)} source-level evidence records and linked them to uploaded files."},
        {"name": "Conflict Analysis Agent", "input": "Evidence records", "output": f"Checked for contradictory signals; {len([item for item in evidence if item.get('conflict')])} explicit conflicts were found."},
        {"name": "Hybrid RCA Agent", "input": "Anomaly + evidence + alternatives", "output": f"Ranked {len(causes)} plausible causes using evidence coverage and data limitations."},
        {"name": "RAG Memory Agent", "input": "Current anomaly, evidence, and metric query", "output": f"Retrieved {len(historical_cases)} historical records with TF-IDF cosine similarity."},
        {"name": "Solution Planner Agent", "input": "Top cause + evidence limitations", "output": "Generated verification-first actions; no production remediation is executed."},
        {"name": "Human Verification Gate", "input": "Ranked diagnosis + proposed actions", "output": "Waiting for explicit human approval, modification, or rejection."},
    ]
    return {
        "id": INVESTIGATION_ID,
        "ready": True,
        "anomalies": anomalies,
        "selected_anomaly": None,
        "anomaly": {"id": "ANOM-UPLOAD", "metric": metric, "timestamp": datetime.now(timezone.utc).isoformat(), "baseline": round(low, 2), "current": round(high, 2), "deviation_percent": round(spread, 1), "anomaly_score": round(min(0.99, abs(spread) / 100), 2), "severity": "HIGH" if spread >= 20 else "MEDIUM", "description": f"Uploaded data contains {len(records)} records and a {metric} range from {low:g} to {high:g} (average {average:.2f})."},
        "baseline": {metric: round(low, 2)}, "current": {metric: round(high, 2)}, "evidence": evidence, "conflicts": [],
        "causes": causes, "historical_cases": historical_cases,         "history": {"source": "backend/data/historical_cases.json", "match_found": bool(historical_cases), "mode": "TF-IDF cosine retrieval" if historical_cases else "no similar memory retrieved", "stored_cases": len(_cases()), "retrieval": retrieval["retrieval"]},
        "uploads": [{"name": name, "type": item["type"], "records": item["records"]} for name, item in UPLOADS.items()],
        "solution": {"root_cause": causes[0]["name"], "plan": ["Add baseline and timestamp fields to the uploaded dataset.", "Validate the observed pattern against order, payment, and support records.", "Review the strongest evidence with an e-commerce operator.", "Re-run the investigation after the missing context is supplied."], "expected_outcome": {metric: {"current": f"{high:g}", "projected": "validated after baseline comparison"}}, "disclaimer": "This recommendation is based only on the uploaded files; no production action is executed."},
        "verification": {"status": "pending", "decision": None, "notes": "Human review is required."},
        "method": {"agents": [agent["name"] for agent in agents], "agent_details": agents, "ranking_label": "Confidence / Evidence Score (not calibrated probability)", "rag": retrieval["retrieval"]},
        "pipeline": agents,
    }


def detect_anomaly() -> dict:
    metrics = _csv("business_metrics.csv")
    normal = [row for row in metrics if row["phase"] == "baseline"]
    current = next(row for row in metrics if row["phase"] == "incident")
    baseline_completion = statistics.mean(float(row["order_completion_rate"]) for row in normal)
    current_completion = float(current["order_completion_rate"])
    deviation = pct_change(current_completion, baseline_completion)
    return {
        "id": "ANOM-001",
        "metric": "order_completion_rate",
        "timestamp": current["timestamp"],
        "baseline": round(baseline_completion, 1),
        "current": current_completion,
        "deviation_percent": deviation,
        "anomaly_score": round(min(0.99, abs(deviation) / 40), 2),
        "severity": "HIGH" if abs(deviation) >= 20 else "MEDIUM",
        "description": f"Order completion fell {abs(deviation):.1f}% from the historical baseline.",
    }


def investigate() -> dict:
    if not UPLOADS:
        return {"id": INVESTIGATION_ID, "ready": False, "status": "insufficient_evidence", "uploads": [], "message": "Upload a CSV or JSON file to start the investigation."}
    # The legacy report shape remains the HTTP contract; the compiled agent
    # graph enriches it with messages, planner steps, and durable checkpoints.
    return run_investigation_graph(uploaded_investigation(), CHECKPOINTS)


def diagnose_case(case_id: str, failure_time: str, description: str) -> dict:
    report = investigate()
    if not report.get("ready"):
        return {
            "case_id": case_id,
            "failure_time": failure_time,
            "description": description,
            "status": "insufficient_evidence",
            "root_cause": None,
            "confidence": 0,
            "supporting_evidence": [],
            "recommended_actions": ["Upload CSV or JSON telemetry, metrics, transactions, tickets, or logs before running RCA."],
            "explanation": "The diagnosis request was accepted, but no investigation evidence is currently loaded.",
        }
    top_cause = report["causes"][0] if report.get("causes") else {}
    return {
        "case_id": case_id,
        "failure_time": failure_time,
        "description": description,
        "status": "diagnosed",
        "root_cause": top_cause.get("name"),
        "confidence": top_cause.get("score", 0),
        "confidence_label": "Confidence / Evidence Score (not calibrated probability)",
        "supporting_evidence": [
            item for item in report.get("evidence", [])
            if item["id"] in top_cause.get("evidence_ids", [])
        ],
        "ranked_causes": report.get("causes", []),
        "recommended_actions": report.get("solution", {}).get("plan", []),
        "historical_matches": report.get("historical_cases", []),
        "conflicting_signals": report.get("conflicts", []),
        "explanation": top_cause.get("explanation", "No explanation was produced."),
        "investigation_id": report.get("id"),
    }


def graph_payload(report: dict) -> dict:
    anomaly = report["anomaly"]
    nodes = [{"id": "anomaly", "label": f"{anomaly['metric']} {anomaly['deviation_percent']}%", "type": "anomaly"}]
    edges = []
    for evidence in report["evidence"]:
        nodes.append({"id": evidence["id"], "label": evidence["description"], "type": "evidence"})
        edges.append({"source": "anomaly", "target": evidence["id"]})
    for cause in report["causes"]:
        nodes.append({"id": cause["id"], "label": cause["name"], "type": "cause"})
        for evidence_id in cause["evidence_ids"]:
            edges.append({"source": evidence_id, "target": cause["id"]})
    nodes.append({"id": "solution", "label": report["solution"]["plan"][0], "type": "solution"})
    edges.append({"source": report["causes"][0]["id"], "target": "solution"})
    return {"nodes": nodes, "edges": edges}


def final_report(report: dict) -> dict:
    review = REVIEWS.get(report["id"], report["verification"])
    return {"title": "Pygenic Arc Investigation Report", "generated_at": datetime.now(timezone.utc).isoformat(), "anomaly_summary": report["anomaly"], "evidence_trail": report["evidence"], "conflicting_evidence": report["conflicts"], "ranked_causes": report["causes"], "historical_cases": report["historical_cases"], "recommended_solution": report["solution"], "human_verification": review}


def gemini_answer(question: str, context: dict) -> tuple[str, bool]:
    """Ask Gemini with investigation-only context."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    prompt = (
        "You are the Pygenic Arc e-commerce investigation assistant. Only answer questions strictly about the supplied investigation context. "
        "Allowed topics: anomaly summary, evidence trail (cite evidence IDs), ranked probable causes, the selected anomaly, the recommended solution steps, human verification status/decision, the final report, and the investigation graph. "
        "If the question is outside these topics, reply exactly: 'I can only answer questions about this investigation (anomaly, evidence, causes, solution, verification, or report).'. "
        "Be concise, cite evidence IDs when relevant, and do not invent facts, external data, or confidence scores beyond what is in the context. "
        f"Question: {question}\nInvestigation context:\n{json.dumps(context, separators=(',', ':'))}"
    )
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?" + urllib.parse.urlencode({"key": api_key})
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        return (text, True)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Gemini request failed: {error}") from error


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _require_report(self) -> dict | None:
        report = investigate()
        if not report.get("ready"):
            self._send(422, report)
            return None
        return report

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send(200, {"ok": True, "service": "pygenic-arc-backend", "version": BACKEND_VERSION, "uploads": len(UPLOADS), "monitor": MONITOR_STATE})
            return
        if path == "/api/monitor/status":
            self._send(200, MONITOR_STATE)
            return
        report = investigate()
        if path == "/api/investigate" or path == f"/api/investigation/{INVESTIGATION_ID}/report":
            if not report.get("ready"):
                self._send(422, report)
            else:
                self._send(200, final_report(report) if path.endswith("/report") else report)
        elif path == f"/api/investigation/{INVESTIGATION_ID}/evidence":
            if report.get("ready"):
                self._send(200, report["evidence"])
            else:
                self._send(422, report)
        elif path == f"/api/investigation/{INVESTIGATION_ID}/graph":
            self._send(200, graph_payload(report) if report.get("ready") else report)
        elif path == "/api/anomaly/detect":
            self._send(200, report["anomaly"] if report.get("ready") else report)
        elif path == "/api/history":
            self._send(200, {"cases": _cases(), "count": len(_cases())})
        elif path == "/" or path == "/index.html" or path.startswith("/assets/"):
            # Serve the production React build when it exists. The root HTML
            # remains a dependency-free fallback before `npm run build`.
            dist_root = ROOT.parent / "frontend" / "dist"
            requested = dist_root / path.lstrip("/") if path.startswith("/assets/") else dist_root / "index.html"
            page = requested if requested.exists() else ROOT.parent / "frontend" / "index.html"
            body = page.read_bytes()
            self.send_response(200)
            content_type = mimetypes.guess_type(str(page))[0] or "text/html"
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "Request body must be valid JSON"})
            return
        report = investigate()
        if path in ("/api/investigation/start", "/api/rca/investigate"):
            self._send(200 if report.get("ready") else 422, report)
        elif path == "/api/v1/diagnose":
            case_id = str(body.get("case_id", "")).strip()
            failure_time = str(body.get("failure_time", "")).strip()
            description = str(body.get("description", "")).strip()
            if not case_id or not failure_time or not description:
                self._send(422, {"error": "case_id, failure_time, and description are required"})
                return
            self._send(200, diagnose_case(case_id, failure_time, description))
        elif path == "/api/rag/search":
            query = str(body.get("query", "")).strip()
            if not query:
                self._send(422, {"error": "query is required; RAG does not use a fabricated default query"})
                return
            try:
                result = retrieve_cases(DATA / "historical_cases.json", query, limit=5)
            except ValueError as error:
                self._send(500, {"error": str(error)})
                return
            self._send(200, {"query": query, **result})
        elif path == "/api/chat":
            question = str(body.get("question", "")).strip()
            if not question:
                self._send(422, {"error": "question is required"})
                return
            if not report.get("ready"):
                self._send(422, report)
                return
            try:
                answer, powered_by_gemini = gemini_answer(question, body.get("context", report))
            except RuntimeError as error:
                self._send(503, {"error": str(error)})
                return
            self._send(200, {"answer": answer, "powered_by": "gemini" if powered_by_gemini else "unknown", "grounded_in": "current e-commerce investigation"})
        elif path == "/api/solution/generate":
            self._send(200, report["solution"])
        elif path == f"/api/investigation/{INVESTIGATION_ID}/verify":
            decision = body.get("decision")
            if decision not in ("approved", "modified", "rejected"):
                self._send(422, {"error": "decision must be approved, modified, or rejected"})
                return
            REVIEWS[INVESTIGATION_ID] = {"status": "verified", "decision": decision, "notes": body.get("notes", "")}
            self._send(200, {**REVIEWS[INVESTIGATION_ID], "saved_to_local_history": False, "storage": "browser localStorage"})
        elif path == "/api/data/upload":
            filename = str(body.get("filename", "")).strip()
            content = body.get("content", "")
            try:
                result = ingest_upload(filename, content)
                self._send(200, {**result, "message": "File added to this backend investigation context."})
            except ValueError as error:
                self._send(422, {"error": str(error)})
        else:
            self._send(404, {"error": "Not found"})

    def do_DELETE(self) -> None:
        if urlparse(self.path).path == "/api/data/upload":
            UPLOADS.clear()
            REVIEWS.clear()
            self._send(200, {"cleared": True, "message": "Uploaded investigation data cleared."})
            return
        self._send(404, {"error": "Not found"})

    def log_message(self, *_args: object) -> None:
        print(f"[backend] {self.command} {self.path}", flush=True)


if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True, name="incoming-monitor").start()
    print("Pygenic Arc running at http://localhost:8000")
    ThreadingHTTPServer(("localhost", 8000), Handler).serve_forever()
