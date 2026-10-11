"""Read the sample ticket corpus and keep locally filed tickets on disk."""

from __future__ import annotations

import json
import re
import threading
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MOCK_PATH = ROOT / "data" / "mock_tickets.json"
LOCAL_PATH = ROOT / "data" / "local_tickets.json"
_ID_RE = re.compile(r"^MEET-(\d+)$")
_lock = threading.Lock()


def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def all_tickets() -> list[dict]:
    """Sample tickets plus anything filed from the review page."""
    with _lock:
        mock = _read_json(MOCK_PATH)
        local = _read_json(LOCAL_PATH)
    seen = {ticket.get("id") for ticket in mock}
    combined = list(mock)
    for ticket in local:
        if ticket.get("id") not in seen:
            combined.append(ticket)
            seen.add(ticket.get("id"))
    return combined


def get_ticket(ticket_id: str) -> dict | None:
    for ticket in all_tickets():
        if ticket.get("id") == ticket_id:
            return ticket
    return None


def _next_id(existing: list[dict]) -> str:
    numbers = []
    for ticket in existing:
        match = _ID_RE.match(str(ticket.get("id") or ""))
        if match:
            numbers.append(int(match.group(1)))
    return f"MEET-{(max(numbers) if numbers else 100) + 1}"


def create_ticket(
    *,
    title: str,
    description: str,
    assignee: str,
    priority: str,
    meeting_id: str,
) -> dict:
    with _lock:
        existing = _read_json(MOCK_PATH) + _read_json(LOCAL_PATH)
        ticket = {
            "id": _next_id(existing),
            "title": title,
            "description": description,
            "status": "open",
            "assignee": assignee or "Unassigned",
            "priority": priority,
            "created_at": date.today().isoformat(),
            "meeting_id": meeting_id,
            "source": "meetingagent",
        }
        local = _read_json(LOCAL_PATH)
        local.append(ticket)
        LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_PATH.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
        return ticket
