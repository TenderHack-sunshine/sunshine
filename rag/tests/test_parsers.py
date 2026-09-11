from unittest.mock import patch

from src.ingestion.parsers.pdf import parse_pdf


class _Page:
    def __init__(self, text):
        self.text = text

    def get_text(self, kind):
        assert kind == "text"
        return self.text


class _Pdf:
    def __init__(self):
        self.pages = [_Page("Section one\nUseful instructions"), _Page("Title .... 3\nOther .... 5\nMore .... 9")]

    def __enter__(self):
        return self.pages

    def __exit__(self, *args):
        return False


def test_pdf_parser_preserves_manual_metadata():
    with patch("fitz.open", return_value=_Pdf()):
        documents = parse_pdf("manual.pdf")
    assert documents == [{
        "text": "Section one\nUseful instructions", "source": "manual.pdf", "page": 1,
        "document_type": "manual", "source_type": "pdf", "authority": "manual",
    }]
