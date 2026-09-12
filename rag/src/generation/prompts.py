OPERATOR_FALLBACK = (
    "I could not find sufficiently reliable information in the knowledge base. "
    "Please contact a support operator."
)

# The current generator is extractive, but keeping this explicit makes the
# evidence contract clear for the future LLM adapter.
EVIDENCE_GENERATION_POLICY = (
    "Answer only from supplied evidence. Prefer official documentation; use "
    "support tickets only as secondary troubleshooting context. Do not invent "
    "missing information; if evidence is insufficient, escalate. Keep support "
    "answers concise."
)
