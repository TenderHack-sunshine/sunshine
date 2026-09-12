# Tender Hack 2026 — local RAG MVP

## Docker profile

The supported runtime is one Docker Compose stack: PostgreSQL, Qdrant, a
Qwen3 embedding worker, Ollama with `qwen3:1.7b`, the RAG API, Go API, and
frontend. `docker compose up --build -d` downloads the Qwen model once into a
named Docker volume; the first start is therefore much longer than subsequent
starts. Open `http://localhost:5173` after all services are healthy.

The answer model is Qwen3 1.7B (Ollama's CPU quantized build). It is invoked only
after retrieval and safety gates, receives the user question plus up to three
complete, deduplicated evidence chunks (configurable with
`GENERATION_MAX_EVIDENCE_CHUNKS`). It has a 50-second generation budget within
the one-minute end-to-end API deadline and must pass post-generation grounding. No host
Python worker or `host.docker.internal` dependency is required.

## Data and extraction audit

Run the audits from `rag/` after every corpus refresh:

```powershell
python scripts/audit_corpus.py --output data/processed/audit/corpus_audit.json
python scripts/audit_pdfs.py --output data/processed/audit/pdf_extraction_audit.json
```

The corpus audit checks every supplied local PDF/XLSX against canonical chunk
metadata. It deliberately reports `UNVERIFIABLE_NO_SOURCE_EXPORT` when the
raw `zakupki.mos.ru` knowledge-base export is absent: 253 KB chunks do **not**
prove that the public site was ingested completely. The PDF report records pages
with no extracted text, very short text, or image-heavy/low-text layout. OCR is
not installed or run by this script; its purpose is a reproducible list of
possible extraction losses before deciding whether OCR is needed.

## Evidence, FAQ, and safety limits

Context selection keeps whole chunks within `GENERATION_MAX_CONTEXT_CHARS`,
removes exact duplicates, limits repeated documents, and reserves the protected
official tier ahead of historical tickets. Adjacent compacted chunks from one
instruction may remain together. Retrieval scores are not changed. Response
diagnostics list the original chunk IDs actually sent to the generator.

The post-generation check is a deliberately conservative local lexical and
numeric guard, not a guarantee of factual correctness. Unsupported substantive
claims or values cause `ESCALATE_TO_OPERATOR`; human review is still required
for legal or high-impact answers.

`data/processed/faq/cards.jsonl` is optional. Runtime uses only cards marked
`verified=true` and `review_status=VERIFIED` with current, official source
chunk IDs. Pending, stale, or source-less cards are ignored and normal RAG is
used instead. Generate review-only drafts with:

```powershell
python scripts/draft_faq_cards.py --output data/processed/faq/drafts.jsonl --limit 10
```

## Active retrieval path

The active MVP uses two independent retrieval paths:

```text
query -> moderation -> normalization -> technical router
      -> Qwen3 + Qdrant (official_kb, official_manual, support_taxonomy only)
      -> Dense-primary ranking of official evidence
      -> BM25 rescue only when dense evidence is weak; BM25 fallback if Dense is unavailable
      -> ticket document diversity -> extractive evidence
```

The official dense collection is named `zakupki_official` and never contains
`support_ticket` records. The indexer writes
`data/processed/index/official_index_manifest.json` only after it indexes the
complete current canonical official set; runtime validates that manifest and
the Qdrant count before enabling dense search. `OFFICIAL_EXPECTED_POINTS=1073`
is only a legacy fallback for old installations with no manifest. After adding
data, run `scripts/prepare_index.py`, then rerun
`scripts/index_official_qdrant.py`; do not edit the count merely to accept a
partial index. Qdrant is optional at runtime: an unavailable collection,
Qdrant error, embedding error, or dense-query timeout explicitly selects the
lightweight official BM25 fallback; the CLI prints `dense_available=false` and
`fallback_used=true`.

On the Windows Intel host, start the persistent local Qwen worker once before serving requests. It loads and warms the model once, then the RAG process uses Qdrant only via REST/HTTP.

```powershell
# Start once in a separate terminal; verify it is ready before serving traffic.
python -u scripts/embedding_worker.py
python scripts/embedding_worker.py --status

# End-to-end application; it uses fallback BM25 until the complete collection is available.
python scripts/ask.py "как добавить МЧД"

# Separate resumable overnight job. Do not use --recreate when resuming.
python -u scripts/index_official_qdrant.py --batch-size 1 --log-every 25

# PowerShell background job with durable logs.
Start-Process python -ArgumentList '-u','scripts/index_official_qdrant.py','--batch-size','1','--log-every','25' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput data/processed/index/official_index.log -RedirectStandardError data/processed/index/official_index.err.log

```

`scripts/ask.py` is the stable end-to-end entry point. It uses `dense_available=false` and `fallback_used=true` until the current official-index manifest and Qdrant count agree and the persistent worker is ready; it never attempts dense embedding of the 25,044 historical tickets.

## Demo preflight

Run the demo from `rag/` in this order. The production demo profile uses a
deterministic local profanity gate with no model or network dependency.

```powershell
# Terminal 1 — start once and keep this process running.
python -u scripts/embedding_worker.py

# Terminal 2 — validates ML profanity, data, BM25, worker and Qdrant.
python scripts/check_demo_health.py --profanity-backend rule --load-profanity

# Terminal 3 — use the same ML profile for the CLI or HTTP adapter.
python scripts/ask.py "как добавить МЧД"
# python scripts/serve.py --port 8000
```

Before the presentation, also run the reviewable ML E2E suite:

```powershell
python scripts/run_e2e_demo_eval.py data/eval/e2e_demo_scenarios.jsonl --profanity-backend rule
python scripts/build_final_demo_reports.py
python -m pytest -q
```

The profanity gate is deterministic and uses compiled local rules; it does not
need `best_model/`, `threshold.json`, Torch, or transformers. The runner writes reviewable JSON and Markdown reports under
`data/processed/eval/`; `ANSWER` scenarios stay marked `REVIEW` until a person
checks `final_grounding_review.md`.

### Pre-demo checklist

- [ ] deterministic profanity smoke cases passed
- [ ] Qwen embedding worker alive
- [ ] Qdrant healthy; `official_index_manifest.json` matches `zakupki_official`
- [ ] ticket BM25 index present
- [ ] `RERANKER_ENABLED=0`
- [ ] `RETRIEVAL_STRATEGY=dense_primary`
- [ ] `CONFIDENCE_MIN_OFFICIAL_SCORE=0.60`
- [ ] `CLARIFICATION_POLICY_ENABLED=1`
- [ ] `python -m pytest -q` is green

With the manifest-validated official collection and the worker ready, the default is `dense_primary`: Qdrant dense ranks official evidence. BM25 is retrieved cheaply for conservative recall rescue when the Dense result is weak and as the full fallback when Dense is unavailable. L3 additionally queries ticket BM25; tickets are never dense-indexed. `hybrid_rrf` and `bm25_only` remain available as explicit experimental strategies.

Локальный ассистент поддержки Портала поставщиков Москвы. Проект не вызывает внешние LLM/API и не скачивает веса моделей автоматически. Ответ формируется только из найденного evidence или заменяется передачей оператору.

## Текущий статус данных

Ingestion завершён и не является частью текущего retrieval workflow.

| Источник | Chunks | Семантика |
| --- | ---: | --- |
| Knowledge Base | 253 | `official_kb` / `official` |
| PDF-инструкции | 734 | `official_manual` / `official` |
| Исторические обращения | 25,044 | `support_ticket` / `case_history` |
| Таксономия обращений | 86 | `support_taxonomy` / `taxonomy` |
| Всего local + KB | 26,117 | canonical corpus |

Canonical preparation валидирует отсутствие пустого текста и повторяющихся `chunk_id`. Оригинальные JSONL не изменяются.

## Архитектура MVP на Intel-only ноутбуке

```text
Запрос
  -> profanity rejection
  -> typo/format normalization
  -> context analysis and L1 / L2 / L3 router
  -> official evidence search (dense only after a complete REST Qdrant index)
  -> [только L3] BM25 по historical tickets
  -> weighted Reciprocal Rank Fusion
  -> optional reranker hook
  -> document diversity для tickets
  -> confidence + evidence sufficiency: answer / clarification / operator
  -> [ANSWER only] Docker-hosted Ollama Qwen3 8B
  -> post-generation grounding guard
```

Для текущего Intel Iris Xe ноутбука full-corpus Qwen3 embedding не запускается: CPU inference 26k tickets занимает непрактичное время. Вместо этого:

- До завершения ночного job `official_kb`, `official_manual`, `support_taxonomy` ищутся через lightweight official retriever. После появления ровно 1,073 REST-Qdrant points runtime автоматически использует Qwen3 + Qdrant dense path.
- `support_ticket` индексируется полностью локальным Russian BM25.
- Historical tickets добавляются только к technical/error запросам и не могут занять весь top-k: RRF weights настраиваются отдельно, а для tickets ограничен повтор одного `document_id`.

RRF объединяет ранги, а не сравнивает raw BM25 score с cosine similarity.

## Структура

- `src/ingestion/` — готовые парсеры и chunking; их не нужно запускать для обычного поиска.
- `src/retrieval/canonical.py` — canonical merge и validation.
- `src/retrieval/bm25.py` — dependency-free Russian inverted-index BM25.
- `src/retrieval/mvp.py` — two-path retrieval, RRF, source priority и diversity.
- `src/application/` — стабильные contracts, RAGService, clarification, routing и confidence decision.
- `src/retrieval/vector_store.py` — REST-only Qdrant adapter, безопасный рядом с Torch на Windows.
- `src/retrieval/embeddings/qwen3.py` — сохранённый локальный Qwen3 embedding component.
- `src/moderation/`, `src/routing/`, `src/generation/` — раннее отклонение profanity, нормализация, routing и отдельный local Qwen generation adapter.
- `data/raw/`, `data/processed/`, `data/indexes/`, `models/` — локальные данные, generated artifacts и веса; они не коммитятся.

## Установка

Нужен Python 3.10+.

```powershell
python -m pip install -e ".[dev]"
```

При необходимости скопируйте `.env.example` в `.env`. Все пути в конфигурации относительны к корню `rag/`.

## Быстрый запуск MVP

Выполняйте команды из папки `rag/`.

```powershell
# 1. Собрать и проверить canonical corpus
python scripts/prepare_index.py

# 2. Построить BM25 по всем 25k historical tickets
python scripts/build_ticket_bm25.py

# 3. Выполнить end-to-end поиск
python scripts/ask.py "ошибка при добавлении МЧД"
```

Ориентировочные показатели на hackathon laptop:

- BM25 build: ~6–20 секунд;
- 43,991 уникальных нормализованных terms;
- сериализованный ticket index: ~83 MB;
- non-technical query: около 1 ms;
- technical query с ticket path: около 14–30 ms.

Примеры запросов:

```powershell
python scripts/ask.py "как добавить МЧД"
python scripts/ask.py "как создать оферту"
python scripts/ask.py "как зарегистрироваться поставщику"
python scripts/ask.py "не подписывается оферта"
python scripts/ask.py "не открывается котировочная сессия"
```

Non-technical queries возвращают official evidence. Technical queries возвращают official evidence первым и добавляют relevant historical ticket как supporting troubleshooting context.

## Ночной official-only Qwen3 + Qdrant индекс

Используется только локальная `models/qwen3-embedding-0.6b`. Через Qdrant REST индексируются ровно 1,073 official chunks: `official_kb`, `official_manual`, `support_taxonomy`. `support_ticket` никогда не попадает в dense collection.

На Windows Torch работает в отдельном embedding-процессе, а основной индексатор использует HTTP/REST к `localhost:6333`; Python Qdrant client рядом с Torch не загружается.

```powershell
# Старт или продолжение отдельного overnight job
python -u scripts/index_official_qdrant.py --batch-size 1 --log-every 25

# Намеренно начать с нуля (удаляет collection и checkpoint)
python -u scripts/index_official_qdrant.py --recreate --batch-size 1 --log-every 25
```

Collection называется `zakupki_official`; vectors имеют dimension 1024 и cosine distance. Точки строятся из стабильного `chunk_id`, checkpoint находится в `data/processed/index/official_index_checkpoint.json`. При обычном повторном запуске уже подтверждённые batches не вычисляются заново. Progress и ошибки записываются в `official_index.log` и `official_index.err.log` при фоновом запуске из верхней команды README.

## Retrieval evaluation and optional reranking

Offline evaluation uses JSONL. Every newly reviewed row should declare
`label_provenance` as one of `HUMAN_LABELLED`, `MODEL_REVIEWED`, `SILVER`, or
`PENDING_HUMAN_REVIEW`. Only `HUMAN_LABELLED` items may be described as ground
truth; the evaluator preserves all other groups as diagnostics and never
upgrades them automatically.

```json
{"query":"как добавить МЧД","route":"L1","relevant_chunk_ids":["..."],"relevant_document_ids":["..."],"expected_decision":"ANSWER","notes":"optional"}
```

`relevant_chunk_ids` and `relevant_document_ids` are optional. Unlabelled rows still provide diagnostics and latency, but are deliberately excluded from Recall/MRR rather than receiving invented labels.

Use the terminal labeler to review the current 30-query dataset. It displays compact hybrid evidence and writes atomically, preserving `query`, route and expected decision. Every save creates `retrieval_eval.jsonl.bak`.

```powershell
python scripts/label_retrieval_eval.py data/eval/retrieval_eval.jsonl
```

Commands: `1 3` adds both chunk/document labels, `c 1` adds chunk-only, `d 1` adds document-only, `r 1 3` explicitly replaces, `note text` saves a note, `s` skips, `n` marks none relevant, and `q` saves then exits.

```powershell
python scripts/evaluate_retrieval.py data/eval/retrieval_eval.jsonl --output data/processed/eval/retrieval_eval_report.json --markdown data/processed/eval/retrieval_eval_report.md
```

Add `--markdown data/processed/eval/retrieval_eval_report.md` for a presentation-friendly report. The report compares `BM25`, `DENSE`, `HYBRID` and `HYBRID_RERANKED`, calculates separate chunk/document Recall/HitRate at 1/3/5/10 and MRR@10, reports route/category groups, route/decision accuracy, compact groundedness diagnostics, failure analysis, and p50/p95 latency.

Reranking is optional. `RERANKER_ENABLED=0` is the safe default (`RERANK_ENABLED` remains compatible); when enabled, a local compatible CrossEncoder is used only on `HYBRID_RERANK_TOP_N=20` candidates. A load or inference failure keeps the RRF order and does not fail the request. The default final evidence size is `FINAL_TOP_K=5`.

## Что намеренно не включено

- slow Qwen reranking (есть отключённый hook, `RERANK_ENABLED=0`);
- генеративный LLM-ответ;
- full dense embedding historical tickets на CPU;
- изменения ingestion/parsing pipeline.

### Local answer synthesis

`GENERATOR_BACKEND=qwen` uses Docker-hosted Ollama with `qwen3:1.7b`. It is not
the Qwen embedding worker and does not change Dense/BM25/Qdrant retrieval. The
model is downloaded once into a Docker volume at first Compose startup.

```powershell
docker compose up --build -d
docker compose ps
```

Generation is called only after profanity, clarification, retrieval, confidence and evidence-sufficiency gates return `ANSWER`. A worker failure, timeout, empty output, or failed post-generation grounding returns `ESCALATE_TO_OPERATOR`; extractive fallback is opt-in and disabled by default. Internal diagnostics expose backend, invocation, logical model name, latency, grounding result, and fallback usage without exposing a filesystem path.

## Тесты

```powershell
python -m pytest -q
```

Тесты используют fixtures/mocks или локальный temporary Qdrant и не требуют model download, GPU либо запущенного Qdrant service.

## HTTP adapter for backend

После подготовки canonical corpus `data/processed/index/all_chunks.jsonl` и
ticket BM25 index `data/indexes/support_tickets_bm25.pkl` запустите
существующий RAG pipeline как HTTP-сервис для backend:

```powershell
$env:USE_QDRANT = "0"
python scripts/serve.py --port 8000
```

Адаптер предоставляет `GET /health` и `POST /process`. Он вызывает уже
существующие moderation, retrieval и confidence gate и возвращает backend
статусы `answered`, `need_clarification`, `blocked` или `escalated`; правила
для этих статусов определены в `src/application/pipeline.py`. Для моделей вне `rag/models`
укажите `MODEL_DIR`; в текущем workspace это `../../models` при запуске из
папки `rag/`.
