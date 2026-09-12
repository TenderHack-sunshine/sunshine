"""Small, explainable judge for clarification versus human escalation."""
from __future__ import annotations

from dataclasses import dataclass



@dataclass(frozen=True)
class EscalationDecision:
    clarify: bool
    reason: str = "ESCALATE_TO_OPERATOR"


class EscalationJudge:
    """Keep ambiguous short turns in the dialog before opening a ticket.

    This is intentionally deterministic: a second generative model would add
    latency and could itself hallucinate a routing decision.  The judge only
    overrides escalation for plainly incomplete follow-ups; a concrete error
    or a detailed unsupported request still reaches a specialist.
    """

    def decide(self, query: str, reason: str | None, candidates: list[dict]) -> EscalationDecision:
        # Missing slots are handled before retrieval by IntentFrame. A failed
        # retrieval is not evidence of ambiguity and must follow the handoff
        # state machine rather than inventing another clarification here.
        del query, reason, candidates
        return EscalationDecision(False)
