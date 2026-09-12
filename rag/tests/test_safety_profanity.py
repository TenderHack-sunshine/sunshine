from __future__ import annotations

from types import SimpleNamespace

from src.application.pipeline import QueryPreprocessor, RAGService
from src.core.config import Settings
from src.safety.profanity import MLProfanityDetector, ProfanityResult


class FakeDetector:
    backend = "ml"

    def __init__(self, detected: bool, probability: float = .1, threshold: float = .5):
        self.result = ProfanityResult(detected, probability, threshold)
        self.calls = 0

    def detect(self, _text: str) -> ProfanityResult:
        self.calls += 1
        return self.result


class SpyContext:
    def __init__(self):
        self.calls = 0

    def needs_clarification(self, _query: str) -> bool:
        self.calls += 1
        return False


class SpyRouter:
    def __init__(self):
        self.calls = 0

    def classify(self, _query: str) -> dict:
        self.calls += 1
        return {"route": "L1", "technical": False, "reason": []}


class SpyRetriever:
    def __init__(self):
        self.calls = 0

    def retrieve_with_trace(self, _query: str, technical: bool = False) -> dict:
        self.calls += 1
        assert technical is False
        return {"results": [{"chunk_id": "official", "document_id": "official", "text": "official answer", "source_type": "official_manual", "authority": "official", "score": .8, "metadata": {}}], "official_bm25": [], "official_dense": [], "timing": {}}


class SpyGenerator:
    def __init__(self):
        self.calls = 0

    def answer(self, evidence: list[dict]) -> dict:
        self.calls += 1
        return {"answer": evidence[0]["text"], "used_evidence": True}


def test_clean_ml_result_continues_to_normal_pipeline():
    detector, context, router, retriever, generator = FakeDetector(False), SpyContext(), SpyRouter(), SpyRetriever(), SpyGenerator()
    result = RAGService(retriever, preprocessor=QueryPreprocessor(detector), context=context, router=router, generator=generator).ask("clean query")
    assert result["status"] == "ANSWER"
    assert detector.calls == context.calls == router.calls == retriever.calls == generator.calls == 1
    assert result["diagnostics"]["profanity_backend"] == "ml"
    assert result["diagnostics"]["profanity_detected"] is False


def test_profane_ml_result_stops_before_every_other_component():
    detector, context, router, retriever, generator = FakeDetector(True, .91, .5), SpyContext(), SpyRouter(), SpyRetriever(), SpyGenerator()
    result = RAGService(retriever, preprocessor=QueryPreprocessor(detector), context=context, router=router, generator=generator).ask("profane query")
    assert result["status"] == "REFUSE_PROFANITY"
    assert detector.calls == 1
    assert context.calls == router.calls == retriever.calls == generator.calls == 0
    assert result["diagnostics"]["retrieval_mode"] == "NONE"
    assert result["diagnostics"]["dense_candidates"] == result["diagnostics"]["bm25_candidates"] == 0
    assert result["diagnostics"]["profanity_probability"] == .91
    assert result["diagnostics"]["profanity_threshold"] == .5


def test_ml_detector_loads_once_reuses_model_and_honors_threshold(tmp_path, monkeypatch):
    from src.safety import profanity

    model_dir = tmp_path / "best_model"
    model_dir.mkdir()
    threshold_path = tmp_path / "threshold.json"
    threshold_path.write_text('{"threshold": 0.6}', encoding="utf-8")
    loads = {"count": 0}

    def fake_load(_path, device):
        loads["count"] += 1
        return object(), object()

    def fake_predict(texts, _tokenizer, _model, **kwargs):
        assert texts
        assert kwargs["batch_size"] == 8
        return [.6]

    monkeypatch.setattr(profanity, "_inference_utilities", lambda _src: (lambda: SimpleNamespace(type="cpu"), fake_load, fake_predict))
    detector = MLProfanityDetector(model_dir, threshold_path, classifier_src=tmp_path)
    assert detector.detect("first").detected is True
    assert detector.detect("second").detected is True
    assert loads["count"] == 1


def test_factory_constructs_one_configured_detector_for_the_service(tmp_path, monkeypatch):
    import src.application.factory as factory

    detector = FakeDetector(False)
    created = []

    def build(backend, model_dir, threshold_path):
        created.append((backend, model_dir, threshold_path))
        return detector

    monkeypatch.setattr(factory, "build_profanity_detector", build)
    monkeypatch.setattr(factory, "load_two_path_retriever", lambda *_args, **_kwargs: SpyRetriever())
    settings = Settings(data_dir=tmp_path, profanity_backend="rule")
    service = factory.build_rag_service(settings, official_dense=object())
    assert service.preprocessor.detector is detector
    assert len(created) == 1
