"""Qdrant connection: a server when QDRANT_URL is set, otherwise an embedded folder."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from qdrant_client import QdrantClient

from config import settings

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    if settings.QDRANT_URL:
        return QdrantClient(url=settings.QDRANT_URL, timeout=10)
    path = ROOT / settings.QDRANT_PATH
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))


def reset_client() -> None:
    get_client.cache_clear()


def collection_ready() -> bool:
    try:
        client = get_client()
        return client.collection_exists(settings.QDRANT_COLLECTION)
    except Exception as e:
        logger.debug(f"Qdrant unavailable: {e}")
        return False
