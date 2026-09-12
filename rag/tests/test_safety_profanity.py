from __future__ import annotations

from src.application.pipeline import QueryPreprocessor, RAGService
from src.core.config import Settings
from src.safety.profanity import ProfanityResult, RuleProfanityDetector


class FakeDetector:
    backend = "rule"

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


def test_clean_rule_result_continues_to_normal_pipeline():
    detector, context, router, retriever, generator = FakeDetector(False), SpyContext(), SpyRouter(), SpyRetriever(), SpyGenerator()
    result = RAGService(retriever, preprocessor=QueryPreprocessor(detector), context=context, router=router, generator=generator).ask("clean query")
    assert result["status"] == "ANSWER"
    assert detector.calls == router.calls == retriever.calls == generator.calls == 1
    assert context.calls == 0
    assert result["diagnostics"]["profanity_backend"] == "rule"
    assert result["diagnostics"]["profanity_detected"] is False


def test_profane_rule_result_stops_before_every_other_component():
    detector, context, router, retriever, generator = FakeDetector(True, .91, .5), SpyContext(), SpyRouter(), SpyRetriever(), SpyGenerator()
    result = RAGService(retriever, preprocessor=QueryPreprocessor(detector), context=context, router=router, generator=generator).ask("profane query")
    assert result["status"] == "REFUSE_PROFANITY"
    assert detector.calls == 1
    assert context.calls == router.calls == retriever.calls == generator.calls == 0
    assert result["diagnostics"]["retrieval_mode"] == "NONE"
    assert result["diagnostics"]["dense_candidates"] == result["diagnostics"]["bm25_candidates"] == 0
    assert result["diagnostics"]["profanity_probability"] == .91
    assert result["diagnostics"]["profanity_threshold"] == .5


def test_rule_detector_requires_no_model_or_threshold_files(tmp_path):
    detector = RuleProfanityDetector()
    result = detector.detect("\u044d\u0442\u043e \u0445\u0443\u0439\u043d\u044f")
    assert result.detected is True
    assert result.probability == 1.0
    assert result.threshold == 1.0
    assert result.match_type in {"exact", "root"}
    assert not list(tmp_path.iterdir())


def test_factory_constructs_one_configured_detector_for_the_service(tmp_path, monkeypatch):
    import src.application.factory as factory

    detector = FakeDetector(False)
    created = []

    def build(backend):
        created.append(backend)
        return detector

    monkeypatch.setattr(factory, "build_profanity_detector", build)
    monkeypatch.setattr(factory, "load_two_path_retriever", lambda *_args, **_kwargs: SpyRetriever())
    settings = Settings(data_dir=tmp_path, profanity_backend="rule")
    service = factory.build_rag_service(settings, official_dense=object())
    assert service.preprocessor.detector is detector
    assert len(created) == 1
