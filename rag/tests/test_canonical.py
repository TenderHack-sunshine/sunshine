from __future__ import annotations

import json

import pytest

from src.retrieval.canonical import prepare_canonical_chunks


def _write(path, records):
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def test_canonical_merge_preserves_kb_metadata_and_local_semantics(tmp_path):
    kb, local = tmp_path / "kb.jsonl", tmp_path / "local.jsonl"
    _write(kb, [{"chunk_id": "kb:1:0", "document_id": "kb:1", "text": "KB", "title": "Article", "support_level": "L2", "metadata": {"article_id": 1, "tags": ["tag"]}}])
    _write(local, [{"chunk_id": "local:abc:0", "document_id": "local:abc", "text": "Manual", "source_type": "official_manual", "authority": "official", "source_path": "manuals/a.pdf", "page_start": 2, "page_end": 2, "metadata": {}}])
    chunks, report = prepare_canonical_chunks(kb, local)
    assert report["total_canonical_chunks"] == 2
    assert chunks[0]["source_type"] == "official_kb"
    assert chunks[0]["authority"] == "official"
    assert chunks[0]["metadata"]["article_id"] == 1
    assert chunks[1]["source_path"] == "manuals/a.pdf"


def test_canonical_merge_fails_on_duplicate_or_empty_chunk_id(tmp_path):
    kb, local = tmp_path / "kb.jsonl", tmp_path / "local.jsonl"
    _write(kb, [{"chunk_id": "same", "text": "one"}])
    _write(local, [{"chunk_id": "same", "text": "two"}])
    with pytest.raises(ValueError, match="Duplicate chunk_id"):
        prepare_canonical_chunks(kb, local)
    _write(local, [{"chunk_id": "unique", "text": ""}])
    with pytest.raises(ValueError, match="empty text"):
        prepare_canonical_chunks(kb, local)
