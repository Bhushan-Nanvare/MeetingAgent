import pytest
import uuid
from pydantic import ValidationError
from models.schemas import ActionItem, ExtractionResult, JobStatus, DispatchResult
from datetime import datetime, timezone


def _make_action_item(**kwargs) -> ActionItem:
    defaults = dict(
        id=str(uuid.uuid4()),
        task="Fix the login bug",
        owner="Alice",
        priority="high",
    )
    defaults.update(kwargs)
    return ActionItem(**defaults)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_action_item_valid():
    item = _make_action_item()
    assert item.status == "new"
    assert item.similar_tickets == []


def test_action_item_invalid_priority():
    with pytest.raises(ValidationError):
        _make_action_item(priority="critical")


def test_action_item_similar_tickets_default():
    item = _make_action_item()
    assert item.similar_tickets == []


def test_extraction_result_valid():
    items = [_make_action_item(), _make_action_item(task="Deploy to prod", owner="Bob", priority="medium")]
    result = ExtractionResult(
        meeting_id=str(uuid.uuid4()),
        summary="Q3 planning sync",
        decisions=["Use FastAPI", "Ship by Friday"],
        action_items=items,
        extracted_at=_now(),
    )
    assert len(result.action_items) == 2


def test_dispatch_result_partial():
    dr = DispatchResult(
        item_id=str(uuid.uuid4()),
        task="Create Jira ticket",
        status="partial",
        errors=["Jira failed"],
        dispatched_at=_now(),
    )
    assert len(dr.errors) == 1


def test_job_status_queued():
    js = JobStatus(
        job_id=str(uuid.uuid4()),
        status="queued",
        created_at=_now(),
        updated_at=_now(),
    )
    assert js.result is None
    assert js.error_message is None
