from .base import InvestigationAgent
from .state import InvestigationState, message


class InvestigatorAgent(InvestigationAgent):
    name = "Investigator Agent"

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        evidence = report.get("evidence", [])
        report.setdefault("method", {})["evidence_policy"] = "Only uploaded or bundled evidence is used."
        state.setdefault("messages", []).append(message(
            self.name, "RCA Agent", "evidence_ready",
            f"Collected {len(evidence)} evidence records; no external facts were added.",
            [item.get("id", "") for item in evidence],
        ))
        return self._complete(state)
