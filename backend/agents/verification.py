from .base import InvestigationAgent
from .state import InvestigationState, message


class VerificationAgent(InvestigationAgent):
    name = "Verification Agent"

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        state.setdefault("messages", []).append(message(
            self.name, "human", "review_required",
            "Diagnosis is pending explicit human approval, modification, or rejection.",
            [item.get("id", "") for item in report.get("evidence", [])],
        ))
        return self._complete(state)
