"""Turn approved action items into tracker tickets."""

from datetime import datetime, timezone

from models.schemas import ActionItem, DispatchResult
from services.roster import roster
from tools import get_tracker


async def dispatch_items(items: list[ActionItem], meeting_id: str) -> list[DispatchResult]:
    now = datetime.now(timezone.utc).isoformat()

    try:
        tracker = get_tracker()
    except Exception as e:
        return [
            DispatchResult(
                item_id=item.id,
                task=item.task,
                status="failed",
                errors=[str(e)],
                dispatched_at=now,
            )
            for item in items
        ]

    results: list[DispatchResult] = []
    for item in items:
        try:
            created = await tracker.create_issue(
                item, meeting_id, roster.account_for(item.owner, tracker.name)
            )
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
            item.status = "failed"
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
