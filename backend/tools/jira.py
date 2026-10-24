import httpx

from config import settings
from models.schemas import ActionItem
from tools.base import TicketProvider, describe

PRIORITY_NAMES = {"high": "High", "medium": "Medium", "low": "Low"}
REQUIRED_SETTINGS = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY")


class JiraCloud(TicketProvider):
    name = "jira"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        missing = [name for name in REQUIRED_SETTINGS if not getattr(settings, name)]
        if missing:
            raise RuntimeError(f"Jira is not configured. Set {', '.join(missing)} in .env")
        self._base_url = settings.JIRA_BASE_URL.rstrip("/")
        self._auth = (settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)
        self._transport = transport

    async def create_issue(
        self, item: ActionItem, meeting_id: str, assignee: str | None = None
    ) -> dict:
        async with httpx.AsyncClient(
            auth=self._auth, timeout=30.0, transport=self._transport
        ) as client:
            response = await client.post(
                f"{self._base_url}/rest/api/3/issue",
                json=self.payload(item, meeting_id, assignee),
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Jira rejected the issue ({response.status_code}): {response.text[:300]}"
            )

        key = response.json()["key"]
        return {"id": key, "url": f"{self._base_url}/browse/{key}"}

    def payload(self, item: ActionItem, meeting_id: str, assignee: str | None = None) -> dict:
        fields = {
            "project": {"key": settings.JIRA_PROJECT_KEY},
            "issuetype": {"name": settings.JIRA_ISSUE_TYPE},
            "summary": item.task[:255],
            "description": _adf(describe(item, meeting_id)),
        }
        if item.due_date:
            fields["duedate"] = item.due_date
        if assignee:
            fields["assignee"] = {"accountId": assignee}
        if settings.JIRA_SET_PRIORITY:
            fields["priority"] = {"name": PRIORITY_NAMES[item.priority]}
        return {"fields": fields}


def _adf(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in text.split("\n")
            if line
        ],
    }
