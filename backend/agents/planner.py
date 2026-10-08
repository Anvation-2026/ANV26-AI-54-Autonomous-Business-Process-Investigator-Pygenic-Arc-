from __future__ import annotations

from .state import InvestigationState


class AgentPlanner:
    """Plans the fixed evidence-first sequence; no agent can skip verification."""

    steps = [
        "anomaly_detection",
        "evidence_collection",
        "conflict_analysis",
        "rca",
        "rag_memory",
        "solution",
        "verification",
    ]

    def plan(self, state: InvestigationState) -> list[str]:
        if not state:
            return list(self.steps)
        report = state.get("investigation", {})
        planned = list(self.steps)
        if not report.get("historical_cases"):
            planned.remove("rag_memory")
        return planned
