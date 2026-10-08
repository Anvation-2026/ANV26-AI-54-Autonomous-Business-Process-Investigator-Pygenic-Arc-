"""RCA agent with an optional LangChain tool call and safe deterministic fallback."""

from __future__ import annotations

import json
import os
import hashlib
import threading
from typing import Any

from .base import InvestigationAgent
from .state import InvestigationState, message

_TOOL_CALL_CACHE: dict[str, bool] = {}
_TOOL_CALL_CACHE_LOCK = threading.Lock()


def rank_evidence_tool(evidence: list[dict[str, Any]], causes: list[dict[str, Any]]) -> dict[str, Any]:
    """Tool exposed to an LLM; it can only rank supplied evidence."""
    evidence_ids = {item.get("id") for item in evidence}
    ranked = []
    for cause in causes:
        linked = [item for item in cause.get("evidence_ids", []) if item in evidence_ids]
        ranked.append({**cause, "evidence_ids": linked, "evidence_coverage": len(linked)})
    return {"causes": sorted(ranked, key=lambda item: item.get("score", 0), reverse=True)}


class RCAAgent(InvestigationAgent):
    name = "RCA Agent"

    def _llm_tool_call(self, report: dict[str, Any]) -> bool:
        """Attempt a grounded tool call only when optional LangChain deps exist."""
        if not os.environ.get("GEMINI_API_KEY", "").strip():
            return False
        cache_key = hashlib.sha256(json.dumps({
            "evidence": report.get("evidence", []),
            "causes": report.get("causes", []),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        with _TOOL_CALL_CACHE_LOCK:
            if cache_key in _TOOL_CALL_CACHE:
                return _TOOL_CALL_CACHE[cache_key]
        try:
            from langchain_core.messages import HumanMessage
            from langchain_google_genai import ChatGoogleGenerativeAI

            model = ChatGoogleGenerativeAI(
                model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                google_api_key=os.environ["GEMINI_API_KEY"],
                temperature=0,
            ).bind_tools([rank_evidence_tool])
            response = model.invoke([HumanMessage(content=(
                "Use the rank_evidence_tool exactly once with only this JSON evidence and causes. "
                "Do not infer facts: " + json.dumps({
                    "evidence": report.get("evidence", []), "causes": report.get("causes", [])
                })
            ))])
            # A tool call is accepted only as an audit signal; deterministic
            # scores remain authoritative for the frontend contract.
            result = bool(getattr(response, "tool_calls", []))
            with _TOOL_CALL_CACHE_LOCK:
                _TOOL_CALL_CACHE[cache_key] = result
            return result
        except Exception:
            with _TOOL_CALL_CACHE_LOCK:
                _TOOL_CALL_CACHE[cache_key] = False
            return False

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        tool_used = self._llm_tool_call(report)
        state["llm_used"] = tool_used
        top = (report.get("causes") or [{}])[0]
        state.setdefault("messages", []).append(message(
            self.name, "Solution Planner Agent", "rca_complete",
            f"Top cause is {top.get('name', 'undetermined')} using deterministic evidence ranking"
            + (" with an LLM tool-call audit." if tool_used else " (LLM unavailable; deterministic fallback)."),
            top.get("evidence_ids", []),
        ))
        report.setdefault("method", {})["rca_mode"] = "langchain_tool_call" if tool_used else "deterministic_fallback"
        return self._complete(state)
