import json

import httpx
import pytest

from agents import dispatch
from agents.dispatch import dispatch_items
from config import settings
from models.schemas import ActionItem
from services import ticket_store
from services.roster import Roster
from tools import get_tracker
from tools.jira import JiraCloud
from tools.local import LocalTracker


def _item(**kwargs) -> ActionItem:
    defaults = dict(
        id="item-1",
        task="Add rate limiting to the login endpoint",
        owner="Bob",
        priority="high",
        due_date="2026-10-30",
        source_segment="I will do it by Wednesday.",
    )
    defaults.update(kwargs)
    return ActionItem(**defaults)


@pytest.fixture
def roster_file(tmp_path):
    path = tmp_path / "team.json"
    path.write_text(
        json.dumps(
            {
                "Bob Mehta": {"email": "bob@example.com", "jira_account_id": "acc-bob"},
                "Carol D'Souza": {"email": "carol@example.com", "jira_account_id": ""},
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def jira_settings(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_INTEGRATIONS", False)
    monkeypatch.setattr(settings, "TRACKER_PROVIDER", "jira")
    monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://team.atlassian.net/")
    monkeypatch.setattr(settings, "JIRA_EMAIL", "me@example.com")
    monkeypatch.setattr(settings, "JIRA_API_TOKEN", "token")
    monkeypatch.setattr(settings, "JIRA_PROJECT_KEY", "MEET")


def test_roster_matches_full_name(roster_file):
    assert Roster(roster_file).account_for("Bob Mehta", "jira") == "acc-bob"


def test_roster_matches_first_name_only(roster_file):
    assert Roster(roster_file).account_for("bob", "jira") == "acc-bob"


def test_roster_returns_none_for_blank_account(roster_file):
    assert Roster(roster_file).account_for("Carol D'Souza", "jira") is None


def test_roster_returns_none_for_unknown_person(roster_file):
    assert Roster(roster_file).account_for("Nobody", "jira") is None


def test_roster_without_a_file_returns_none(tmp_path):
    assert Roster(tmp_path / "missing.json").account_for("Bob Mehta", "jira") is None


def test_get_tracker_defaults_to_local():
    assert isinstance(get_tracker(), LocalTracker)


def test_get_tracker_returns_jira_when_configured(jira_settings):
    assert isinstance(get_tracker(), JiraCloud)


def test_get_tracker_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_INTEGRATIONS", False)
    monkeypatch.setattr(settings, "TRACKER_PROVIDER", "trello")

    with pytest.raises(RuntimeError, match="Unknown TRACKER_PROVIDER"):
        get_tracker()


def test_jira_without_credentials_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MOCK_INTEGRATIONS", False)
    monkeypatch.setattr(settings, "TRACKER_PROVIDER", "jira")
    monkeypatch.setattr(settings, "JIRA_BASE_URL", "")

    with pytest.raises(RuntimeError, match="JIRA_BASE_URL"):
        get_tracker()


def test_jira_payload_carries_the_item(jira_settings):
    payload = JiraCloud().payload(_item(), "m1", assignee="acc-bob")["fields"]

    assert payload["project"] == {"key": "MEET"}
    assert payload["summary"] == "Add rate limiting to the login endpoint"
    assert payload["duedate"] == "2026-10-30"
    assert payload["assignee"] == {"accountId": "acc-bob"}
    assert payload["priority"] == {"name": "High"}
    assert "I will do it by Wednesday." in json.dumps(payload["description"])


def test_jira_payload_skips_unset_fields(jira_settings, monkeypatch):
    monkeypatch.setattr(settings, "JIRA_SET_PRIORITY", False)

    payload = JiraCloud().payload(_item(due_date=None), "m1")["fields"]

    assert "duedate" not in payload
    assert "assignee" not in payload
    assert "priority" not in payload


async def test_jira_create_issue_returns_key_and_url(jira_settings):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"key": "MEET-42"})

    created = await JiraCloud(transport=httpx.MockTransport(handler)).create_issue(_item(), "m1")

    assert seen["url"] == "https://team.atlassian.net/rest/api/3/issue"
    assert seen["body"]["fields"]["summary"] == "Add rate limiting to the login endpoint"
    assert created == {
        "id": "MEET-42",
        "url": "https://team.atlassian.net/browse/MEET-42",
    }


async def test_jira_error_is_reported(jira_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"errors": {"priority": "Field not on screen"}}')

    tracker = JiraCloud(transport=httpx.MockTransport(handler))

    with pytest.raises(RuntimeError, match="Jira rejected the issue"):
        await tracker.create_issue(_item(), "m1")


async def test_dispatch_uses_the_roster_account(monkeypatch, tmp_path, roster_file):
    monkeypatch.setattr(ticket_store, "LOCAL_PATH", tmp_path / "local_tickets.json")
    monkeypatch.setattr(dispatch.roster, "_path", roster_file)
    monkeypatch.setattr(dispatch.roster, "_people", None)
    sent = {}

    class RecordingTracker(LocalTracker):
        name = "jira"

        async def create_issue(self, item, meeting_id, assignee=None):
            sent["assignee"] = assignee
            return {"id": "MEET-7", "url": "https://team.atlassian.net/browse/MEET-7"}

    monkeypatch.setattr(dispatch, "get_tracker", lambda: RecordingTracker())

    results = await dispatch_items([_item(owner="Bob Mehta")], "m1")

    assert sent["assignee"] == "acc-bob"
    assert results[0].status == "success"
    assert results[0].jira_ticket_id == "MEET-7"


async def test_dispatch_records_failures_per_item(monkeypatch):
    class BrokenTracker(LocalTracker):
        async def create_issue(self, item, meeting_id, assignee=None):
            raise RuntimeError("Jira rejected the issue (401)")

    monkeypatch.setattr(dispatch, "get_tracker", lambda: BrokenTracker())
    item = _item()

    results = await dispatch_items([item], "m1")

    assert results[0].status == "failed"
    assert "401" in results[0].errors[0]
    assert item.status == "failed"


async def test_dispatch_reports_misconfiguration_once_per_item(monkeypatch):
    def _broken():
        raise RuntimeError("Jira is not configured. Set JIRA_BASE_URL in .env")

    monkeypatch.setattr(dispatch, "get_tracker", _broken)

    results = await dispatch_items([_item(), _item(id="item-2")], "m1")

    assert [result.status for result in results] == ["failed", "failed"]
    assert "not configured" in results[0].errors[0]
