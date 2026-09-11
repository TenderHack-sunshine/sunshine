from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.ingestion.pipeline import ingest_manuals


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse and chunk local PDF/DOCX/HTML manuals")
    parser.add_argument("--manuals-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--strategy", choices=("semantic", "recursive"), default=None,
                        help="Semantic requires the local embedding model; recursive is explicit fallback.")
    args = parser.parse_args()
    settings = Settings()
    chunks = ingest_manuals(args.manuals_dir or settings.manuals_dir, strategy=args.strategy, settings=settings)
    output = settings.processed_dir / "manual_chunks.jsonl" if args.output is None else Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"Wrote {len(chunks)} chunks to {output}")


if __name__ == "__main__":
    main()
