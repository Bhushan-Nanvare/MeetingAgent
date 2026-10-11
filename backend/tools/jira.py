"""Create tickets in the tracker. Live Jira is not wired yet; mock mode writes locally."""

from models.schemas import ActionItem
from services.ticket_store import create_ticket


class JiraTool:
    async def create_issue(self, item: ActionItem, meeting_id: str) -> dict:
        description_parts = [item.task]
        if item.source_segment:
            description_parts.append(f'\nQuote from meeting: "{item.source_segment}"')
        if item.due_date:
            description_parts.append(f"Due: {item.due_date}")
        description_parts.append(f"Filed from meeting {meeting_id}")

        ticket = create_ticket(
            title=item.task,
            description="\n".join(description_parts),
            assignee=item.owner,
            priority=item.priority,
            meeting_id=meeting_id,
        )
        return {
            "id": ticket["id"],
            "url": f"/tickets/{ticket['id']}",
        }


jira_tool = JiraTool()
