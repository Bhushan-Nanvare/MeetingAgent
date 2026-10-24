from config import settings
from tools.base import TicketProvider
from tools.jira import JiraCloud
from tools.local import LocalTracker


def get_tracker() -> TicketProvider:
    if settings.MOCK_INTEGRATIONS or settings.TRACKER_PROVIDER == "local":
        return LocalTracker()
    if settings.TRACKER_PROVIDER == "jira":
        return JiraCloud()
    raise RuntimeError(
        f"Unknown TRACKER_PROVIDER '{settings.TRACKER_PROVIDER}'. Use 'local' or 'jira'."
    )
