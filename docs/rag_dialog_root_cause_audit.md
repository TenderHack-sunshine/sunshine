# RAG dialog reliability: baseline audit

Baseline reviewed: `3a9e4c6f87a84b4f4feed673cd08258bb3fd1711`.

## Confirmed causes before the reliability work

| Finding | Evidence | Impact |
| --- | --- | --- |
| Clarification is a small set of string rules | `rag/src/application/clarification.py` | A short but determinate request and an underspecified turn are not distinguished structurally. |
| Conversation context is concatenated text | `rag/src/api.py::_contextual_query` | The current turn, previously confirmed facts, and a stale topic cannot be separated. |
| Escalation is sticky | `backend/internal/application/support.go::AddUserMessage` | After a ticket exists, normal follow-ups bypass answer/clarification flow. |
| Topic is inferred from first retrieval source | `rag/src/api.py::_topic` | A semantically adjacent top-ranked document can assign a wrong ticket category. |
| Support level relies on marker lists | `SupportRouter`, `TechnicalRouter`, KB ingestion classifier | Line selection is not grounded in the support taxonomy. |
| Grounding is lexical overlap | `rag/src/generation/grounding.py` | It can accept evidence about the same noun but a different requested action. |
| FAQ is review-gated but no runtime-eligible verified corpus is shipped | `rag/src/faq/cards.py`, `data/processed/faq` | FAQ cannot be a source of production truth yet. |
| Evaluation labels include SILVER/model-reviewed datasets | `rag/data/eval` | They are useful diagnostics, not human ground truth. |
| Runtime model/context configuration differs between documentation and Compose | `rag/README.md`, `.env.example`, `docker-compose.yml` | Behaviour and latency are not reproducible from documentation alone. |

## Baseline data constraints

`audit_corpus.py` already correctly reports that a chunk count cannot prove
coverage of zakupki.mos.ru without a retained raw snapshot and manifest.
`instructionOperator` is currently read but the first non-empty user-facing
field is selected, losing the remaining structured content. The implementation
must retain each user-facing field with provenance and keep operator-only text
outside normal retrieval.

## Guardrails for the implementation

* Intent and evidence matching must use generic action classes and a lexicon
  built from local corpus/taxonomy metadata; no branch may name an evaluation
  object or article ID.
* Runtime has no external inference dependency. Provisioning and official-data
  ingestion are separate from local runtime.
* A ticket is offered first and created only after explicit confirmation or a
  direct human request.
