from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from src.ingestion.chunker import approximate_token_count, chunk_document
from src.ingestion.parsers.base import clean_text
from src.ingestion.parsers.html import clean_html_fragment


SOURCE = "zakupki_mos_knowledgebase"
MAIN_TEXT_FIELDS = ("selfServicePortal", "detailText", "previewText", "chatBots", "instructionOperator")
L3_HINTS = ("ошибка", "не отображается", "не работает", "не загружается", "не подписывается", "авторизац", "техническ", "сбой", "интеграц", "загрузка", "подписан")
L2_HINTS = ("регламент", "закон", "правил", "требован", "порядок", "котировочн", "норматив", "методолог", "процедур")
L1_HINTS = ("как ", "где ", "кто ", "что ", "инструкц", "добавить", "создать", "найти", "перейти")


class KnowledgeBaseAPIError(RuntimeError):
    pass


class ZakupkiKnowledgeBaseClient:
    """Small configurable HTTP client. It deliberately does not guess an API endpoint."""

    def __init__(self, api_url: str | None, timeout_seconds: float = 20, max_retries: int = 3):
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def fetch_articles(self, section_type: str) -> list[dict]:
        if not self.api_url:
            raise KnowledgeBaseAPIError("ZAKUPKI_KB_API_URL is not set; provide the verified structured API endpoint.")
        parsed = urlparse(self.api_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["sectionType"] = section_type
        url = urlunparse(parsed._replace(query=urlencode(query)))
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                request = Request(url, headers={"Accept": "application/json", "User-Agent": "TenderHack-KB-Ingestion/1.0"})
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    if not 200 <= response.status < 300:
                        raise KnowledgeBaseAPIError(f"Knowledge Base API returned HTTP {response.status}")
                    content_type = response.headers.get_content_type()
                    if content_type not in {"application/json", "text/json"}:
                        raise KnowledgeBaseAPIError(f"Knowledge Base API returned {content_type}, not JSON")
                    try:
                        payload = json.loads(response.read().decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise KnowledgeBaseAPIError(f"Knowledge Base API returned malformed JSON: {error}") from error
                    return validate_payload(payload)
            except (HTTPError, URLError, TimeoutError, KnowledgeBaseAPIError) as error:
                last_error = error
                if isinstance(error, KnowledgeBaseAPIError) or attempt == self.max_retries - 1:
                    break
                time.sleep(0.5 * (2 ** attempt))
        raise KnowledgeBaseAPIError(f"Could not fetch Knowledge Base section {section_type!r}: {last_error}")


def validate_payload(payload: Any) -> list[dict]:
    if not isinstance(payload, list):
        raise KnowledgeBaseAPIError("Knowledge Base response must be a JSON array of categories")
    if not all(isinstance(category, dict) for category in payload):
        raise KnowledgeBaseAPIError("Knowledge Base response contains a non-object category")
    return payload


def _clean_plain(value: Any) -> str | None:
    if value is None:
        return None
    text = clean_text(re.sub(r"<[^>]+>", "", str(value)))
    return text or None


def _parse_updated_date(value: Any) -> tuple[str | None, str | None]:
    original = _clean_plain(value)
    if not original:
        return None, None
    try:
        return datetime.strptime(original, "%d.%m.%Y %H:%M:%S").isoformat(), original
    except ValueError:
        return None, original


def _role_from_sections(section_types: Any, requested_section: str | None = None) -> str | None:
    if not isinstance(section_types, dict):
        return None
    if requested_section and section_types.get(requested_section):
        return requested_section
    return next((str(key) for key, value in section_types.items() if value), None)


def classify_support_level(title: str, text: str) -> str:
    haystack = f"{title} {text}".casefold()
    if any(hint in haystack for hint in L3_HINTS):
        return "L3"
    if any(hint in haystack for hint in L2_HINTS):
        return "L2"
    if any(hint in haystack for hint in L1_HINTS):
        return "L1"
    return "UNKNOWN"


def _meaningful_field(article: dict, base_url: str) -> tuple[str | None, dict]:
    for field in MAIN_TEXT_FIELDS:
        cleaned = clean_html_fragment(article.get(field), base_url)
        if cleaned["text"]:
            return field, cleaned
    return None, {"text": "", "links": [], "images": []}


def normalize_article(article: dict, category: dict, service: dict, section_type: str | None, base_url: str) -> dict | None:
    article_id = article.get("id")
    if article_id is None:
        return None
    title = _clean_plain(article.get("largeName"))
    selected_field, content = _meaningful_field(article, base_url)
    if not title or not content["text"]:
        return None
    operator = clean_html_fragment(article.get("instructionOperator"), base_url)
    updated_at, updated_original = _parse_updated_date(article.get("updatedDate"))
    section_types = article.get("sectionTypes") if isinstance(article.get("sectionTypes"), dict) else {}
    metadata = {
        "article_id": article_id, "static_id": article.get("staticId"), "category_id": category.get("categoryId"),
        "service_id": service.get("serviceId"), "task_name": _clean_plain(article.get("taskName")),
        "status": _clean_plain(article.get("status")), "article_status": _clean_plain(article.get("artStatus")),
        "section_types": section_types, "tags": article.get("tags"), "alt_class_lvl1": article.get("altClassLvl1"),
        "alt_class_lvl2": article.get("altClassLvl2"), "alt_class_lvl3": article.get("altClassLvl3"),
        "alt_class_lvl4": article.get("altClassLvl4"), "selected_text_field": selected_field,
        "updated_date_original": updated_original,
    }
    return {
        "document_id": f"zakupki_kb:{article_id}", "source": SOURCE, "title": title, "text": content["text"],
        "operator_text": operator["text"] or None, "category": _clean_plain(category.get("categoryName")),
        "service": _clean_plain(service.get("serviceName")), "role": _role_from_sections(section_types, section_type),
        "support_level": classify_support_level(title, content["text"]), "updated_at": updated_at,
        "links": content["links"], "images": content["images"], "metadata": metadata,
        "authority": "manual", "document_type": "knowledgebase_article",
    }


def _embedding_prefix(document: dict) -> str:
    labels = [("Название", document["title"]), ("Категория", document.get("category")), ("Раздел", document.get("service"))]
    return "\n".join(f"{label}: {value}" for label, value in labels if value)


def chunk_knowledgebase_article(document: dict, max_tokens: int = 700) -> list[dict]:
    """Use the existing structure-preserving recursive chunker, without embeddings."""
    prefix = _embedding_prefix(document)
    prefix_tokens = approximate_token_count(prefix)
    body_tokens = approximate_token_count(document["text"])
    if prefix_tokens + body_tokens <= max_tokens:
        bodies = [{"text": document["text"], "section": None, "token_count": body_tokens}]
    else:
        body_limit = max(100, max_tokens - prefix_tokens)
        bodies = chunk_document(
            {"source": document["source"], "text": document["text"], "document_type": document["document_type"], "authority": document["authority"]},
            chunk_size=body_limit, overlap_paragraphs=1, min_chunk_tokens=1,
        )
    chunks = []
    for index, body in enumerate(bodies):
        text = f"{prefix}\n\n{body['text']}".strip()
        chunks.append({
            "chunk_id": f"{document['document_id']}:{index}", "document_id": document["document_id"], "text": text,
            "title": document["title"], "category": document.get("category"), "service": document.get("service"),
            "role": document.get("role"), "support_level": document["support_level"], "source": SOURCE,
            "updated_at": document.get("updated_at"), "section": body.get("section"), "page": None,
            "page_start": None, "page_end": None, "chunk_index": index, "token_count": approximate_token_count(text),
            "authority": document["authority"], "document_type": document["document_type"], "chunking_strategy": "knowledgebase_structured",
            "metadata": document["metadata"],
        })
    return chunks


def ingest_knowledgebase_payload(payload: Any, section_type: str | None = "supplier", base_url: str = "https://zakupki.mos.ru",
                                 max_chunk_tokens: int = 700) -> tuple[list[dict], list[dict], dict]:
    """Parse a saved/API JSON payload. Bad records are reported, not fatal."""
    categories = validate_payload(payload)
    documents: list[dict] = []
    chunks: list[dict] = []
    seen_ids: set[str] = set()
    roles, levels, skipped = Counter(), Counter(), Counter()
    service_count = article_total = duplicate_count = empty_count = 0
    warnings: list[str] = []
    for category in categories:
        services = category.get("articlesByService", [])
        if not isinstance(services, list):
            warnings.append(f"Category {category.get('categoryId')} has invalid articlesByService")
            continue
        for service in services:
            if not isinstance(service, dict):
                warnings.append("Skipped malformed service")
                continue
            service_count += 1
            articles = service.get("articles", [])
            if not isinstance(articles, list):
                warnings.append(f"Service {service.get('serviceId')} has invalid articles")
                continue
            for article in articles:
                article_total += 1
                if not isinstance(article, dict):
                    skipped["malformed"] += 1
                    continue
                article_id = article.get("id")
                if article_id is None:
                    skipped["missing_id"] += 1
                    continue
                stable_id = str(article_id)
                if stable_id in seen_ids:
                    duplicate_count += 1
                    continue
                seen_ids.add(stable_id)
                if article.get("status") != "Опубликована":
                    skipped["not_published"] += 1
                    continue
                if article.get("artStatus") != "Активная":
                    skipped["not_active"] += 1
                    continue
                try:
                    document = normalize_article(article, category, service, section_type, base_url)
                except (TypeError, ValueError, AttributeError) as error:
                    warnings.append(f"Article {article_id} could not be normalized: {error}")
                    skipped["malformed"] += 1
                    continue
                if document is None:
                    empty_count += 1
                    continue
                documents.append(document)
                article_chunks = chunk_knowledgebase_article(document, max_chunk_tokens)
                chunks.extend(article_chunks)
                roles[document["role"] or "UNKNOWN"] += 1
                levels[document["support_level"]] += 1
    report = {
        "source": SOURCE, "categories": len(categories), "services": service_count, "articles_total": article_total,
        "articles_ingested": len(documents), "articles_skipped": sum(skipped.values()) + empty_count + duplicate_count,
        "skipped_reasons": {**dict(skipped), "empty": empty_count, "duplicate": duplicate_count},
        "chunks": len(chunks), "roles": dict(roles), "support_levels": {level: levels[level] for level in ("L1", "L2", "L3", "UNKNOWN")},
        "empty_articles": empty_count, "duplicates": duplicate_count, "warnings": warnings,
    }
    return documents, chunks, report


def load_payload(path: str | Path) -> list[dict]:
    try:
        return validate_payload(json.loads(Path(path).read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise KnowledgeBaseAPIError(f"Saved Knowledge Base JSON is malformed: {error}") from error
