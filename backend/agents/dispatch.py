"""Turn approved action items into tracker tickets."""

from datetime import datetime, timezone

from config import settings
from models.schemas import ActionItem, DispatchResult
from tools.jira import jira_tool


async def dispatch_items(items: list[ActionItem], meeting_id: str) -> list[DispatchResult]:
    now = datetime.now(timezone.utc).isoformat()
    results: list[DispatchResult] = []

    if not settings.MOCK_INTEGRATIONS:
        return [
            DispatchResult(
                item_id=item.id,
                task=item.task,
                status="failed",
                errors=["Live Jira is not configured. Set MOCK_INTEGRATIONS=true to file into the local tracker."],
                dispatched_at=now,
            )
            for item in items
        ]

    for item in items:
        try:
            created = await jira_tool.create_issue(item, meeting_id)
            item.jira_ticket_id = created["id"]
            item.jira_url = created["url"]
            item.status = "approved"
            results.append(
                DispatchResult(
                    item_id=item.id,
                    task=item.task,
                    jira_url=created["url"],
                    jira_ticket_id=created["id"],
                    status="success",
                    dispatched_at=now,
                )
            )
        except Exception as e:
            results.append(
                DispatchResult(
                    item_id=item.id,
                    task=item.task,
                    status="failed",
                    errors=[str(e)],
                    dispatched_at=now,
                )
            )
    return results
