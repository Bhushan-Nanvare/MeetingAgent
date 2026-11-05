"""Load tickets into Qdrant so duplicate detection can match on meaning."""

from __future__ import annotations

import asyncio
import logging

from qdrant_client import models

from config import settings
from providers.embedder import embedder
from rag.client import get_client

logger = logging.getLogger(__name__)
BATCH_SIZE = 64


def ticket_text(ticket: dict) -> str:
    return f"{ticket.get('title') or ''}\n{ticket.get('description') or ''}".strip()


async def ingest_tickets(tickets: list[dict], recreate: bool = True) -> int:
    usable = [ticket for ticket in tickets if ticket_text(ticket)]
    if not usable:
        return 0

    vectors = await embedder.embed_batch([ticket_text(ticket) for ticket in usable])
    client = get_client()

    if recreate:
        await asyncio.to_thread(
            client.recreate_collection,
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=models.VectorParams(
                size=settings.EMBEDDING_SIZE, distance=models.Distance.COSINE
            ),
        )

    points = [
        models.PointStruct(
            id=index,
            vector=vector,
            payload={
                "ticket_id": str(ticket.get("id") or ""),
                "title": str(ticket.get("title") or ""),
                "status": str(ticket.get("status") or ""),
                "assignee": str(ticket.get("assignee") or ""),
            },
        )
        for index, (ticket, vector) in enumerate(zip(usable, vectors))
    ]

    for start in range(0, len(points), BATCH_SIZE):
        await asyncio.to_thread(
            client.upsert,
            collection_name=settings.QDRANT_COLLECTION,
            points=points[start : start + BATCH_SIZE],
        )

    logger.info(f"Indexed {len(points)} tickets into {settings.QDRANT_COLLECTION}")
    return len(points)
