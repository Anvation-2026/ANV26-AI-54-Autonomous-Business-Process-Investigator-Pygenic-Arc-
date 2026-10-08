"""Shared state and agent-to-agent message contracts.

The state is deliberately JSON-compatible so checkpoints are portable and do
not expose raw credentials or permit agents to invent evidence.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentMessage(TypedDict):
    sender: str
    recipient: str
    kind: str
    content: str
    evidence_ids: list[str]


class InvestigationState(TypedDict, total=False):
    investigation: dict[str, Any]
    messages: list[AgentMessage]
    completed_agents: list[str]
    plan: list[str]
    checkpoint_ref: str
    llm_used: bool


def message(sender: str, recipient: str, kind: str, content: str, evidence_ids: list[str] | None = None) -> AgentMessage:
    return {
        "sender": sender,
        "recipient": recipient,
        "kind": kind,
        "content": content,
        "evidence_ids": evidence_ids or [],
    }
