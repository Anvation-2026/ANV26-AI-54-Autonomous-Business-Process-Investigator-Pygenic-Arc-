"""Base class for independent agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .state import InvestigationState


class InvestigationAgent(ABC):
    name: str

    @abstractmethod
    def run(self, state: InvestigationState) -> InvestigationState:
        raise NotImplementedError

    def _complete(self, state: InvestigationState) -> InvestigationState:
        completed = list(state.get("completed_agents", []))
        if self.name not in completed:
            completed.append(self.name)
        state["completed_agents"] = completed
        return state
