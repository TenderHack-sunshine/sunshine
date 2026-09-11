from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.ingestion.tickets import load_taxonomy, preprocess_tickets


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean historical support tickets")
    parser.add_argument("tickets_file")
    parser.add_argument("taxonomy_file")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    settings = Settings()
    tickets = preprocess_tickets(args.tickets_file, load_taxonomy(args.taxonomy_file))
    output = settings.processed_dir / "tickets.jsonl" if args.output is None else Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as file:
        for ticket in tickets:
            file.write(json.dumps(ticket, ensure_ascii=False) + "\n")
    print(f"Wrote {len(tickets)} tickets to {output}")


if __name__ == "__main__":
    main()
