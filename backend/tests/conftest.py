import pytest

from config import settings
from services import db, ticket_store


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Every test gets its own database and local ticket file."""
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(ticket_store, "LOCAL_PATH", tmp_path / "local_tickets.json")
    db.init_db()


@pytest.fixture(autouse=True)
def offline_dedup(monkeypatch):
    """Tests never call embeddings or Qdrant unless they ask for it."""
    monkeypatch.setattr(settings, "SEMANTIC_DEDUP", False)
