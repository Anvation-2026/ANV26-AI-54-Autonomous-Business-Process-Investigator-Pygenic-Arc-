# Pygenic Arc

Pygenic Arc is an evidence-first **Autonomous Business Process Investigator**
for the hackathon problem. The demo investigates an e-commerce order-completion
failure: completion drops approximately 35%, payment failures rise 42%, and
timeouts reach 4x normal while traffic and inventory remain normal.

The gateway health endpoint still reports `OPERATIONAL`. Pygenic Arc surfaces
this as conflicting/noisy evidence and explains why a provider status page does
not rule out regional or transaction-level latency degradation.

## Run the working MVP

Requires Python 3.10+ and no third-party packages:

```powershell
python backend\app.py
```

Open <http://localhost:8000>. The dashboard provides Overview, Anomaly,
Evidence, Root cause, Solution + RAG, and Verify + report surfaces.

## React frontend

The dashboard is implemented in React with Vite under `frontend/`. Run the
backend in one terminal and the React development server in another:

```powershell
# terminal 1
python backend\app.py

# terminal 2
npm install --prefix frontend
npm run dev --prefix frontend
```

Open <http://localhost:5173>. Vite proxies `/api` requests to the Python
backend at port 8000. Create a production bundle with:

```powershell
npm run build --prefix frontend
```

## Gemini chatbot and PDF

The chatbot sends each question with the current e-commerce anomaly, evidence,
ranked causes, solution, historical cases, and browser history to
`POST /api/chat`. The backend calls Gemini without exposing the API key to the
browser. Configure it locally:

```powershell
Copy-Item backend\.env.example backend\.env
# edit .env and set GEMINI_API_KEY=your_key
python backend\app.py
```

If `GEMINI_API_KEY` is empty or Gemini is unavailable, the chatbot clearly
reports offline mode instead of pretending that an LLM answered. The PDF
button creates and downloads a real `.pdf` file in the browser using jsPDF; it
does not depend on popups or the print dialog.

The React/Vite application is the frontend under `frontend\`; the Python API
and its data are isolated under `backend\`.

## Upload and local learning loop

Use **Add business data** at the top of the React workspace to upload CSV, JSON,
or a ZIP archive containing CSV/JSON evidence. ZIP files are extracted in the
browser, then every file is validated and submitted to the backend. The UI
does not create an offline or synthetic diagnosis when the backend is
unavailable.

The first investigation uses the RCA engine when no sufficiently similar
history exists. After a human selects **Approve & save history** or
**Modify & save**, the case is saved in the browser's `localStorage`. Uploaded
files and review decisions are also stored there. Rejected recommendations are
not stored. No MongoDB, ChromaDB, or server history database is used; the
backend's separate ignored checkpoint file only stores graph execution state.

The investigation is deterministic and uses only the files uploaded through
the backend API. It does not invent a result when evidence is absent or
non-numeric: the API returns `status: "insufficient_evidence"` instead.
`backend\requirements.txt` lists optional integrations for a later deployment:
FastAPI/Pydantic, Pandas/NumPy/scikit-learn, NetworkX, ChromaDB, Gemini,
LangGraph, LangChain Core/Google GenAI, and MongoDB.

## API flow

The standard endpoints are available:

```text
GET  /api/anomaly/detect
GET  /api/health
GET  /api/monitor/status
POST /api/data/upload
POST /api/investigation/start
GET  /api/investigation/{id}/evidence
POST /api/rca/investigate
POST /api/rag/search
POST /api/solution/generate
GET  /api/investigation/{id}/graph
POST /api/investigation/{id}/verify
GET  /api/investigation/{id}/report
POST /api/v1/diagnose
```

Verification accepts only `approved`, `modified`, or `rejected`. Approved and
modified results are saved to browser localStorage; no production action is
executed.

## Agent-facing RCA tool

Use this tool whenever a business process fails, an alert triggers, or a user
reports an operational incident. It accepts a case identifier, failure time,
and symptom description, then returns the ranked causes, evidence trail,
confidence/evidence scores, conflicting signals, and recommended actions from
the currently loaded investigation data.

```text
Tool name: run_root_cause_analysis
Endpoint: POST http://localhost:8000/api/v1/diagnose
Input: {"case_id": string, "failure_time": string, "description": string}
Output: structured JSON diagnosis
```

Example:

```powershell
$body = @{
  case_id = "incident-9921"
  failure_time = "2026-04-18 10:35:00"
  description = "Checkout requests became slow and some payments failed."
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/v1/diagnose `
  -Method Post -ContentType "application/json" -Body $body
```

The endpoint does not execute remediation. If no telemetry has been uploaded,
it returns `status: "insufficient_evidence"` and explains what data is needed.

## Real-time local-folder monitor

The backend continuously watches `backend\incoming\` every two seconds. Copy a
new CSV or JSON file into that folder; the monitor validates it, ingests it,
runs the same anomaly/evidence/Hybrid RCA pipeline, and exposes its state at
`GET /api/monitor/status`. Invalid files remain visible as `last_error`; they
are never converted into a successful diagnosis.

## Backend agent architecture

The backend runs a compiled, evidence-first graph in `backend\agents\`.
`InvestigatorAgent`, `RCAAgent`, `SolutionPlannerAgent`, and
`VerificationAgent` are independent classes connected by a shared,
JSON-compatible `InvestigationState` and explicit agent-to-agent messages.
`AgentPlanner` fixes the order and always ends at a human verification gate.
Each node writes a durable checkpoint to `backend\checkpoints.json` (ignored
by Git), while preserving the existing frontend response shape.

`RCAAgent` exposes `rank_evidence_tool` to LangChain. With a Gemini key and the
optional provider installed it attempts a temperature-zero, evidence-only tool
call. Deterministic evidence ranking remains authoritative; if credentials,
the provider, network, or tool call is unavailable, the agent records
`deterministic_fallback` and returns the same strict result. No agent executes
production remediation.

## Architecture decisions

The deterministic anomaly, filtering, evidence scoring, conflict detection,
ranking, and projected outcomes happen before any LLM integration. The current
historical retrieval is a dependency-free keyword-similarity fallback; it is
explicitly labeled in the API. Gemini embeddings + ChromaDB can replace that
provider without changing the frontend contract.

Scores are labeled **Confidence / Evidence Score**, not scientifically
calibrated probabilities. Projected outcomes are estimates from similar cases,
not guarantees.

## Phase 1: synthetic scenario generator

The new Phase 1 backend lives under `backend/`:

```text
backend/
├── app/
│   └── data_gen/
│       ├── generator.py
│       ├── cli.py
│       └── schemas.py
├── data/
│   ├── business_metrics.csv
│   ├── transactions.csv
│   ├── tickets.csv
│   ├── logs.csv
│   ├── process_events.csv
│   ├── historical_cases.json
│   └── ground_truth.json
└── requirements.txt
```

The generated schemas are:

```text
business_metrics: timestamp, orders, revenue, profit, error_rate,
  processing_time_sec, conversion_rate, order_completion_rate
transactions: txn_id, ts, customer_id, amount, payment_method, gateway,
  app_version, status, failure_code, region
tickets: ticket_id, ts, category, text, severity, region, app_version
logs: ts, service, level, message, source
process_events: ts, event_type, actor, details
historical_cases: case_id, symptoms, root_cause, fix, outcome, lessons
```

Generate another deterministic scenario:

```powershell
python -m backend.app.data_gen.cli --scenario PAYMENT_GATEWAY_OUTAGE --severity high --seed 7 --output backend\data
```

Available scenarios are `BAD_DEPLOY`, `PAYMENT_GATEWAY_OUTAGE`,
`PRICING_ERROR`, `CAMPAIGN_SURGE`, and `DATA_PIPELINE_BUG`. Every generated
scenario includes a lagging healthy monitoring signal, an unrelated red-herring
process event, Gaussian noise, and approximately 5% missing KPI values.
