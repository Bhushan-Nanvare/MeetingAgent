"""Score extraction quality against the labelled cases in cases.json.

    python evals/run_eval.py             all cases
    python evals/run_eval.py hiring-sync one case

This calls the real model, so it spends API quota. Results are written to
evals/results/<timestamp>.json so you can compare runs after a prompt change.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.extraction import extract_meeting  # noqa: E402
from config import settings  # noqa: E402

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases.json"
RESULTS = HERE / "results"


def matches(expected: dict, task: str) -> bool:
    lowered = task.lower()
    return all(keyword.lower() in lowered for keyword in expected["keywords"])


def score_case(case: dict, result) -> dict:
    predictions = list(result.action_items)
    expected = list(case["expected_items"])

    pairs: list[tuple[dict, object]] = []
    missed: list[list[str]] = []
    unmatched = list(predictions)
    for want in expected:
        hit = next((item for item in unmatched if matches(want, item.task)), None)
        if hit:
            unmatched.remove(hit)
            pairs.append((want, hit))
        else:
            missed.append(want["keywords"])

    forbidden = [
        item.task
        for item in predictions
        if any(word.lower() in item.task.lower() for word in case.get("forbidden_keywords", []))
    ]
    owners_right = sum(1 for want, got in pairs if got.owner == want["owner"])
    dates_right = sum(1 for want, got in pairs if (got.due_date or None) == want["due_date"])

    found_decisions = sum(
        1
        for words in case.get("expected_decisions", [])
        if any(
            all(word.lower() in decision.lower() for word in words)
            for decision in result.decisions
        )
    )

    return {
        "case": case["id"],
        "expected_items": len(expected),
        "predicted_items": len(predictions),
        "matched_items": len(pairs),
        "missed": missed,
        "extra_items": [item.task for item in unmatched],
        "invented_from_parked_ideas": forbidden,
        "owners_right": owners_right,
        "dates_right": dates_right,
        "expected_decisions": len(case.get("expected_decisions", [])),
        "found_decisions": found_decisions,
    }


def totals(scores: list[dict]) -> dict:
    expected = sum(score["expected_items"] for score in scores)
    predicted = sum(score["predicted_items"] for score in scores)
    matched = sum(score["matched_items"] for score in scores)
    precision = matched / predicted if predicted else 1.0
    recall = matched / expected if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    decisions_expected = sum(score["expected_decisions"] for score in scores)

    return {
        "cases": len(scores),
        "item_precision": round(precision, 3),
        "item_recall": round(recall, 3),
        "item_f1": round(f1, 3),
        "owner_accuracy": round(
            sum(score["owners_right"] for score in scores) / matched, 3
        )
        if matched
        else 0.0,
        "due_date_accuracy": round(
            sum(score["dates_right"] for score in scores) / matched, 3
        )
        if matched
        else 0.0,
        "decision_recall": round(
            sum(score["found_decisions"] for score in scores) / decisions_expected, 3
        )
        if decisions_expected
        else 1.0,
        "parked_ideas_turned_into_tasks": sum(
            len(score["invented_from_parked_ideas"]) for score in scores
        ),
    }


async def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        cases = [case for case in cases if case["id"] in wanted]
        if not cases:
            print(f"No case matches {', '.join(wanted)}")
            return 1

    print(f"Model: {settings.LLM_MODEL}  cases: {len(cases)}\n")
    scores = []
    for case in cases:
        result = await extract_meeting(
            case["transcript"],
            meeting_id=case["id"],
            meeting_date=case.get("meeting_date"),
            attendees=case.get("attendees", []),
        )
        score = score_case(case, result)
        scores.append(score)
        print(
            f"{score['case']:<18} items {score['matched_items']}/{score['expected_items']} "
            f"found, {len(score['extra_items'])} extra, "
            f"owners {score['owners_right']}/{score['matched_items']}, "
            f"dates {score['dates_right']}/{score['matched_items']}, "
            f"decisions {score['found_decisions']}/{score['expected_decisions']}"
        )
        for task in score["invented_from_parked_ideas"]:
            print(f"    turned a parked idea into a task: {task}")

    summary = totals(scores)
    print("\nOverall")
    for key, value in summary.items():
        print(f"  {key.replace('_', ' '):<32} {value}")

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RESULTS / f"{stamp}.json"
    path.write_text(
        json.dumps(
            {"model": settings.LLM_MODEL, "summary": summary, "cases": scores}, indent=2
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {path.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
