"""Evidence-first specialist agents used by the investigation graph."""

from __future__ import annotations

from .base import InvestigationAgent
from .state import InvestigationState, message


class AnomalyDetectionAgent(InvestigationAgent):
    name = "Anomaly Detection Agent"

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        anomalies = report.get("anomalies", [])
        report.setdefault("method", {})["anomaly_policy"] = "Numeric deviation from the uploaded-record baseline."
        state.setdefault("messages", []).append(message(
            self.name, "Evidence Collection Agent", "anomaly_detected",
            f"Detected {len(anomalies)} anomaly candidate(s) from uploaded numeric fields.",
            [item.get("id", "") for item in anomalies],
        ))
        return self._complete(state)


class EvidenceCollectionAgent(InvestigationAgent):
    name = "Evidence Collection Agent"

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        evidence = report.get("evidence", [])
        state.setdefault("messages", []).append(message(
            self.name, "Conflict Analysis Agent", "evidence_collected",
            f"Linked {len(evidence)} evidence item(s) to uploaded source files.",
            [item.get("id", "") for item in evidence],
        ))
        return self._complete(state)


class ConflictAnalysisAgent(InvestigationAgent):
    name = "Conflict Analysis Agent"

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        conflicts = report.get("conflicts", [])
        state.setdefault("messages", []).append(message(
            self.name, "Hybrid RCA Agent", "conflict_analysis_complete",
            f"Preserved {len(conflicts)} conflicting signal(s); no unsupported conflict was created.",
            [item.get("id", "") for item in conflicts],
        ))
        return self._complete(state)


class RAGMemoryAgent(InvestigationAgent):
    name = "RAG Memory Agent"

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        matches = report.get("historical_cases", [])
        report.setdefault("method", {})["rag_agent"] = {
            "retrieval": report.get("history", {}).get("retrieval", {}),
            "matches": len(matches),
        }
        state.setdefault("messages", []).append(message(
            self.name, "Solution Planner Agent", "memory_retrieved",
            f"Retrieved {len(matches)} historical case match(es) from the backend memory file.",
            [],
        ))
        return self._complete(state)
