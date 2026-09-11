# Tender Hack 2026 — local RAG MVP

## Active retrieval path

The active MVP uses two independent retrieval paths:

```text
query -> moderation -> normalization -> technical router
      -> Qwen3 + Qdrant (official_kb, official_manual, support_taxonomy only)
      -> BM25 (support_ticket only, and only for technical requests)
      -> reciprocal-rank fusion -> ticket document diversity -> extractive evidence
```

The official dense collection is named `zakupki_official`. It must contain exactly 1,073 points and never contains `support_ticket` records. Qdrant is optional at runtime: an unavailable collection, Qdrant error, embedding error, or dense-query timeout explicitly selects the lightweight official BM25 fallback; the CLI prints `dense_available=false` and `fallback_used=true`.

```powershell
# End-to-end application; it uses fallback BM25 until the complete collection is available.
python scripts/ask.py "как добавить МЧД"

# Separate resumable overnight job. Do not use --recreate when resuming.
python -u scripts/index_official_qdrant.py --batch-size 1 --log-every 25

# PowerShell background job with durable logs.
Start-Process python -ArgumentList '-u','scripts/index_official_qdrant.py','--batch-size','1','--log-every','25' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput data/processed/index/official_index.log -RedirectStandardError data/processed/index/official_index.err.log

```

`scripts/ask.py` is the stable end-to-end entry point. It uses `dense_available=false` and `fallback_used=true` until REST Qdrant reports exactly 1,073 official points; it never attempts dense embedding of the 25,044 historical tickets.

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
  -> confidence decision: answer / clarification / operator
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
- `src/moderation/`, `src/routing/`, `src/generation/` — раннее отклонение profanity, нормализация, routing, extractive fallback.
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

## Что намеренно не включено

- slow Qwen reranking (есть отключённый hook, `RERANK_ENABLED=0`);
- генеративный LLM-ответ;
- full dense embedding historical tickets на CPU;
- изменения ingestion/parsing pipeline.

Текущий generator — extractive: он показывает лучший источник. При отсутствии достаточного evidence отдаёт операторский fallback; profanity отклоняется до retrieval.

## Тесты

```powershell
python -m pytest -q
```

Тесты используют fixtures/mocks или локальный temporary Qdrant и не требуют model download, GPU либо запущенного Qdrant service.

## HTTP adapter for backend

После подготовки `data/processed/*chunks.jsonl` запустите существующий RAG
pipeline как HTTP-сервис для backend:

```powershell
$env:USE_QDRANT = "0"
python scripts/serve.py --port 8000
```

Адаптер предоставляет `GET /healthz` и `POST /v1/process`. Он вызывает уже
существующие moderation, retrieval и confidence gate и возвращает backend
статусы `answered`, `blocked` или `escalated`. Для моделей вне `rag/models`
укажите `MODEL_DIR`; в текущем workspace это `../../models` при запуске из
папки `rag/`.
