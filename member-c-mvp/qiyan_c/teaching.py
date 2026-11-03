"""Pure deterministic decisions. Rule loading belongs to assets.py."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .contracts import Intent, Mastery, TeachingDirective, TeachingRequest


@dataclass(frozen=True)
class RuleBook:
    version: str
    matrix: Mapping[tuple[str, str], tuple[int, ...]]
    penalties: tuple[int, ...]


def compile_rules(data: dict) -> RuleBook:
    """Validate external configuration and freeze a private copy."""
    if not isinstance(data.get("version"), str) or not data["version"]:
        raise ValueError("Rules need a nonempty version")
    penalties = data.get("penalties")
    if (
        not isinstance(penalties, list)
        or len(penalties) != 4
        or any(type(n) is not int or n < 0 for n in penalties)
    ):
        raise ValueError("penalties must contain four nonnegative integers")
    matrix = {}
    source = data.get("base")
    if not isinstance(source, dict) or set(source) != set(Intent):
        raise ValueError("Rules must cover exactly the five draft intents")
    for intent in Intent:
        row = source[intent]
        if not isinstance(row, dict) or set(row) != set(Mastery):
            raise ValueError(f"Incomplete mastery row: {intent}")
        for mastery in Mastery:
            levels = row[mastery]
            if (
                not isinstance(levels, list)
                or len(levels) != 4
                or any(type(n) is not int or n not in range(4) for n in levels)
            ):
                raise ValueError(f"Invalid matrix row: {intent}/{mastery}")
            matrix[(intent.value, mastery.value)] = tuple(levels)
    return RuleBook(data["version"], MappingProxyType(matrix), tuple(penalties))


def hard_ceiling(req: TeachingRequest) -> int:
    return 3 if req.attempts >= 2 or req.giveup else 2


def decide(req: TeachingRequest, rules: RuleBook) -> TeachingDirective:
    """attempts = completed unsuccessful answers for the CURRENT question.

    giveup is supplied only after explicit user confirmation. The five intent
    values and the v0.1 matrix are authored drafts, not team-frozen contracts.
    """
    ceiling = hard_ceiling(req)
    bucket = min(req.attempts, 3)
    base = rules.matrix[(req.intent.value, req.mastery.value)][bucket]
    penalty = rules.penalties[bucket]
    active = req.intent is not Intent.OFF_TOPIC
    level = min(base + penalty, ceiling)
    if req.giveup:
        level = 3
    if not active:
        level = 0
    questions = (
        "请先指出支持你判断的原文位置。",
        "读过提示后，你会怎样修正自己的回答？",
        "请按检查项作答，并说明判断依据。",
        "看过解释后，请回到原问题，用自己的话再答一次。",
    )
    forbidden = ["code_generation", "paper_ghostwriting"] if active else []
    if active and level < 3:
        forbidden.append("direct_answer")
    if active and level == 0:
        forbidden.append("structured_solution")
    return TeachingDirective(
        req.intent, level, req.scaffold, req.dimension,
        (questions[level],) if active else (), tuple(forbidden),
        f"matrix={base} penalty={penalty} ceiling={ceiling} "
        f"attempts={req.attempts} giveup={req.giveup} "
        f"override={'off_topic' if not active else 'giveup' if req.giveup else 'none'}",
        rules.version, active,
    )


def require_version(rules: RuleBook, pinned_version: str) -> RuleBook:
    if rules.version != pinned_version:
        raise ValueError("Pinned rules unavailable; do not silently use a new version")
    return rules
