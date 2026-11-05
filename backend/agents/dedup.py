"""Flag action items that already look like tickets in the tracker.

Semantic search (embeddings in Qdrant) runs first when it is available, because it
catches "users cannot sign in" against "fix login bug". Word overlap is the fallback,
so the feature still works with no Qdrant, no API key and no network.
"""

from __future__ import annotations

import logging
import re

from config import settings
from models.schemas import ActionItem, SimilarTicket
from services.ticket_store import all_tickets

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a", "an", "the", "to", "of", "for", "and", "or", "in", "on", "with", "by",
    "from", "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "it", "at", "as", "into",
}
# Word overlap is stricter than embedding cosine, so this is lower than DEDUP_THRESHOLD.
LEXICAL_THRESHOLD = 0.45


def _tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _STOP and len(word) > 2}


def _score(task: str, ticket: dict) -> float:
    task_tokens = _tokens(task)
    title_tokens = _tokens(str(ticket.get("title") or ""))
    body_tokens = title_tokens | _tokens(str(ticket.get("description") or ""))
    if not task_tokens or not body_tokens:
        return 0.0

    title_overlap = len(task_tokens & title_tokens) / len(task_tokens) if title_tokens else 0.0
    body_overlap = len(task_tokens & body_tokens) / len(task_tokens)
    jaccard = len(task_tokens & body_tokens) / len(task_tokens | body_tokens)
    return max(title_overlap, body_overlap * 0.9, jaccard)


def find_similar(task: str, tickets: list[dict] | None = None, limit: int = 3) -> list[SimilarTicket]:
    corpus = tickets if tickets is not None else all_tickets()
    ranked = sorted(
        ((_score(task, ticket), ticket) for ticket in corpus),
        key=lambda pair: pair[0],
        reverse=True,
    )
    matches = []
    for score, ticket in ranked:
        if score < LEXICAL_THRESHOLD:
            continue
        matches.append(
            SimilarTicket(
                id=str(ticket.get("id") or ""),
                title=str(ticket.get("title") or ""),
                status=str(ticket.get("status") or ""),
                assignee=str(ticket.get("assignee") or ""),
                score=round(score, 3),
            )
        )
        if len(matches) >= limit:
            break
    return matches


async def match_task(task: str, corpus: list[dict] | None = None) -> list[SimilarTicket]:
    if settings.SEMANTIC_DEDUP:
        try:
            matches = await _semantic_matches(task)
            if matches:
                return matches
        except Exception as e:
            logger.warning(f"Semantic dedup unavailable ({e}), using word overlap")
    return find_similar(task, corpus)


async def _semantic_matches(task: str) -> list[SimilarTicket]:
    from rag.client import collection_ready
    from rag.search import search_similar

    if not collection_ready():
        return []
    return await search_similar(task)


async def annotate_action_items(items: list[ActionItem]) -> list[ActionItem]:
    """Attach similar tickets and mark likely duplicates. Approved/rejected stay as-is."""
    corpus = all_tickets()
    for item in items:
        item.similar_tickets = await match_task(item.task, corpus)
        if item.status in {"approved", "rejected", "failed", "done"}:
            continue
        item.status = "possible_duplicate" if item.similar_tickets else "new"
    return items
