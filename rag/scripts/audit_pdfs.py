"""Report PDF pages at risk of text-extraction loss; OCR is intentionally absent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def audit_pdf(path: Path, short_text_chars: int, image_threshold: int) -> dict:
    import fitz

    pages = []
    with fitz.open(path) as document:
        for number, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            image_count = len(page.get_images(full=True))
            flags = []
            if not text:
                flags.append("NO_EXTRACTED_TEXT")
            elif len(text) < short_text_chars:
                flags.append("VERY_SHORT_TEXT")
            if image_count >= image_threshold and len(text) < short_text_chars * 3:
                flags.append("IMAGE_HEAVY_LOW_TEXT")
            if flags:
                pages.append({"page": number, "text_characters": len(text), "image_count": image_count, "flags": flags})
    return {"path": str(path), "flagged_pages": pages, "flagged_page_count": len(pages)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit PDFs for reproducible extraction-loss evidence; it does not run OCR.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/manuals"), help="PDF file or directory")
    parser.add_argument("--short-text-chars", type=int, default=80)
    parser.add_argument("--image-threshold", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.short_text_chars < 1 or args.image_threshold < 1:
        parser.error("thresholds must be positive")
    paths = [args.input] if args.input.is_file() else sorted(args.input.rglob("*.pdf"))
    report = {
        "ocr_performed": False,
        "ocr_required": False,
        "short_text_chars": args.short_text_chars,
        "image_threshold": args.image_threshold,
        "files": [audit_pdf(path, args.short_text_chars, args.image_threshold) for path in paths],
    }
    report["flagged_page_count"] = sum(item["flagged_page_count"] for item in report["files"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
