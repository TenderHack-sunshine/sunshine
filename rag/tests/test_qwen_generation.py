from __future__ import annotations

import pytest

from src.application.clarification import ClarificationPolicy
from src.application.pipeline import QueryPreprocessor, RAGService
from src.generation.qwen import GenerationUnavailable, QwenGenerator, build_grounded_prompt, select_generation_evidence
from src.safety.profanity import ProfanityResult


class Client:
    def __init__(self, text="Чтобы добавить МЧД, откройте профиль и выберите добавление МЧД."):
        self.text, self.calls = text, 0

    def generate(self, prompt, max_new_tokens, max_seconds=None):
        self.calls += 1
        assert "Вопрос пользователя:" in prompt and "chunk_id: c1" in prompt
        from src.generation.qwen import GenerationResponse
        return GenerationResponse(self.text, 12.5, "Qwen3-4B")


class UnavailableClient(Client):
    def generate(self, *_args):
        self.calls += 1
        raise GenerationUnavailable("offline")


class Retriever:
    def __init__(self): self.calls = 0
    def retrieve_with_trace(self, *_args, **_kwargs):
        self.calls += 1
        item = {"chunk_id": "c1", "document_id": "d1", "text": "Чтобы добавить МЧД, откройте профиль и выберите добавление МЧД.",
                "authority": "official", "source_type": "official_manual", "score": .9, "metadata": {}}
        return {"results": [item], "official_bm25": [], "official_dense": [], "timing": {}}


class Detector:
    backend = "rule"
    def __init__(self, flagged=False): self.flagged = flagged
    def detect(self, _query): return ProfanityResult(self.flagged, float(self.flagged), 1.0)


def service(client):
    return RAGService(Retriever(), preprocessor=QueryPreprocessor(Detector()),
                      clarification_policy=ClarificationPolicy(enabled=False), generator=QwenGenerator(client))


def test_qwen_adapter_receives_query_and_returns_diagnostics():
    client = Client()
    result = service(client).ask("Как добавить МЧД?")
    assert result["status"] == "ANSWER"
    assert result["answer"] != result["sources"][0].get("text")
    generation = result["diagnostics"]["generation"]
    assert {key: generation[key] for key in ("backend", "invoked", "model", "latency_ms", "fallback_used")} == {
        "backend": "qwen", "invoked": True, "model": "Qwen3-4B", "latency_ms": 12.5, "fallback_used": False,
    }
    assert generation["evidence_chunk_count"] == 1
    assert generation["prompt_characters"] > generation["context_characters"] > 0
    assert generation["max_new_tokens"] == 128
    assert generation["max_seconds"] == 90
    assert result["diagnostics"]["grounding"]["grounded"] is True
    assert client.calls == 1


@pytest.mark.parametrize("query", ["Как это исправить?", "Что делать с МЧД?"])
def test_qwen_is_not_called_when_clarification_precedes_retrieval(query):
    client = Client()
    result = RAGService(Retriever(), preprocessor=QueryPreprocessor(Detector()), generator=QwenGenerator(client)).ask(query)
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert result["diagnostics"]["generation"]["invoked"] is False
    assert client.calls == 0


def test_qwen_is_not_called_after_profanity_gate():
    client = Client()
    result = RAGService(Retriever(), preprocessor=QueryPreprocessor(Detector(True)), generator=QwenGenerator(client)).ask("bad")
    assert result["status"] == "REFUSE_PROFANITY"
    assert result["diagnostics"]["generation"]["invoked"] is False
    assert client.calls == 0


def test_qwen_is_not_called_when_confidence_escalates_for_no_evidence():
    class EmptyRetriever:
        def retrieve_with_trace(self, *_args, **_kwargs):
            return {"results": [], "official_bm25": [], "official_dense": [], "timing": {}}
    client = Client()
    result = RAGService(EmptyRetriever(), preprocessor=QueryPreprocessor(Detector()),
                        clarification_policy=ClarificationPolicy(enabled=False), generator=QwenGenerator(client)).ask("Как добавить МЧД?")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["generation"]["invoked"] is False
    assert client.calls == 0


def test_generation_unavailable_fails_closed_without_extractive_fallback():
    client = UnavailableClient()
    result = service(client).ask("Как добавить МЧД?")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["confidence_reason"] == "GENERATION_UNAVAILABLE"
    assert result["diagnostics"]["generation"]["fallback_used"] is False


def test_unsupported_numeric_generation_fails_grounding():
    client = Client("Срок составляет 5 месяцев.")
    result = service(client).ask("Как добавить МЧД?")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["confidence_reason"] == "GENERATION_NOT_GROUNDED"
    assert result["diagnostics"]["grounding"]["reason"] == "unsupported_numeric_claim"


@pytest.mark.parametrize("output", ["Недостаточно данных.", "Недостаточно информации", "Н", ""])
def test_invalid_qwen_refusal_or_truncation_uses_grounded_extractive_fallback(output):
    client = Client(output)
    result = service(client).ask("Как добавить МЧД?")
    assert result["status"] == "ANSWER"
    assert result["answer"] == "Чтобы добавить МЧД, откройте профиль и выберите добавление МЧД."
    assert result["diagnostics"]["generation"]["fallback_used"] is True
    assert result["diagnostics"]["generation"]["invalid_generation_reason"] in {"insufficient_data_refusal", "truncated_output", "empty_output"}
    assert result["diagnostics"]["grounding"]["grounded"] is True


def test_create_offer_refusal_falls_back_to_creation_procedure_not_definition():
    class OfferRetriever:
        def retrieve_with_trace(self, *_args, **_kwargs):
            definition = {"chunk_id": "definition", "document_id": "definition", "title": "Что такое оферта?",
                          "text": "Оферта — предложение поставщика.", "authority": "official", "source_type": "official_kb", "score": .9, "metadata": {}}
            procedure = {"chunk_id": "procedure", "document_id": "procedure", "title": "Способы создания оферт и СТЕ",
                         "text": "Чтобы создать оферту, откройте раздел «Оферты» и нажмите «Создать оферту».", "authority": "official", "source_type": "official_kb", "score": .8, "metadata": {}}
            return {"results": [definition, procedure], "official_bm25": [], "official_dense": [], "timing": {}}
    class RefusingOfferClient:
        def generate(self, *_args):
            from src.generation.qwen import GenerationResponse
            return GenerationResponse("Недостаточно данных", 1.0, "Qwen")
    result = RAGService(OfferRetriever(), preprocessor=QueryPreprocessor(Detector()),
                        clarification_policy=ClarificationPolicy(enabled=False), generator=QwenGenerator(RefusingOfferClient())).ask("Как создать оферту?")
    assert result["status"] == "ANSWER"
    assert "Создать оферту" in result["answer"]
    assert result["diagnostics"]["generation"]["fallback_used"] is True


def test_prompt_keeps_source_identifiers_and_exact_question():
    prompt = build_grounded_prompt("Какой срок?", [{"chunk_id": "c", "document_id": "d", "text": "Три месяца"}])
    assert "chunk_id: c" in prompt and "document_id: d" in prompt and "Какой срок?" in prompt


def test_generation_context_deduplicates_and_stays_within_budget():
    items = [
        {"chunk_id": "a", "text": "a" * 60}, {"chunk_id": "a", "text": "a" * 60},
        {"chunk_id": "b", "text": "b" * 60}, {"chunk_id": "c", "text": "c" * 60},
    ]
    selected = select_generation_evidence(items, 120, max_chunks=2)
    assert [item["chunk_id"] for item in selected] == ["a", "b"]
    assert sum(len(item["text"]) for item in selected) == 120


def test_length_limited_generation_retries_once_with_larger_budget():
    from src.generation.qwen import GenerationResponse

    class RetryClient:
        def __init__(self):
            self.budgets = []

        def generate(self, _prompt, max_new_tokens, _max_seconds=None):
            self.budgets.append(max_new_tokens)
            if len(self.budgets) == 1:
                return GenerationResponse("\u0427\u0442\u043e\u0431\u044b \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u041c\u0427\u0414, \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u0438 \u043f\u0435\u0440", 10, "Qwen", generated_tokens=128,
                                          truncated=True, finish_reason="length")
            return GenerationResponse("\u0427\u0442\u043e\u0431\u044b \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u041c\u0427\u0414, \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u041c\u0427\u0414.", 11, "Qwen", generated_tokens=19,
                                      truncated=False, finish_reason="stop")

    client = RetryClient()
    result = service(client).ask("\u041a\u0430\u043a \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u041c\u0427\u0414?")
    generation = result["diagnostics"]["generation"]
    assert result["status"] == "ANSWER"
    assert client.budgets == [128, 256]
    assert generation["retry_attempted"] is True
    assert generation["retry_count"] == 1
    assert generation["generated_tokens"] == 19
    assert generation["truncated"] is False
    assert generation["finish_reason"] == "stop"


def test_double_truncation_uses_grounded_fallback_and_keeps_diagnostics():
    from src.generation.qwen import GenerationResponse

    class AlwaysTruncatedClient:
        def __init__(self):
            self.calls = 0

        def generate(self, _prompt, max_new_tokens, _max_seconds=None):
            self.calls += 1
            return GenerationResponse("\u041c\u0430\u0441\u0441\u043e\u0432\u0430\u044f \u0437\u0430\u0433", 8, "Qwen", generated_tokens=max_new_tokens,
                                      truncated=True, finish_reason="length")

    client = AlwaysTruncatedClient()
    result = service(client).ask("\u041a\u0430\u043a \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u041c\u0427\u0414?")
    generation = result["diagnostics"]["generation"]
    assert result["status"] == "ANSWER"
    assert client.calls == 2
    assert generation["fallback_used"] is True
    assert generation["retry_attempted"] is True
    assert generation["truncated"] is True
    assert generation["finish_reason"] == "length"


def test_generation_context_prefers_query_aligned_approved_evidence():
    items = [
        {"chunk_id": "definition", "title": "Что такое оферта", "text": "Оферта — предложение."},
        {"chunk_id": "procedure", "title": "Способы создания оферт", "text": "Нажмите Создать оферту."},
    ]
    assert select_generation_evidence(items, 1000, 1, "Как создать оферту?")[0]["chunk_id"] == "procedure"
