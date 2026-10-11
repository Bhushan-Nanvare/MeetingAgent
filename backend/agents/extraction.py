"""Turn a meeting transcript into a summary, decisions and action items."""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from models.schemas import ActionItem, ExtractionResult
from providers.llm import llm_provider

logger = logging.getLogger(__name__)

# Roughly 30k tokens. A two hour meeting fits; anything longer is cut with a warning.
MAX_TRANSCRIPT_CHARS = 120_000
MAX_SEGMENT_CHARS = 500

_PRIORITIES = {"high", "medium", "low"}
_UNOWNED = {"", "unassigned", "none", "null", "n/a", "na", "tbd", "team", "everyone"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$")

SYSTEM_PROMPT = """You are a meeting notes assistant for a software team. You read a \
meeting transcript and return structured notes.

Return ONLY a JSON object in exactly this shape:
{
  "summary": "3-6 sentences on what was discussed and what happens next",
  "decisions": ["something the team actually settled on"],
  "action_items": [
    {
      "task": "short imperative description, e.g. 'Add rate limiting to the login endpoint'",
      "owner": "the person who took the work, or 'Unassigned'",
      "due_date": "YYYY-MM-DD, or null",
      "priority": "high, medium or low",
      "source_segment": "the sentence from the transcript this came from, copied word for word"
    }
  ]
}

Rules:
- Only record an action item when someone committed to work or was clearly given it. \
Ignore ideas nobody picked up, such as "we should look at that some day".
- Never invent an owner or a deadline. Use "Unassigned" and null when the transcript does not say.
- Turn relative deadlines such as "by Friday" into real dates using the meeting date given \
below. If no meeting date is given, use null.
- priority: high when it blocks someone, is urgent, or affects customers; low when it is a \
nice-to-have; otherwise medium.
- A decision is something settled ("we will move to Postgres"), not a topic that was discussed.
- Use the speaker names exactly as they appear in the transcript.
- If there are no decisions or action items, return empty lists. Never pad the output."""


class ExtractionError(RuntimeError):
    """The model returned something that could not be read as meeting notes."""


async def extract_meeting(
    transcript: str,
    meeting_id: str | None = None,
    meeting_date: str | None = None,
    attendees: list[str] | None = None,
) -> ExtractionResult:
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("Transcript is empty")

    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        logger.warning(
            f"Transcript is {len(transcript)} chars, truncating to {MAX_TRANSCRIPT_CHARS}"
        )
        transcript = transcript[:MAX_TRANSCRIPT_CHARS]

    raw = await llm_provider.complete(
        SYSTEM_PROMPT, _build_user_prompt(transcript, meeting_date, attendees)
    )
    data = _parse_json(raw)

    items = [
        item
        for item in (
            _build_action_item(entry, attendees)
            for entry in _as_list(data.get("action_items"))
        )
        if item is not None
    ]

    result = ExtractionResult(
        meeting_id=meeting_id or str(uuid.uuid4()),
        summary=str(data.get("summary") or "").strip(),
        decisions=[str(d).strip() for d in _as_list(data.get("decisions")) if str(d).strip()],
        action_items=items,
        transcript_length=len(transcript),
        extracted_at=datetime.now(timezone.utc).isoformat(),
    )
    logger.info(
        f"Extracted {len(result.action_items)} action items and "
        f"{len(result.decisions)} decisions from {len(transcript)} chars"
    )
    return result


def _build_user_prompt(
    transcript: str, meeting_date: str | None, attendees: list[str] | None
) -> str:
    parts = []
    if meeting_date:
        parts.append(f"Meeting date: {meeting_date}")
    if attendees:
        parts.append(f"Attendees: {', '.join(attendees)}")
    parts.append(f"Transcript:\n{transcript}")
    return "\n\n".join(parts)


def _parse_json(raw: str) -> dict:
    text = _CODE_FENCE.sub("", (raw or "").strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Model did not return valid JSON: {e}. Got: {text[:200]}") from e
    if not isinstance(data, dict):
        raise ExtractionError(f"Model returned {type(data).__name__}, expected an object")
    return data


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _build_action_item(entry, attendees: list[str] | None) -> ActionItem | None:
    """Return a validated item, or None when the model gave us nothing usable."""
    if not isinstance(entry, dict):
        return None
    task = str(entry.get("task") or "").strip()
    if not task:
        return None

    priority = str(entry.get("priority") or "").strip().lower()
    segment = str(entry.get("source_segment") or "").strip()

    return ActionItem(
        id=str(uuid.uuid4()),
        task=task,
        owner=_match_owner(entry.get("owner"), attendees),
        due_date=_clean_due_date(entry.get("due_date")),
        priority=priority if priority in _PRIORITIES else "medium",
        source_segment=segment[:MAX_SEGMENT_CHARS] or None,
    )


def _match_owner(raw_owner, attendees: list[str] | None) -> str:
    """Map a name from the transcript onto the attendee list where possible."""
    name = str(raw_owner or "").strip()
    if name.lower() in _UNOWNED:
        return "Unassigned"
    if not attendees:
        return name

    lowered = name.lower()
    for attendee in attendees:
        candidate = attendee.strip()
        if not candidate:
            continue
        if candidate.lower() == lowered or candidate.lower().startswith(f"{lowered} "):
            return candidate
    return name


def _clean_due_date(raw_date) -> str | None:
    """Keep real YYYY-MM-DD dates only; drop things like "next Friday"."""
    value = str(raw_date or "").strip()
    if not _ISO_DATE.match(value):
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return value
