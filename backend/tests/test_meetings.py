import json

import pytest
from fastapi.testclient import TestClient

import main
from agents import extraction
from services import meeting_store

RESPONSE = {
    "summary": "Login work and the release schedule.",
    "decisions": ["Release every Thursday afternoon"],
    "action_items": [
        {
            "task": "Add rate limiting to the login endpoint",
            "owner": "Bob Mehta",
            "due_date": "2026-11-10",
            "priority": "high",
            "source_segment": "I will do it by Wednesday.",
        },
        {
            "task": "Update the onboarding guide",
            "owner": "Eve Sharma",
            "priority": "low",
        },
    ],
}


@pytest.fixture
def client(monkeypatch):
    async def _complete(system_prompt, user_prompt):
        return json.dumps(RESPONSE)

    monkeypatch.setattr(extraction.llm_provider, "complete", _complete)
    return TestClient(main.app)


def _extract(client, **overrides) -> dict:
    payload = {
        "transcript": "Bob: I will add rate limiting by Wednesday.",
        "meeting_date": "2026-11-04",
        "attendees": ["Bob Mehta", "Eve Sharma"],
        "title": "Sprint planning",
    }
    payload.update(overrides)
    return client.post("/extract", json=payload).json()


def test_extract_stores_the_meeting(client):
    extracted = _extract(client)

    meetings = client.get("/meetings").json()
    assert len(meetings) == 1
    assert meetings[0]["id"] == extracted["meeting_id"]
    assert meetings[0]["title"] == "Sprint planning"
    assert meetings[0]["total_items"] == 2
    assert meetings[0]["open_items"] == 2


def test_meeting_detail_has_decisions_and_items(client):
    extracted = _extract(client)

    detail = client.get(f"/meetings/{extracted['meeting_id']}").json()

    assert detail["decisions"] == ["Release every Thursday afternoon"]
    assert detail["attendees"] == ["Bob Mehta", "Eve Sharma"]
    assert {item["task"] for item in detail["action_items"]} == {
        "Add rate limiting to the login endpoint",
        "Update the onboarding guide",
    }


def test_unknown_meeting_is_404(client):
    assert client.get("/meetings/nope").status_code == 404


def test_marking_an_item_done_closes_it(client):
    extracted = _extract(client)
    item_id = extracted["action_items"][0]["id"]

    updated = client.patch(f"/items/{item_id}", json={"status": "done"}).json()

    assert updated["status"] == "done"
    assert updated["closed_at"]
    assert client.get("/meetings").json()[0]["open_items"] == 1


def test_editing_an_item_keeps_it_open(client):
    extracted = _extract(client)
    item_id = extracted["action_items"][0]["id"]

    updated = client.patch(
        f"/items/{item_id}", json={"owner": "Carol D'Souza", "priority": "medium"}
    ).json()

    assert updated["owner"] == "Carol D'Souza"
    assert updated["priority"] == "medium"
    assert updated["closed_at"] is None


def test_updating_an_unknown_item_is_404(client):
    assert client.patch("/items/nope", json={"status": "done"}).status_code == 404


def test_followup_lists_open_items_from_earlier_meetings(client):
    first = _extract(client, meeting_id="m1", title="Last week")
    second = _extract(client, meeting_id="m2", title="This week")
    client.patch(f"/items/{first['action_items'][0]['id']}", json={"status": "done"})

    followup = client.get("/followup", params={"exclude_meeting": "m2"}).json()

    assert {item["meeting_id"] for item in followup} == {"m1"}
    assert [item["task"] for item in followup] == ["Update the onboarding guide"]
    assert followup[0]["meeting_title"] == "Last week"
    assert second["meeting_id"] == "m2"


def test_followup_flags_overdue_items(client):
    _extract(client)

    followup = client.get("/followup").json()
    overdue = [item for item in followup if item["overdue"]]

    assert [item["due_date"] for item in overdue] == ["2026-11-10"] or not overdue


def test_search_finds_decisions_and_items(client):
    _extract(client)

    found = client.get("/search", params={"q": "rate limiting"}).json()
    decisions = client.get("/search", params={"q": "thursday"}).json()

    assert found["action_items"][0]["task"] == "Add rate limiting to the login endpoint"
    assert decisions["decisions"][0]["text"] == "Release every Thursday afternoon"
    assert decisions["decisions"][0]["meeting_title"] == "Sprint planning"


def test_search_needs_a_query(client):
    assert client.get("/search", params={"q": "  "}).status_code == 422


def test_dispatch_stores_the_ticket_link(client):
    extracted = _extract(client)
    item = extracted["action_items"][0]
    item["status"] = "approved"

    client.post(
        "/dispatch",
        json={
            "meeting_id": extracted["meeting_id"],
            "summary": "Sprint planning",
            "approved_items": [item],
        },
    )

    stored = meeting_store.get_item(item["id"])
    assert stored["ticket_id"].startswith("MEET-")
    assert stored["ticket_url"] == f"/tickets/{stored['ticket_id']}"


def test_meeting_survives_a_restart(client):
    extracted = _extract(client)

    with TestClient(main.app) as fresh_client:
        meetings = fresh_client.get("/meetings").json()

    assert [meeting["id"] for meeting in meetings] == [extracted["meeting_id"]]
