from abc import ABC, abstractmethod

from models.schemas import ActionItem


class TicketProvider(ABC):
    name: str

    @abstractmethod
    async def create_issue(
        self, item: ActionItem, meeting_id: str, assignee: str | None = None
    ) -> dict:
        """Return {"id": ..., "url": ...} for the created ticket."""


def describe(item: ActionItem, meeting_id: str) -> str:
    lines = [item.task]
    if item.source_segment:
        lines.append(f'Quote from meeting: "{item.source_segment}"')
    if item.due_date:
        lines.append(f"Due: {item.due_date}")
    lines.append(f"Owner from transcript: {item.owner}")
    lines.append(f"Filed from meeting {meeting_id}")
    return "\n".join(lines)
