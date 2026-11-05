"""Find tickets that mean the same thing as an action item."""

from __future__ import annotations

import asyncio

from config import settings
from models.schemas import SimilarTicket
from providers.embedder import embedder
from rag.client import get_client


async def search_similar(task: str, limit: int = 3) -> list[SimilarTicket]:
    vector = await embedder.embed_one(task)
    client = get_client()
    response = await asyncio.to_thread(
        client.query_points,
        collection_name=settings.QDRANT_COLLECTION,
        query=vector,
        limit=limit,
        score_threshold=settings.DEDUP_THRESHOLD,
        with_payload=True,
    )
    return [
        SimilarTicket(
            id=str(point.payload.get("ticket_id") or ""),
            title=str(point.payload.get("title") or ""),
            status=str(point.payload.get("status") or ""),
            assignee=str(point.payload.get("assignee") or ""),
            score=round(float(point.score), 3),
        )
        for point in response.points
    ]
