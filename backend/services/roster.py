"""Map names heard in a meeting to tracker accounts."""

from __future__ import annotations

import json
from pathlib import Path

from config import settings

ROOT = Path(__file__).resolve().parent.parent.parent


class Roster:
    def __init__(self, path: Path | None = None):
        self._path = Path(path) if path else ROOT / settings.TEAM_ROSTER
        self._people: dict[str, dict] | None = None

    def _load(self) -> dict[str, dict]:
        if self._people is None:
            data = {}
            if self._path.exists():
                loaded = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = {
                        str(name).strip().lower(): person
                        for name, person in loaded.items()
                        if isinstance(person, dict)
                    }
            self._people = data
        return self._people

    def find(self, name: str) -> dict | None:
        key = (name or "").strip().lower()
        if not key:
            return None
        people = self._load()
        if key in people:
            return people[key]
        for full_name, person in people.items():
            if full_name.startswith(f"{key} ") or full_name.split(" ")[0] == key:
                return person
        return None

    def account_for(self, name: str, provider: str) -> str | None:
        person = self.find(name) or {}
        account = person.get(f"{provider}_account_id")
        return str(account) if account else None


roster = Roster()
