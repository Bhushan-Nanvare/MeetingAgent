"""Index the ticket corpus into Qdrant.

    python scripts/seed_corpus.py [path/to/tickets.json]

Stop the API first when Qdrant runs in embedded mode (no QDRANT_URL set); the two
processes cannot open the same folder at once.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from rag.ingest import ingest_tickets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCE = ROOT / "data" / "mock_tickets.json"


async def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.exists():
        print(f"No such file: {source}")
        return 1

    tickets = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(tickets, list):
        print(f"{source} should contain a JSON list of tickets")
        return 1

    where = settings.QDRANT_URL or f"{settings.QDRANT_PATH} (embedded)"
    print(f"Indexing {len(tickets)} tickets from {source.name} into {where}")
    indexed = await ingest_tickets(tickets)
    print(f"Done: {indexed} tickets in collection '{settings.QDRANT_COLLECTION}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
