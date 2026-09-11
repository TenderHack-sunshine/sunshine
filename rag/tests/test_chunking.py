from src.ingestion.chunker import chunk_document, chunk_documents, extract_atomic_units


class FakeEmbedder:
    """Deterministic vectors: alpha units are similar; beta units form a new topic."""

    def count_tokens(self, text):
        return len(text.split())

    def embed_documents(self, texts):
        return [[1.0, 0.0] if "alpha" in text.casefold() else [0.0, 1.0] for text in texts]


def test_chunker_keeps_page_section_and_does_not_split_paragraphs_blindly():
    document = {"source": "manual.pdf", "page": 7, "authority": "manual", "text": "1. Registration\nFirst useful paragraph has sufficient words to become a proper chunk.\nSecond useful paragraph belongs to the same section."}
    chunks = chunk_document(document, chunk_size=50, min_chunk_tokens=3)
    assert chunks
    assert chunks[0]["page_start"] == 7
    assert chunks[0]["section"] == "1. Registration"
    assert "First useful paragraph" in chunks[0]["text"]


def test_section_propagates_and_chunks_can_span_pages():
    documents = [
        {"source": "manual.pdf", "page": 1, "text": "1. Setup\nalpha one has enough useful content."},
        {"source": "manual.pdf", "page": 2, "text": "alpha two continues the same instructions."},
    ]
    chunks = chunk_documents(documents, strategy="semantic", embedder=FakeEmbedder(), min_tokens=1, target_tokens=30, max_tokens=50)
    assert len(chunks) == 1
    assert chunks[0]["page_start"] == 1 and chunks[0]["page_end"] == 2
    assert chunks[0]["section"] == "1. Setup"
    assert chunks[0]["chunking_strategy"] == "semantic"


def test_heading_boundary_does_not_relabel_previous_content():
    document = {"source": "manual.pdf", "pages": [{"page": 1, "text": "1. First\nalpha first section content.\n2. Second\nbeta second section content."}]}
    chunks = chunk_documents([document], strategy="semantic", embedder=FakeEmbedder(), min_tokens=1, target_tokens=30, max_tokens=50)
    assert [chunk["section"] for chunk in chunks] == ["1. First", "2. Second"]
    assert "alpha first" in chunks[0]["text"]
    assert "beta second" not in chunks[0]["text"]


def test_semantic_distance_creates_breakpoint():
    document = {"source": "manual.pdf", "page": 1, "text": "alpha one words here.\nalpha two words here.\nalpha three words here.\nbeta new topic here.\nbeta follow up here."}
    chunks = chunk_documents([document], strategy="semantic", embedder=FakeEmbedder(), min_tokens=3, target_tokens=30, max_tokens=50)
    assert len(chunks) == 2
    assert "alpha three" in chunks[0]["text"]
    assert chunks[1]["text"].startswith("beta new")


def test_no_tiny_chunk_for_early_semantic_break():
    document = {"source": "manual.pdf", "page": 1, "text": "alpha brief.\nbeta content that makes the combined chunk viable."}
    chunks = chunk_documents([document], strategy="semantic", embedder=FakeEmbedder(), min_tokens=5, target_tokens=20, max_tokens=50)
    assert len(chunks) == 1
    assert chunks[0]["token_count"] >= 5


def test_forced_split_and_deterministic_ids():
    document = {"source": "manual.pdf", "page": 1, "text": "alpha one two three four five six.\nalpha seven eight nine ten eleven twelve.\nalpha thirteen fourteen fifteen sixteen seventeen eighteen."}
    kwargs = {"strategy": "semantic", "embedder": FakeEmbedder(), "min_tokens": 1, "target_tokens": 12, "max_tokens": 14, "forced_split_overlap_tokens": 0}
    first, second = chunk_documents([document], **kwargs), chunk_documents([document], **kwargs)
    assert len(first) > 1
    assert first[0]["chunking_strategy"] == "semantic_forced_split"
    assert [chunk["chunk_id"] for chunk in first] == [chunk["chunk_id"] for chunk in second]
    assert max(chunk["token_count"] for chunk in first) <= 14


def test_recursive_fallback_remains_available():
    document = {"source": "manual.pdf", "page": 7, "text": "One useful paragraph.\nAnother useful paragraph."}
    chunks = chunk_documents([document], strategy="recursive", chunk_size=20, min_chunk_tokens=1)
    assert chunks and chunks[0]["chunking_strategy"] == "recursive"
