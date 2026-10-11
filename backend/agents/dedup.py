"""Flag action items that already look like tickets in the tracker.

This first version uses word overlap against the local ticket corpus so it
runs in tests and on a laptop with no Qdrant or embedding calls. Semantic
search can replace `_score` later without changing the API.
"""

from __future__ import annotations

import re

from models.schemas import ActionItem, SimilarTicket
from services.ticket_store import all_tickets

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


def annotate_action_items(items: list[ActionItem]) -> list[ActionItem]:
    """Attach similar tickets and mark likely duplicates. Approved/rejected stay as-is."""
    corpus = all_tickets()
    for item in items:
        item.similar_tickets = find_similar(item.task, corpus)
        if item.status in {"approved", "rejected", "failed"}:
            continue
        item.status = "possible_duplicate" if item.similar_tickets else "new"
    return items
