import json

import pytest
from fastapi.testclient import TestClient

import main
from agents import extraction
from services import ticket_store


RESPONSE = {
    "summary": "Login work.",
    "decisions": [],
    "action_items": [
        {
            "task": "Add rate limiting to the login endpoint",
            "owner": "Bob",
            "due_date": "2026-09-16",
            "priority": "high",
            "source_segment": "I will do it by Wednesday.",
        }
    ],
}


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ticket_store, "LOCAL_PATH", tmp_path / "local_tickets.json")


@pytest.fixture
def client(isolated_store, monkeypatch):
    async def _complete(system_prompt, user_prompt):
        return json.dumps(RESPONSE)

    monkeypatch.setattr(extraction.llm_provider, "complete", _complete)
    return TestClient(main.app)


def test_extract_flags_duplicate_ticket(client):
    body = client.post(
        "/extract",
        json={"transcript": "Bob: I will add rate limiting by Wednesday."},
    ).json()

    item = body["action_items"][0]
    assert item["status"] == "possible_duplicate"
    assert item["similar_tickets"][0]["id"] == "MEET-110"


def test_dispatch_creates_local_ticket(client):
    item = {
        "id": "item-1",
        "task": "Write the on-call rota",
        "owner": "Carol",
        "priority": "medium",
        "status": "approved",
    }

    response = client.post(
        "/dispatch",
        json={"meeting_id": "m1", "summary": "Ops", "approved_items": [item]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tickets_created"] == 1
    ticket_id = body["results"][0]["jira_ticket_id"]
    assert ticket_id.startswith("MEET-")

    listed = client.get("/tickets").json()["tickets"]
    assert any(ticket["id"] == ticket_id for ticket in listed)
    detail = client.get(f"/tickets/{ticket_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Write the on-call rota"


def test_dispatch_rejects_empty_list(client):
    assert client.post("/dispatch", json={"meeting_id": "m1", "approved_items": []}).status_code == 422


def test_missing_ticket_is_404(client):
    assert client.get("/tickets/MEET-missing").status_code == 404
