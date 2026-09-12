from __future__ import annotations

from src.application.evidence import compact_evidence, tagged_context


def _item(chunk_id, document_id, index, text, authority="official"):
    return {"chunk_id": chunk_id, "document_id": document_id, "text": text, "section": "s", "authority": authority,
            "score": 1.0, "metadata": {"chunk_index": index}}


def test_evidence_removes_exact_duplicates_and_compacts_adjacent_chunks():
    first = _item("a:1", "a", 1, "first")
    adjacent = _item("a:2", "a", 2, "second")
    compact = compact_evidence([first, dict(first), adjacent])
    assert len(compact) == 1
    assert compact[0]["merged_chunk_ids"] == ["a:1", "a:2"]
    assert "first" in compact[0]["text"] and "second" in compact[0]["text"]


def test_official_evidence_is_before_secondary_ticket_and_context_is_tagged():
    ticket = _item("t", "t", 1, "historical", "case_history")
    official = _item("o", "o", 1, "official", "official")
    compact = compact_evidence([ticket, official])
    assert compact[0]["authority"] == "official"
    context = tagged_context(compact)
    assert context.index("[OFFICIAL]") < context.index("[SUPPORT_TICKET]")
