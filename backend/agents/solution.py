from .base import InvestigationAgent
from .state import InvestigationState, message


class SolutionPlannerAgent(InvestigationAgent):
    name = "Solution Planner Agent"

    def run(self, state: InvestigationState) -> InvestigationState:
        report = state["investigation"]
        plan = report.get("solution", {}).get("plan", [])
        state.setdefault("messages", []).append(message(
            self.name, "Verification Agent", "plan_ready",
            f"Prepared {len(plan)} verification-first actions; no remediation is executed.",
            list((report.get("causes") or [{}])[0].get("evidence_ids", [])),
        ))
        return self._complete(state)
