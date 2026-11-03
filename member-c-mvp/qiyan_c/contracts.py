"""Draft data contracts only; no IO, model clients or persistence."""

from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    UNDERSTAND = "understand"
    LOCATE = "locate"
    EVALUATE = "evaluate"
    REFLECT = "reflect"
    OFF_TOPIC = "off_topic"


class Dimension(StrEnum):
    SEARCH = "search"
    READING = "critical_reading"
    DESIGN = "experiment_design"
    STATISTICS = "statistical_judgment"
    EXPRESSION = "academic_expression"


class Mastery(StrEnum):
    NOVICE = "novice"
    GUIDED = "guided"
    INDEPENDENT = "independent"


@dataclass(frozen=True)
class TeachingRequest:
    intent: Intent
    dimension: Dimension
    mastery: Mastery
    scaffold: int = 0
    attempts: int = 0
    giveup: bool = False

    def __post_init__(self):
        for value, enum in (
            (self.intent, Intent), (self.dimension, Dimension), (self.mastery, Mastery)
        ):
            if not isinstance(value, enum):
                raise ValueError(f"Expected {enum.__name__}, got {value!r}")
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("attempts must be a nonnegative integer")
        if type(self.scaffold) is not int or self.scaffold not in range(4):
            raise ValueError("scaffold must be an integer in 0..3")
        if type(self.giveup) is not bool:
            raise ValueError("giveup must be a boolean")


@dataclass(frozen=True)
class TeachingDirective:
    intent: Intent
    hint_level: int
    scaffold_level: int
    dimension: Dimension
    must_ask: tuple[str, ...]
    forbidden: tuple[str, ...]
    rationale: str
    rule_version: str
    active: bool = True


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reasons: tuple[str, ...]
    action: str  # display / rewrite / suppress
    safe_text: str


@dataclass(frozen=True)
class PromptBundle:
    text: str
    token_count: int
    measurement: str  # tokenizer / utf8_byte_estimate / skipped
