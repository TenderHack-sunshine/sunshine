"""HTTP client for the Docker-hosted Ollama Qwen3 generation server."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
    """Client for Ollama's local HTTP API.

    The model server is deliberately a separate Docker service.  That keeps
    the RAG API small and means one loaded Qwen3 model serves every request.
    """

    def __init__(self, host: str, port: int, timeout_seconds: float = 12, model: str = "qwen3:1.7b"):
        self.host, self.port, self.timeout_seconds, self.model = host, port, timeout_seconds, model

    def _request(self, method: str, path: str, payload: dict | None = None, *, timeout: float | None = None) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(
            f"http://{self.host}:{self.port}{path}", data=body, method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urlopen(request, timeout=timeout or self.timeout_seconds) as response:
                raw = response.read()
        except (HTTPError, URLError, OSError, TimeoutError) as error:
            raise GenerationUnavailable(f"generation server unavailable: {error}") from error
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GenerationError("generation server returned malformed JSON") from error
        if not isinstance(response, dict):
            raise GenerationError("generation server returned an invalid response")
        if response.get("error"):
            raise GenerationUnavailable(str(response["error"]))
        return response

    def status(self) -> dict:
        tags = self._request("GET", "/api/tags", timeout=min(self.timeout_seconds, 5))
        models = tags.get("models") if isinstance(tags.get("models"), list) else []
        available = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
        if self.model not in available:
            raise GenerationUnavailable(f"{self.model} model is still loading")
        return {"ready": True, "model": self.model}

    def generate(self, prompt: str, max_new_tokens: int, max_seconds: float | None = None) -> GenerationResponse:
        started = perf_counter()
        # Keep instructions in the API's system role.  Supplying them as the
        # first part of a long user message made the small model favour copying
        # the evidence that followed instead of composing an answer.
        user_prompt = prompt.removeprefix(SYSTEM_PROMPT).lstrip()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            # The UI has a strict interactive latency budget.  A bounded
            # context also prevents a local CPU model from exhausting RAM.
            "options": {"temperature": 0.15, "top_p": 0.9, "num_predict": max_new_tokens, "num_ctx": 4096},
            "think": False,
            "stream": False,
            # Keep the already loaded local model resident between support
            # requests.  This avoids spending most of the one-minute budget on
            # a repeat model load.
            "keep_alive": "15m",
        }
        response = self._request("POST", "/api/chat", payload,
                                 timeout=min(self.timeout_seconds, max_seconds or self.timeout_seconds))
        message = response.get("message") if isinstance(response.get("message"), dict) else {}
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise GenerationError("generation server returned an empty answer")
        prompt_tokens = response.get("prompt_eval_count")
        generated_tokens = response.get("eval_count")
        finish_reason = str(response.get("done_reason", "unknown"))
        truncated = finish_reason in {"length", "max_tokens"}
        return GenerationResponse(text=text.strip(), latency_ms=(perf_counter() - started) * 1000,
                                  model=str(response.get("model") or self.model),
                                  prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
                                  generated_tokens=int(generated_tokens) if generated_tokens is not None else None,
                                  truncated=truncated, finish_reason=finish_reason)


SYSTEM_PROMPT = """Ты — помощник Портала поставщиков. Отвечай только на основании фрагментов базы знаний.
Не используй внешние знания и не додумывай отсутствующие факты. Отвечай именно на вопрос пользователя,
кратко и понятно.

Обязательный формат: один абзац, максимум 80 слов и четыре предложения. Сначала дай прямой ответ,
затем опиши только подтверждённые действия или условия. Не копируй фрагмент источника целиком,
не добавляй заголовки «Прямой ответ» или «Подтверждённые действия», нумерацию, ссылки или факты,
которых нет в источниках. Сохраняй точные суммы, сроки,
проценты, названия меню и важные формулировки.
Если в источнике для ошибки есть и причина, и действие, дай их как минимум в двух полных предложениях:
сначала причина, затем конкретный следующий шаг.
Если в фрагментах нет нужной информации, ответь только: НЕДОСТАТОЧНО_ДАННЫХ."""


def clean_generated_answer(text: str) -> str:
    """Remove a recurring Qwen presentation template, without adding content.

    The model occasionally emits a second, unsupported checklist despite the
    prompt.  The direct-answer paragraph is kept verbatim; only the template
    label and its redundant tail are removed.  This is output normalisation,
    not a canned answer or a retrieval shortcut.
    """
    value = text.strip()
    value = re.sub(r"^\s*прямой\s+ответ\s*:\s*", "", value, flags=re.IGNORECASE)
    value = re.split(r"\s*подтвержд[её]нные\s+действия\s*:\s*", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return " ".join(value.split())


def build_grounded_prompt(query: str, evidence: list[dict]) -> str:
    blocks: list[str] = []
    for number, item in enumerate(evidence, start=1):
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        blocks.append("[Источник {0}]\nchunk_id: {1}\ndocument_id: {2}\ntext: {3}".format(
            number, item.get("chunk_id", "unknown"), item.get("document_id", "unknown"), text))
    return f"{SYSTEM_PROMPT}\n\n" + "\n\n".join(blocks) + f"\n\nВопрос пользователя:\n{query}\n\nОтвет:"


def select_generation_evidence(evidence: list[dict], max_context_chars: int, max_chunks: int = 3,
                               query: str | None = None) -> list[dict]:
    """Select complete, deduplicated chunks for generation without touching scores.

    Retrieval has already ranked the candidates.  This function only removes
    duplicates and applies a context budget; it deliberately never rewrites a
    retrieval score.  Official sources form a protected tier, so a historical
    ticket cannot consume the context ahead of an available instruction.
    """
    priority = {"official": 0, "taxonomy": 1, "case_history": 2}
    query_terms = [token.casefold()[:5] for token in (query or "").split() if len(token) >= 5]

    def relevance(item: dict) -> int:
        haystack = (str(item.get("title", "")) + " " + str(item.get("text", ""))).casefold()
        return sum(term in haystack for term in query_terms)

    # Query affinity breaks ties only *inside* an authority tier.  Original
    # ranking remains the final tie-breaker and is never rewritten.
    ordered = sorted(
        enumerate(evidence),
        key=lambda pair: (priority.get(pair[1].get("authority"), 1), -relevance(pair[1]), pair[0]),
    )
    selected, seen_ids, seen_text = [], set(), set()
    per_document: dict[str, int] = {}
    used = 0
    for _, item in ordered:
        text = str(item.get("text", "")).strip()
        chunk_id = str(item.get("chunk_id", ""))
        fingerprint = " ".join(text.casefold().split())
        if not text or not chunk_id or chunk_id in seen_ids or fingerprint in seen_text:
            continue
        document_id = str(item.get("document_id") or chunk_id)
        if per_document.get(document_id, 0) >= 2:
            continue
        # Retain whole chunks only: source IDs and supported facts stay intact.
        if used + len(text) > max_context_chars:
            continue
        selected.append(dict(item))
        used += len(text)
        seen_ids.add(chunk_id)
        seen_text.add(fingerprint)
        per_document[document_id] = per_document.get(document_id, 0) + 1
        if used >= max_context_chars or len(selected) >= max_chunks:
            break
    return selected


class QwenGenerator:
    backend = "qwen"

    def __init__(self, client: QwenGenerationClient, *, model_name: str = "Qwen3-8B-Q4_K_M", max_new_tokens: int = 128,
                 max_seconds: float = 90,
                 max_context_chars: int = 12000,
                 max_evidence_chunks: int = 3,
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
        started = perf_counter()
        try:
            # Avoid putting an interactive request behind Ollama's model-load
            # queue.  If the configured model is absent, take the explicitly
            # allowed grounded extractive path immediately.
            status = getattr(self.client, "status", None)
            if callable(status):
                status()
            selected = select_generation_evidence(evidence, self.max_context_chars, self.max_evidence_chunks, query)
            prompt = build_grounded_prompt(query, selected)
            response = self.client.generate(prompt, self.max_new_tokens, self.max_seconds)
            retry_attempted = False
            answer = clean_generated_answer(response.text)
            invalid_reason = self._invalid_reason(answer, response.generated_tokens, self.max_new_tokens,
                                                  response.truncated, response.finish_reason)
            # The model can have correct grounded evidence but reach the output
            # cap mid-sentence. Retry once only, with a bounded larger budget.
            if invalid_reason == "truncated_output":
                retry_attempted = True
                retry_budget = min(self.max_new_tokens * 2, 512)
                # Both attempts share one interactive budget.  Previously a
                # 10-second request could be retried for another 10 seconds;
                # with a one-minute SLA that would quietly exceed the caller's
                # deadline.
                remaining_seconds = self.max_seconds - (perf_counter() - started)
                if remaining_seconds <= 1:
                    raise InvalidGeneration(invalid_reason, response.text,
                                            self._diagnostics(response, selected, prompt, retry_attempted))
                response = self.client.generate(prompt, retry_budget, remaining_seconds)
                answer = clean_generated_answer(response.text)
                invalid_reason = self._invalid_reason(answer, response.generated_tokens, retry_budget,
                                                      response.truncated, response.finish_reason)
            generation = self._diagnostics(response, selected, prompt, retry_attempted)
            if invalid_reason:
                raise InvalidGeneration(invalid_reason, response.text, generation)
            if answer == "НЕДОСТАТОЧНО_ДАННЫХ":
                raise GenerationError("model indicated insufficient evidence")
            return {"answer": answer, "used_evidence": True, "generation": generation}
        except GenerationError:
            if not self.allow_extractive_fallback:
                raise
            result = self._fallback.answer(evidence, query=query)
            result["generation"] = {"backend": self.backend, "invoked": True, "model": self.model_name,
                                    "latency_ms": 0.0, "fallback_used": True}
            return result

    def _diagnostics(self, response: GenerationResponse, selected: list[dict], prompt: str,
                     retry_attempted: bool) -> dict:
        # ``compact_evidence`` may make one generator item out of neighbouring
        # source chunks.  Surface both the compact item and its original IDs so
        # an operator can see exactly what evidence reached the prompt.
        source_chunk_ids = [
            source_id
            for item in selected
            for source_id in item.get("merged_chunk_ids", [item.get("chunk_id")])
            if source_id
        ]
        return {"backend": self.backend, "invoked": True, "model": response.model,
                "latency_ms": response.latency_ms, "fallback_used": False,
                "evidence_chunk_count": len(selected),
                "evidence_chunk_ids": source_chunk_ids,
                "evidence_document_ids": [item.get("document_id") for item in selected],
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
