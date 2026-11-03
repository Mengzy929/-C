"""Immutable learning-event reduction. Persistence/scheduling remain external."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class LearningEvent:
    id: str
    question_id: str
    kind: str
    occurred_at: str
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Ledger:
    events: tuple[LearningEvent, ...] = ()


def reduce_events(ledger: Ledger, incoming: tuple[LearningEvent, ...]) -> Ledger:
    """O(N+M) reduction, preserving original order, rejecting ID collisions."""
    seen = {event.id: event for event in ledger.events}
    if len(seen) != len(ledger.events):
        raise ValueError("Existing ledger contains duplicate IDs")
    result = list(ledger.events)
    for event in incoming:
        if not event.id or not event.question_id:
            raise ValueError("Event and question IDs cannot be empty")
        if event.id in seen:
            if seen[event.id] != event:
                raise ValueError("Same event ID reused with different content")
            continue
        seen[event.id] = event
        result.append(event)
    return Ledger(tuple(result))


def giveup_events(question_id: str, occurred_at: str, *, review_days: int = 5) -> tuple[LearningEvent, ...]:
    if type(review_days) is not int or not 3 <= review_days <= 7:
        raise ValueError("Review interval must be 3..7 days")
    timestamp = datetime.fromisoformat(occurred_at)
    if timestamp.tzinfo is None:
        raise ValueError("An explicit timezone is required")
    due = (timestamp + timedelta(days=review_days)).isoformat()
    return (
        LearningEvent(f"{question_id}:giveup", question_id, "explicit_giveup", occurred_at,
                      (("weight", "-0.8"), ("status", "intent_only"))),
        LearningEvent(f"{question_id}:scaffold", question_id, "scaffold_failure", occurred_at),
        LearningEvent(f"{question_id}:review", question_id, "review_requested", occurred_at,
                      (("due_at", due), ("scheduled", "false"))),
    )
