import json

import pytest

from agents import extraction
from agents.extraction import ExtractionError, extract_meeting

VALID_RESPONSE = {
    "summary": "The team discussed login problems and releases.",
    "decisions": ["Release every Thursday", "  "],
    "action_items": [
        {
            "task": "Build the email based password reset flow",
            "owner": "Alice",
            "due_date": "2026-09-18",
            "priority": "high",
            "source_segment": "I will build the email based reset flow.",
        },
        {
            "task": "Add rate limiting to the login endpoint",
            "owner": "Bob Mehta",
            "due_date": None,
            "priority": "high",
            "source_segment": "I will do it by Wednesday.",
        },
    ],
}


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the model call with a canned response."""

    def _install(payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)

        async def _complete(system_prompt, user_prompt):
            _install.last_user_prompt = user_prompt
            return text

        monkeypatch.setattr(extraction.llm_provider, "complete", _complete)

    return _install


async def test_returns_validated_items(fake_llm):
    fake_llm(VALID_RESPONSE)

    result = await extract_meeting("Alice: I will build the reset flow.", meeting_id="m1")

    assert result.meeting_id == "m1"
    assert len(result.action_items) == 2
    assert result.decisions == ["Release every Thursday"]
    assert result.transcript_length == len("Alice: I will build the reset flow.")
    assert all(item.status == "new" for item in result.action_items)
    assert len({item.id for item in result.action_items}) == 2


async def test_bad_priority_and_date_are_cleaned(fake_llm):
    fake_llm(
        {
            "summary": "s",
            "decisions": [],
            "action_items": [
                {
                    "task": "Look at the slow queries",
                    "owner": "",
                    "due_date": "next Friday",
                    "priority": "critical",
                }
            ],
        }
    )

    item = (await extract_meeting("transcript")).action_items[0]

    assert item.priority == "medium"
    assert item.due_date is None
    assert item.owner == "Unassigned"


async def test_impossible_date_is_dropped(fake_llm):
    fake_llm(
        {
            "summary": "s",
            "decisions": [],
            "action_items": [
                {"task": "t", "owner": "Bob", "due_date": "2026-02-31", "priority": "low"}
            ],
        }
    )

    assert (await extract_meeting("transcript")).action_items[0].due_date is None


async def test_owner_is_matched_to_the_attendee_list(fake_llm):
    fake_llm(VALID_RESPONSE)

    result = await extract_meeting(
        "transcript", attendees=["Alice Fernandes", "Bob Mehta", "Carol D'Souza"]
    )

    assert result.action_items[0].owner == "Alice Fernandes"
    assert result.action_items[1].owner == "Bob Mehta"


async def test_items_without_a_task_are_skipped(fake_llm):
    fake_llm(
        {
            "summary": "s",
            "decisions": [],
            "action_items": [
                {"task": "", "owner": "Alice", "priority": "high"},
                "not an object",
                {"task": "Real work", "owner": "Alice", "priority": "high"},
            ],
        }
    )

    items = (await extract_meeting("transcript")).action_items

    assert [item.task for item in items] == ["Real work"]


async def test_code_fences_are_stripped(fake_llm):
    fake_llm(f"```json\n{json.dumps(VALID_RESPONSE)}\n```")

    assert len((await extract_meeting("transcript")).action_items) == 2


async def test_meeting_date_and_attendees_reach_the_prompt(fake_llm):
    fake_llm(VALID_RESPONSE)

    await extract_meeting("transcript", meeting_date="2026-09-15", attendees=["Alice Fernandes"])

    prompt = fake_llm.last_user_prompt
    assert "Meeting date: 2026-09-15" in prompt
    assert "Attendees: Alice Fernandes" in prompt


async def test_long_transcript_is_truncated(fake_llm):
    fake_llm(VALID_RESPONSE)
    long_transcript = "a" * (extraction.MAX_TRANSCRIPT_CHARS + 500)

    result = await extract_meeting(long_transcript)

    assert result.transcript_length == extraction.MAX_TRANSCRIPT_CHARS


async def test_invalid_json_raises_extraction_error(fake_llm):
    fake_llm("sorry, I cannot help with that")

    with pytest.raises(ExtractionError):
        await extract_meeting("transcript")


async def test_json_list_raises_extraction_error(fake_llm):
    fake_llm("[1, 2, 3]")

    with pytest.raises(ExtractionError):
        await extract_meeting("transcript")


async def test_empty_transcript_raises_value_error(fake_llm):
    fake_llm(VALID_RESPONSE)

    with pytest.raises(ValueError):
        await extract_meeting("   ")
