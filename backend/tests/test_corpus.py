import pytest
from fastapi.testclient import TestClient

import main
import rag.ingest as ingest


@pytest.fixture
def client():
    return TestClient(main.app)


def test_index_corpus_reports_how_many_tickets_were_indexed(client, monkeypatch):
    seen = {}

    async def _ingest(tickets, recreate=True):
        seen["count"] = len(tickets)
        return len(tickets)

    monkeypatch.setattr(ingest, "ingest_tickets", _ingest)

    body = client.post("/corpus/index").json()

    assert body["indexed"] == seen["count"] == 50
    assert body["collection"]


def test_index_corpus_reports_failures(client, monkeypatch):
    async def _broken(tickets, recreate=True):
        raise RuntimeError("Qdrant refused the connection")

    monkeypatch.setattr(ingest, "ingest_tickets", _broken)

    response = client.post("/corpus/index")

    assert response.status_code == 502
    assert "Qdrant refused" in response.json()["detail"]


def test_health_reports_word_based_dedup_when_semantic_is_off(client):
    assert client.get("/health").json()["dedup"] == "words"
