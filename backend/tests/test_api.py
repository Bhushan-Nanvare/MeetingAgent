import json

import pytest
from fastapi.testclient import TestClient

import main
from agents import extraction

RESPONSE = {
    "summary": "Login work and the release schedule.",
    "decisions": ["Release every Thursday"],
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

VTT = b"""WEBVTT

1
00:00:01.000 --> 00:00:05.000
<v Bob Mehta>I will add rate limiting by Wednesday.</v>
"""


@pytest.fixture
def client(monkeypatch):
    async def _complete(system_prompt, user_prompt):
        return json.dumps(RESPONSE)

    monkeypatch.setattr(extraction.llm_provider, "complete", _complete)
    return TestClient(main.app)


def test_review_page_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "MeetingAgent" in response.text


def test_health(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["llm_model"]


def test_extract_returns_action_items(client):
    response = client.post(
        "/extract",
        json={
            "transcript": "Bob: I will add rate limiting by Wednesday.",
            "meeting_date": "2026-09-15",
            "attendees": ["Bob Mehta"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action_items"][0]["owner"] == "Bob Mehta"
    assert body["action_items"][0]["status"] == "possible_duplicate"
    assert body["action_items"][0]["similar_tickets"][0]["id"] == "MEET-110"
    assert body["decisions"] == ["Release every Thursday"]


def test_extract_rejects_empty_transcript(client):
    assert client.post("/extract", json={"transcript": "   "}).status_code == 422


def test_extract_file_accepts_vtt(client):
    response = client.post(
        "/extract/file",
        files={"file": ("meeting.vtt", VTT, "text/vtt")},
        data={"attendees": "Bob Mehta, Alice Fernandes"},
    )

    assert response.status_code == 200
    assert response.json()["action_items"][0]["task"]


def test_extract_file_rejects_other_file_types(client):
    response = client.post(
        "/extract/file",
        files={"file": ("meeting.mp3", b"not a transcript", "audio/mpeg")},
    )

    assert response.status_code == 415


def test_model_failure_returns_502(client, monkeypatch):
    async def _boom(system_prompt, user_prompt):
        raise RuntimeError("Gemini is down")

    monkeypatch.setattr(extraction.llm_provider, "complete", _boom)

    response = client.post("/extract", json={"transcript": "Bob: I will do it."})

    assert response.status_code == 502
