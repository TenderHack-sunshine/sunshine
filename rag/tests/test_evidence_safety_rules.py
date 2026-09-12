from __future__ import annotations

from src.application.evidence_sufficiency import EvidenceSufficiencyChecker
from src.generation.grounding import validate_grounding


def test_legal_consequence_is_not_inferred_from_a_technical_manual():
    result = EvidenceSufficiencyChecker(enabled=True).evaluate(
        "Какова юридическая сила МЧД и последствия?",
        [{"chunk_id": "manual:upload", "authority": "official", "source_type": "official_manual",
          "text": "Загрузите МЧД в профиль. Юридические последствия не описаны."}],
    )
    assert result.sufficient is False
    assert result.reason == "CONSEQUENCE_REQUIRES_NORMATIVE_EVIDENCE"


def test_one_shared_generic_word_does_not_ground_a_substantive_claim():
    result = validate_grounding("Портал гарантирует автоматическую оплату комиссии.", [
        {"text": "Портал позволяет создать оферту."},
    ])
    assert result.grounded is False
    assert result.reason == "unsupported_substantive_claim"
