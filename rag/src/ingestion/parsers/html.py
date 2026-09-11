from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

from .base import clean_text


def clean_html_fragment(html: str | None, base_url: str | None = None) -> dict:
    """Turn an HTML fragment into readable text while retaining links and images."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()
    links = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"]) if base_url else anchor["href"]
        links.append({"url": url, "text": clean_text(anchor.get_text(" ", strip=True))})
    images = []
    for image in soup.find_all("img", src=True):
        url = urljoin(base_url, image["src"]) if base_url else image["src"]
        caption_tag = image.find_next("figcaption")
        caption = caption_tag.get_text(" ", strip=True) if caption_tag else image.get("alt", "")
        images.append({"url": url, "caption": clean_text(caption) or None})
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for item in list(soup.find_all("li")):
        item.replace_with(f"\n- {item.get_text(' ', strip=True)}\n")
    for table in list(soup.find_all("table")):
        rows = []
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if cells:
                rows.append(" | ".join(cells))
        table.replace_with("\n" + "\n".join(rows) + "\n")
    for block in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "table", "tr"]):
        block.insert_before("\n")
        block.append("\n")
    text = clean_text(soup.get_text(separator=" ", strip=False))
    # A link can occur more than once in markup; retain a compact deterministic list.
    unique_links = list({(item["url"], item["text"]): item for item in links}.values())
    unique_images = list({item["url"]: item for item in images}.values())
    return {"text": text, "links": unique_links, "images": unique_images}


def parse_html(path: str | Path) -> list[dict]:
    path = Path(path)
    from bs4 import BeautifulSoup
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    cleaned = clean_html_fragment(html, base_url=path.parent.as_uri() + "/")
    text = cleaned["text"]
    return [] if not text else [{
        "text": text, "source": path.name, "page": None, "title": soup.title.get_text(strip=True) if soup.title else None,
        "document_type": "manual", "source_type": "html", "authority": "manual", "links": cleaned["links"],
    }]
