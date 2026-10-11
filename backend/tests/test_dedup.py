from agents.dedup import annotate_action_items, find_similar
from models.schemas import ActionItem


def _item(task: str, status: str = "new") -> ActionItem:
    return ActionItem(id="1", task=task, owner="Bob", priority="high", status=status)


def test_rate_limiting_matches_existing_ticket():
    matches = find_similar("Add rate limiting to the login endpoint")

    assert matches
    assert matches[0].id == "MEET-110"
    assert matches[0].score >= 0.45


def test_unrelated_task_is_not_a_duplicate():
    assert find_similar("Order lunch for the offsite") == []


def test_annotate_marks_duplicates_but_keeps_approved():
    duplicate = _item("Add rate limiting to the API")
    approved = _item("Add rate limiting to the API", status="approved")
    fresh = _item("Order lunch for the offsite")

    annotate_action_items([duplicate, approved, fresh])

    assert duplicate.status == "possible_duplicate"
    assert duplicate.similar_tickets[0].id == "MEET-110"
    assert approved.status == "approved"
    assert fresh.status == "new"
    assert fresh.similar_tickets == []
