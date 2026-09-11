# Tender Hack 2026 — local RAG MVP

This repository is a local-first support-assistant retrieval MVP for the Moscow Supplier Portal. It parses official manuals, cleans historical tickets, and returns source-backed evidence. It does not call external inference or search APIs, and it never downloads model weights automatically.

## Architecture

```text
User Query
    ↓
Moderation
    ↓
Topic Routing
    ↓
Hybrid Retrieval
    ├── BM25
    └── Dense Retrieval (local Qdrant + local embedding model)
    ↓
RRF Fusion
    ↓
Optional local Reranker
    ↓
Confidence Gate
    ├── enough evidence → extractive answer with source/page
    └── insufficient evidence → human operator fallback
```

Official manuals have `authority: manual`. Historical tickets have `authority: historical_ticket`, and generic ticket resolutions such as “Исправлено” are down-ranked rather than used as primary evidence.

## Layout

- `data/raw/manuals/` — PDF/DOCX/HTML manuals (untracked)
- `data/raw/tickets/` — ticket export and official topic taxonomy (untracked)
- `data/processed/` — generated JSONL (untracked)
- `data/indexes/` — local index artifacts (untracked)
- `models/qwen3-embedding-0.6b/` and `models/qwen3-reranker-0.6b/` — pre-downloaded local weights (untracked)
- `src/ingestion/` — parsers, structure-aware chunking, ticket cleaning
- `src/retrieval/` — BM25, local embeddings/Qdrant, RRF, optional reranking

## Install

Use Python 3.10+ and install the project dependencies:

```bash
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` only when overriding defaults. Paths are relative to the repository root by default.

## Build and query locally

Manual ingestion uses document-level semantic chunking by default: sections persist across PDF pages, adjacent atomic units are embedded locally, and high adaptive-distance boundaries are preferred. It requires `models/qwen3-embedding-0.6b/`; use the explicit legacy fallback only when local model inference is unavailable:

```bash
python scripts/ingest_documents.py --strategy recursive
```

## Generic local-file ingestion

The generic local-file runner recursively supports PDF, XLSX, DOCX, CSV, TXT, Markdown, HTML, and JSON. It emits a separate local-files dataset and skips `data/raw/zakupki_kb/`, because that source has its dedicated structured ingester.

```powershell
python scripts/ingest.py --input data/raw --output data/processed/files --verbose
```

Use `--force` to replace that command’s prior `documents.jsonl`, `chunks.jsonl`, and `report.json`; it does not alter Knowledge Base outputs.

1. Put manuals under `data/raw/manuals/`; put the two Excel files under `data/raw/tickets/`.
2. Start Qdrant locally, for example:

   ```bash
   docker run --rm -p 6333:6333 -v "${PWD}/qdrant_storage:/qdrant/storage" qdrant/qdrant
   ```

3. Parse and chunk manuals:

   ```bash
   python scripts/ingest_documents.py
   ```

4. Clean ticket history (adjust the two filenames if needed):

   ```bash
   python scripts/prepare_tickets.py "data/raw/tickets/Выгрузка СТП за 2026.xlsx" "data/raw/tickets/Темы_подтемы_обращений.xlsx"
   ```

5. With the local embedding model in `models/qwen3-embedding-0.6b/`, build the local Qdrant collection. This includes manuals and historical-ticket examples, with their distinct authority metadata:

   ```bash
   python scripts/build_index.py
   ```

6. Start the CLI demo:

   ```bash
   python scripts/search_demo.py
   ```

It displays route, evidence source/page/score, and an extractive answer or operator fallback. If Qdrant or a model is not available, the in-process BM25 retrieval still works; the CLI expects the Qdrant index for dense retrieval.

## Tests

```bash
pytest
```

The unit tests use fixtures/mocks and do not download models or contact Qdrant.

## Moscow Supplier Portal Knowledge Base

The Knowledge Base source uses its structured JSON API, never rendered-page scraping. Set `ZAKUPKI_KB_API_URL` to the verified API endpoint—the repository deliberately does not guess it—and then fetch the configured supplier section:

```powershell
python scripts/ingest_zakupki_kb.py --section-type supplier --save-raw
```

For reproducible, offline parsing of a saved response:

```powershell
python scripts/ingest_zakupki_kb.py --from-file data/raw/zakupki_kb/supplier.json
```

The command writes `zakupki_kb_documents.jsonl`, `zakupki_kb_chunks.jsonl`, and `zakupki_kb_report.json` beneath `data/processed/`. It does not create embeddings, connect to Qdrant, or download article images.
