"""Client adapter for the separately hosted local Qwen generation worker."""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from time import perf_counter

from .generator import ExtractiveGenerator


class GenerationError(RuntimeError):
    """A generation failure that must never expose an ungrounded answer."""


class GenerationUnavailable(GenerationError):
    pass


class InvalidGeneration(GenerationError):
    def __init__(self, reason: str, raw_output: str, generation: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.raw_output = raw_output
        self.generation = generation or {}


@dataclass(frozen=True)
class GenerationResponse:
    text: str
    latency_ms: float
    model: str
    prompt_tokens: int | None = None
    generated_tokens: int | None = None
    truncated: bool = False
    finish_reason: str = "unknown"


class QwenGenerationClient:
    """Small NDJSON client; the worker, not the RAG process, owns model state."""

    def __init__(self, host: str, port: int, timeout_seconds: float = 45):
        self.host, self.port, self.timeout_seconds = host, port, timeout_seconds

    def _request(self, payload: dict) -> dict:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout_seconds) as connection:
                connection.settimeout(self.timeout_seconds)
                stream = connection.makefile("rwb")
                stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                stream.flush()
                raw = stream.readline()
        except (OSError, TimeoutError) as error:
            raise GenerationUnavailable(f"generation worker unavailable: {error}") from error
        if not raw:
            raise GenerationUnavailable("generation worker returned no response")
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GenerationError("generation worker returned malformed JSON") from error
        if not isinstance(response, dict):
            raise GenerationError("generation worker returned an invalid response")
        if response.get("error"):
            raise GenerationUnavailable(str(response["error"]))
        return response

    def status(self) -> dict:
        return self._request({"operation": "status"})

    def generate(self, prompt: str, max_new_tokens: int, max_seconds: float | None = None) -> GenerationResponse:
        started = perf_counter()
        payload = {"operation": "generate", "prompt": prompt, "max_new_tokens": max_new_tokens}
        if max_seconds is not None:
            payload["max_seconds"] = max_seconds
        response = self._request(payload)
        text = response.get("text")
        if not isinstance(text, str) or not text.strip():
            raise GenerationError("generation worker returned an empty answer")
        latency_ms = float(response.get("latency_ms", (perf_counter() - started) * 1000))
        prompt_tokens = response.get("prompt_tokens")
        generated_tokens = response.get("generated_tokens")
        finish_reason = str(response.get("finish_reason", "unknown"))
        truncated = bool(response.get("truncated", finish_reason == "length"))
        return GenerationResponse(text=text.strip(), latency_ms=latency_ms, model=str(response.get("model", "Qwen")),
                                  prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
                                  generated_tokens=int(generated_tokens) if generated_tokens is not None else None,
                                  truncated=truncated, finish_reason=finish_reason)


SYSTEM_PROMPT = """Ты — помощник Портала поставщиков. Отвечай только на основании фрагментов базы знаний.
Не используй внешние знания и не додумывай отсутствующие факты. Отвечай именно на вопрос пользователя,
кратко и понятно. Сохраняй точные суммы, сроки, проценты, названия меню и важные формулировки.
Если в фрагментах нет нужной информации, ответь только: НЕДОСТАТОЧНО_ДАННЫХ."""


def build_grounded_prompt(query: str, evidence: list[dict]) -> str:
    blocks: list[str] = []
    for number, item in enumerate(evidence, start=1):
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        blocks.append("[Источник {0}]\nchunk_id: {1}\ndocument_id: {2}\ntext: {3}".format(
            number, item.get("chunk_id", "unknown"), item.get("document_id", "unknown"), text))
    return f"{SYSTEM_PROMPT}\n\n" + "\n\n".join(blocks) + f"\n\nВопрос пользователя:\n{query}\n\nОтвет:"


def select_generation_evidence(evidence: list[dict], max_context_chars: int, max_chunks: int = 1,
                               query: str | None = None) -> list[dict]:
    """Bound generation-only context without changing selected retrieval evidence."""
    if query:
        terms = [token.casefold()[:5] for token in query.split() if len(token) >= 5]
        def relevance(item: dict) -> int:
            haystack = (str(item.get("title", "")) + " " + str(item.get("text", ""))).casefold()
            return sum(term in haystack for term in terms)
        evidence = sorted(evidence, key=relevance, reverse=True)
    selected, seen_ids, seen_text = [], set(), set()
    used = 0
    for item in evidence:
        text = str(item.get("text", "")).strip()
        chunk_id = str(item.get("chunk_id", ""))
        fingerprint = " ".join(text.casefold().split())
        if not text or not chunk_id or chunk_id in seen_ids or fingerprint in seen_text:
            continue
        # Retain whole chunks only: source IDs and supported facts stay intact.
        if selected and used + len(text) > max_context_chars:
            continue
        selected.append(dict(item))
        used += len(text)
        seen_ids.add(chunk_id)
        seen_text.add(fingerprint)
        if used >= max_context_chars or len(selected) >= max_chunks:
            break
    return selected


class QwenGenerator:
    backend = "qwen"

    def __init__(self, client: QwenGenerationClient, *, model_name: str = "Qwen2.5-1.5B-Instruct", max_new_tokens: int = 128,
                 max_seconds: float = 90,
                 max_context_chars: int = 12000,
                 max_evidence_chunks: int = 1,
                 allow_extractive_fallback: bool = False):
        self.client = client
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.max_seconds = max_seconds
        self.max_context_chars = max_context_chars
        self.max_evidence_chunks = max_evidence_chunks
        self.allow_extractive_fallback = allow_extractive_fallback
        self._fallback = ExtractiveGenerator()

    def answer(self, evidence: list[dict], *, query: str | None = None) -> dict:
        if not query:
            raise GenerationError("Qwen generator requires the original user query")
        try:
            selected = select_generation_evidence(evidence, self.max_context_chars, self.max_evidence_chunks, query)
            prompt = build_grounded_prompt(query, selected)
            response = self.client.generate(prompt, self.max_new_tokens, self.max_seconds)
            retry_attempted = False
            invalid_reason = self._invalid_reason(response.text, response.generated_tokens, self.max_new_tokens,
                                                  response.truncated, response.finish_reason)
            # The model can have correct grounded evidence but reach the output
            # cap mid-sentence. Retry once only, with a bounded larger budget.
            if invalid_reason == "truncated_output":
                retry_attempted = True
                retry_budget = min(self.max_new_tokens * 2, 512)
                response = self.client.generate(prompt, retry_budget, self.max_seconds)
                invalid_reason = self._invalid_reason(response.text, response.generated_tokens, retry_budget,
                                                      response.truncated, response.finish_reason)
            generation = self._diagnostics(response, selected, prompt, retry_attempted)
            if invalid_reason:
                raise InvalidGeneration(invalid_reason, response.text, generation)
            if response.text == "НЕДОСТАТОЧНО_ДАННЫХ":
                raise GenerationError("model indicated insufficient evidence")
            return {"answer": response.text, "used_evidence": True, "generation": generation}
        except GenerationError:
            if not self.allow_extractive_fallback:
                raise
            result = self._fallback.answer(evidence, query=query)
            result["generation"] = {"backend": self.backend, "invoked": True, "model": self.model_name,
                                    "latency_ms": 0.0, "fallback_used": True}
            return result

    def _diagnostics(self, response: GenerationResponse, selected: list[dict], prompt: str,
                     retry_attempted: bool) -> dict:
        return {"backend": self.backend, "invoked": True, "model": response.model,
                "latency_ms": response.latency_ms, "fallback_used": False,
                "evidence_chunk_count": len(selected),
                "context_characters": sum(len(str(item.get("text", ""))) for item in selected),
                "prompt_characters": len(prompt), "prompt_tokens": response.prompt_tokens,
                "generated_tokens": response.generated_tokens,
                "max_new_tokens": self.max_new_tokens * 2 if retry_attempted else self.max_new_tokens,
                "max_seconds": self.max_seconds, "truncated": response.truncated,
                "finish_reason": response.finish_reason,
                "retry_attempted": retry_attempted, "retry_count": int(retry_attempted)}

    @staticmethod
    def _invalid_reason(text: str, generated_tokens: int | None = None, max_new_tokens: int | None = None,
                        truncated: bool = False, finish_reason: str = "unknown") -> str | None:
        normalized = " ".join(text.casefold().strip(" .,!?:;—-").split())
        if not normalized:
            return "empty_output"
        if len(normalized) < 3:
            return "truncated_output"
        hit_token_limit = truncated or finish_reason == "length" or (
            generated_tokens is not None and max_new_tokens is not None and generated_tokens >= max_new_tokens)
        unfinished_prefixes = ("\u0437\u0430\u0433", "\u043f\u0435\u0440")
        unmatched_open_quote = normalized.count("\u00ab") > normalized.count("\u00bb")
        obvious_fragment = normalized.endswith(unfinished_prefixes) or unmatched_open_quote
        if hit_token_limit or (finish_reason == "time_limit" and (normalized[-1].isalnum() or unmatched_open_quote)) or obvious_fragment:
            return "truncated_output"
        refusals = ("недостаточно данных", "недостаточно информации", "нет информации", "не могу ответить", "не знаю")
        return "insufficient_data_refusal" if any(phrase in normalized for phrase in refusals) else None
