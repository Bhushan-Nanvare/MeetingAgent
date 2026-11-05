"""Read and write meetings, decisions and action items."""

from __future__ import annotations

from datetime import date, datetime, timezone

from models.schemas import ActionItem, ExtractionResult
from services.db import session

CLOSED_STATUSES = ("done", "rejected")
EDITABLE_FIELDS = ("task", "owner", "due_date", "priority", "status")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_meeting(
    result: ExtractionResult,
    meeting_date: str | None = None,
    attendees: list[str] | None = None,
    title: str = "",
) -> None:
    now = _now()
    with session() as conn:
        conn.execute(
            """
            INSERT INTO meetings (id, title, meeting_date, summary, attendees, transcript_length, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                meeting_date = excluded.meeting_date,
                summary = excluded.summary,
                attendees = excluded.attendees,
                transcript_length = excluded.transcript_length
            """,
            (
                result.meeting_id,
                title or _default_title(meeting_date),
                meeting_date,
                result.summary,
                ", ".join(attendees or []),
                result.transcript_length,
                now,
            ),
        )
        conn.execute("DELETE FROM decisions WHERE meeting_id = ?", (result.meeting_id,))
        conn.executemany(
            "INSERT INTO decisions (meeting_id, text, position) VALUES (?, ?, ?)",
            [(result.meeting_id, text, i) for i, text in enumerate(result.decisions)],
        )
        for item in result.action_items:
            _upsert_item(conn, item, result.meeting_id, now)


def _default_title(meeting_date: str | None) -> str:
    return f"Meeting {meeting_date or date.today().isoformat()}"


def _upsert_item(conn, item: ActionItem, meeting_id: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO action_items
            (id, meeting_id, task, owner, due_date, priority, status, source_segment,
             ticket_id, ticket_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            task = excluded.task,
            owner = excluded.owner,
            due_date = excluded.due_date,
            priority = excluded.priority,
            status = excluded.status,
            source_segment = excluded.source_segment,
            ticket_id = COALESCE(excluded.ticket_id, action_items.ticket_id),
            ticket_url = COALESCE(excluded.ticket_url, action_items.ticket_url),
            updated_at = excluded.updated_at
        """,
        (
            item.id,
            meeting_id,
            item.task,
            item.owner,
            item.due_date,
            item.priority,
            item.status,
            item.source_segment,
            item.jira_ticket_id,
            item.jira_url,
            now,
            now,
        ),
    )


def save_items(items: list[ActionItem], meeting_id: str) -> None:
    """Persist edits made on the review page, including filed ticket links."""
    now = _now()
    with session() as conn:
        known = conn.execute("SELECT id FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if known is None:
            conn.execute(
                "INSERT INTO meetings (id, title, summary, created_at) VALUES (?, ?, ?, ?)",
                (meeting_id, _default_title(None), "", now),
            )
        for item in items:
            _upsert_item(conn, item, meeting_id, now)


def list_meetings(limit: int = 50) -> list[dict]:
    with session() as conn:
        rows = conn.execute(
            """
            SELECT m.*,
                   COUNT(a.id) AS total_items,
                   SUM(CASE WHEN a.status NOT IN ('done', 'rejected') THEN 1 ELSE 0 END) AS open_items
            FROM meetings m
            LEFT JOIN action_items a ON a.meeting_id = m.id
            GROUP BY m.id
            ORDER BY COALESCE(m.meeting_date, m.created_at) DESC, m.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_meeting_row(row) for row in rows]


def get_meeting(meeting_id: str) -> dict | None:
    with session() as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            return None
        decisions = conn.execute(
            "SELECT text FROM decisions WHERE meeting_id = ? ORDER BY position",
            (meeting_id,),
        ).fetchall()
        items = conn.execute(
            "SELECT * FROM action_items WHERE meeting_id = ? ORDER BY created_at",
            (meeting_id,),
        ).fetchall()

    meeting = _meeting_row(row)
    meeting["decisions"] = [d["text"] for d in decisions]
    meeting["action_items"] = [dict(item) for item in items]
    meeting["total_items"] = len(items)
    meeting["open_items"] = sum(
        1 for item in items if item["status"] not in CLOSED_STATUSES
    )
    return meeting


def open_items(exclude_meeting: str | None = None, limit: int = 50) -> list[dict]:
    with session() as conn:
        rows = conn.execute(
            f"""
            SELECT a.*, m.title AS meeting_title, m.meeting_date, m.created_at AS meeting_created_at
            FROM action_items a
            JOIN meetings m ON m.id = a.meeting_id
            WHERE a.status NOT IN ('done', 'rejected')
              AND (? IS NULL OR a.meeting_id != ?)
            ORDER BY COALESCE(m.meeting_date, m.created_at) DESC,
                     CASE a.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT ?
            """,
            (exclude_meeting, exclude_meeting, limit),
        ).fetchall()
    return [_open_item_row(row) for row in rows]


def update_item(item_id: str, changes: dict) -> dict | None:
    fields = {key: value for key, value in changes.items() if key in EDITABLE_FIELDS}
    if not fields:
        return get_item(item_id)

    assignments = ", ".join(f"{field} = ?" for field in fields)
    values = list(fields.values())
    now = _now()

    with session() as conn:
        updated = conn.execute(
            f"UPDATE action_items SET {assignments}, updated_at = ? WHERE id = ?",
            [*values, now, item_id],
        )
        if updated.rowcount == 0:
            return None
        if "status" in fields:
            closed_at = now if fields["status"] in CLOSED_STATUSES else None
            conn.execute(
                "UPDATE action_items SET closed_at = ? WHERE id = ?", (closed_at, item_id)
            )
    return get_item(item_id)


def get_item(item_id: str) -> dict | None:
    with session() as conn:
        row = conn.execute("SELECT * FROM action_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def search(query: str, limit: int = 20) -> dict:
    term = f"%{query.strip().lower()}%"
    with session() as conn:
        decisions = conn.execute(
            """
            SELECT d.text, m.id AS meeting_id, m.title AS meeting_title, m.meeting_date
            FROM decisions d JOIN meetings m ON m.id = d.meeting_id
            WHERE LOWER(d.text) LIKE ?
            ORDER BY COALESCE(m.meeting_date, m.created_at) DESC
            LIMIT ?
            """,
            (term, limit),
        ).fetchall()
        items = conn.execute(
            """
            SELECT a.*, m.title AS meeting_title, m.meeting_date
            FROM action_items a JOIN meetings m ON m.id = a.meeting_id
            WHERE LOWER(a.task) LIKE ? OR LOWER(a.owner) LIKE ?
            ORDER BY COALESCE(m.meeting_date, m.created_at) DESC
            LIMIT ?
            """,
            (term, term, limit),
        ).fetchall()
        meetings = conn.execute(
            """
            SELECT id, title, meeting_date, summary FROM meetings
            WHERE LOWER(summary) LIKE ? OR LOWER(title) LIKE ?
            ORDER BY COALESCE(meeting_date, created_at) DESC
            LIMIT ?
            """,
            (term, term, limit),
        ).fetchall()

    return {
        "decisions": [dict(row) for row in decisions],
        "action_items": [dict(row) for row in items],
        "meetings": [dict(row) for row in meetings],
    }


def _meeting_row(row) -> dict:
    meeting = dict(row)
    meeting["total_items"] = int(meeting.get("total_items") or 0)
    meeting["open_items"] = int(meeting.get("open_items") or 0)
    meeting["attendees"] = [
        name.strip() for name in str(meeting.get("attendees") or "").split(",") if name.strip()
    ]
    return meeting


def _open_item_row(row) -> dict:
    item = dict(row)
    reference = item.get("meeting_date") or (item.get("meeting_created_at") or "")[:10]
    item["days_open"] = _days_since(reference)
    item["overdue"] = bool(
        item.get("due_date") and item["due_date"] < date.today().isoformat()
    )
    item.pop("meeting_created_at", None)
    return item


def _days_since(day: str) -> int:
    try:
        return max((date.today() - date.fromisoformat(day)).days, 0)
    except (TypeError, ValueError):
        return 0
