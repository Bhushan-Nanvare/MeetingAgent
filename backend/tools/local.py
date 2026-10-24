from models.schemas import ActionItem
from services.ticket_store import create_ticket
from tools.base import TicketProvider, describe


class LocalTracker(TicketProvider):
    name = "local"

    async def create_issue(
        self, item: ActionItem, meeting_id: str, assignee: str | None = None
    ) -> dict:
        ticket = create_ticket(
            title=item.task,
            description=describe(item, meeting_id),
            assignee=assignee or item.owner,
            priority=item.priority,
            meeting_id=meeting_id,
        )
        return {"id": ticket["id"], "url": f"/tickets/{ticket['id']}"}
