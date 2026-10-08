"""Compiled LangGraph orchestration with a dependency-free compatible runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .checkpoint import JsonCheckpointStore
from .analysis import AnomalyDetectionAgent, ConflictAnalysisAgent, EvidenceCollectionAgent, RAGMemoryAgent
from .planner import AgentPlanner
from .rca import RCAAgent
from .solution import SolutionPlannerAgent
from .state import InvestigationState
from .verification import VerificationAgent


class _FallbackGraph:
    def __init__(self, nodes: list[tuple[str, Any]], store: JsonCheckpointStore):
        self.nodes, self.store = nodes, store

    def invoke(self, state: InvestigationState) -> InvestigationState:
        for name, agent in self.nodes:
            state = agent.run(state)
            state["checkpoint_ref"] = self.store.save(dict(state), name)
        return state


def build_investigation_graph(checkpoint_path: str | Path):
    store = JsonCheckpointStore(checkpoint_path)
    nodes = [
        ("anomaly_detection", AnomalyDetectionAgent()),
        ("evidence_collection", EvidenceCollectionAgent()),
        ("conflict_analysis", ConflictAnalysisAgent()),
        ("rca", RCAAgent()),
        ("rag_memory", RAGMemoryAgent()),
        ("solution", SolutionPlannerAgent()),
        ("verification", VerificationAgent()),
    ]
    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(InvestigationState)
        for name, agent in nodes:
            graph.add_node(name, agent.run)
        graph.add_edge(START, "anomaly_detection")
        graph.add_edge("anomaly_detection", "evidence_collection")
        graph.add_edge("evidence_collection", "conflict_analysis")
        graph.add_edge("conflict_analysis", "rca")
        graph.add_edge("rca", "rag_memory")
        graph.add_edge("rag_memory", "solution")
        graph.add_edge("solution", "verification")
        graph.add_edge("verification", END)
        # LangGraph's own compiled graph is used when installed; durable JSON
        # checkpoints are written by the wrapper after invocation.
        return _CheckpointedLangGraph(graph.compile(), store, nodes)
    except ImportError:
        return _FallbackGraph(nodes, store)


class _CheckpointedLangGraph:
    def __init__(self, compiled: Any, store: JsonCheckpointStore, nodes: list[tuple[str, Any]]):
        self.compiled, self.store, self.nodes = compiled, store, nodes

    def invoke(self, state: InvestigationState) -> InvestigationState:
        result = self.compiled.invoke(state)
        for name, _ in self.nodes:
            result["checkpoint_ref"] = self.store.save(dict(result), name)
        return result


def run_investigation_graph(report: dict[str, Any], checkpoint_path: str | Path) -> dict[str, Any]:
    state: InvestigationState = {
        "investigation": report,
        "messages": [],
        "completed_agents": [],
        "plan": AgentPlanner().plan({}),
        "llm_used": False,
    }
    result = build_investigation_graph(checkpoint_path).invoke(state)
    report = result["investigation"]
    report.setdefault("method", {})["planner"] = result["plan"]
    report["method"]["agent_messages"] = result["messages"]
    report["method"]["checkpoint_id"] = result.get("checkpoint_ref")
    report["method"]["graph_agents"] = result["completed_agents"]
    return report
