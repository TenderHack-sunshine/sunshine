# Tender Hack 2026 — локальный RAG MVP

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
  -> technical / non-technical router
  -> official evidence search
  -> [только technical] BM25 по historical tickets
  -> weighted Reciprocal Rank Fusion
  -> document diversity для tickets
  -> extractive evidence или operator fallback
```

Для текущего Intel Iris Xe ноутбука full-corpus Qwen3 embedding не запускается: CPU inference 26k tickets занимает непрактичное время. Вместо этого:

- `official_kb`, `official_manual`, `support_taxonomy` ищутся через local official retriever; Qwen3 + Qdrant dense path сохранён для будущего ускоренного оборудования.
- `support_ticket` индексируется полностью локальным Russian BM25.
- Historical tickets добавляются только к technical/error запросам и не могут занять весь top-k: официальный источник имеет более высокий RRF weight, а для tickets ограничен повтор одного `document_id`.

RRF объединяет ранги, а не сравнивает raw BM25 score с cosine similarity.

## Структура

- `src/ingestion/` — готовые парсеры и chunking; их не нужно запускать для обычного поиска.
- `src/retrieval/canonical.py` — canonical merge и validation.
- `src/retrieval/bm25.py` — dependency-free Russian inverted-index BM25.
- `src/retrieval/mvp.py` — two-path retrieval, RRF, source priority и diversity.
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
python scripts/search_mvp.py "ошибка при добавлении МЧД"
```

Ориентировочные показатели на hackathon laptop:

- BM25 build: ~6–20 секунд;
- 43,991 уникальных нормализованных terms;
- сериализованный ticket index: ~83 MB;
- non-technical query: около 1 ms;
- technical query с ticket path: около 14–30 ms.

Примеры запросов:

```powershell
python scripts/search_mvp.py "как добавить МЧД"
python scripts/search_mvp.py "как создать оферту"
python scripts/search_mvp.py "как зарегистрироваться поставщику"
python scripts/search_mvp.py "не подписывается оферта"
python scripts/search_mvp.py "не открывается котировочная сессия"
```

Non-technical queries возвращают official evidence. Technical queries возвращают official evidence первым и добавляют relevant historical ticket как supporting troubleshooting context.

## Dense Qwen3 + Qdrant (будущее ускоренное оборудование)

Используется только локальная `models/qwen3-embedding-0.6b`. Qwen3 documents получают обычный текст, а queries — встроенный model prompt `query`. Вектор нормализуется для cosine similarity.

```powershell
# Малый smoke test; не запускайте full-corpus embedding на CPU-only ноутбуке
python scripts/index_qdrant.py --limit 100 --smoke-size 100 --batch-size 1 --recreate

# Поиск по готовой Qdrant collection
python scripts/search.py "как добавить машиночитаемую доверенность"
```

Collection называется `zakupki_knowledge`; point ID детерминированно строится из `chunk_id`, поэтому повторный upsert идемпотентен. Qdrant payload сохраняет canonical fields и source-specific metadata.

## Что намеренно не включено

- reranking;
- генеративный LLM-ответ;
- full dense embedding historical tickets на CPU;
- изменения ingestion/parsing pipeline.

Текущий generator — extractive: он показывает лучший источник. При отсутствии достаточного evidence отдаёт операторский fallback; profanity отклоняется до retrieval.

## Тесты

```powershell
python -m pytest -q
```

Тесты используют fixtures/mocks или локальный temporary Qdrant и не требуют model download, GPU либо запущенного Qdrant service.
