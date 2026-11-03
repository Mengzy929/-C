"""Chapter-tree indexing, quote validation and a pure reading state machine."""

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class Paragraph:
    id: str
    text: str
    page: int | None = None


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    paragraphs: tuple[Paragraph, ...] = ()
    children: tuple["Section", ...] = ()


@dataclass(frozen=True)
class DocTree:
    id: str
    version: str
    title: str
    sections: tuple[Section, ...]
    synthetic: bool = True


@dataclass(frozen=True)
class QuoteSpan:
    doc_id: str
    doc_version: str
    paragraph_id: str
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class DocumentIndex:
    doc: DocTree
    paragraphs: Mapping[str, Paragraph]
    sections: Mapping[str, Section]


def build_index(doc: DocTree) -> DocumentIndex:
    """Iterative DFS, O(nodes + paragraphs); duplicate IDs fail explicitly."""
    paragraphs, sections = {}, {}
    stack = list(reversed(doc.sections))
    while stack:
        section = stack.pop()
        if not section.id or section.id in sections:
            raise ValueError(f"Duplicate/empty section id: {section.id}")
        sections[section.id] = section
        for paragraph in section.paragraphs:
            if not paragraph.id or paragraph.id in paragraphs:
                raise ValueError(f"Duplicate/empty paragraph id: {paragraph.id}")
            paragraphs[paragraph.id] = paragraph
        stack.extend(reversed(section.children))
    return DocumentIndex(doc, MappingProxyType(paragraphs), MappingProxyType(sections))


def locate(index: DocumentIndex, span: QuoteSpan) -> tuple[Paragraph, int, int]:
    """Offsets are paragraph-local Python Unicode code points, [start, end)."""
    if (span.doc_id, span.doc_version) != (index.doc.id, index.doc.version):
        raise ValueError("Document id/version mismatch")
    paragraph = index.paragraphs.get(span.paragraph_id)
    if paragraph is None:
        raise ValueError("Paragraph not found")
    if (
        type(span.start) is not int or type(span.end) is not int
        or not 0 <= span.start < span.end <= len(paragraph.text)
        or paragraph.text[span.start:span.end] != span.quote
    ):
        raise ValueError("Cannot locate quote: text or code-point offsets differ")
    return paragraph, span.start, span.end


def utf16_offsets(index: DocumentIndex, span: QuoteSpan) -> tuple[int, int]:
    """Explicit adapter for JS String.slice; do not change canonical spans."""
    paragraph, start, end = locate(index, span)
    return (
        len(paragraph.text[:start].encode("utf-16-le")) // 2,
        len(paragraph.text[:end].encode("utf-16-le")) // 2,
    )


class AnswerVerdict(StrEnum):
    PASS = "pass"
    OFF_TRACK = "off_track"
    EMPTY = "empty"
    WRONG = "wrong"


@dataclass(frozen=True)
class Question:
    id: str
    stage: int
    title: str
    text: str
    source: QuoteSpan
    keyword_groups: tuple[tuple[str, ...], ...]
    contradiction_phrases: tuple[str, ...]
    reference_answer: str
    hints: tuple[str, str, str]


@dataclass(frozen=True)
class Assessment:
    verdict: AnswerVerdict
    feedback: str
    method: str = "synthetic_fixture_keyword_rules"


def assess_demo(question: Question, answer: str, cited_paragraph: str | None) -> Assessment:
    """Fixture-only assessment. Real semantic assessment is supplied by B/A/D.

    Keyword hits are not sufficient evidence of understanding. This function
    deliberately makes no general claim about arbitrary papers or paraphrases.
    """
    normalized = "".join(answer.casefold().split())
    if not normalized or normalized in {"不知道", "不会", "不懂", "我不知道"}:
        return Assessment(AnswerVerdict.EMPTY, "还没有形成具体回答。先找到原文中的一句话。")
    if any(phrase in normalized for phrase in question.contradiction_phrases):
        return Assessment(AnswerVerdict.WRONG, "回答与示例原文存在矛盾，请重新核对高亮段落。")
    hits = all(any(word in normalized for word in group) for group in question.keyword_groups)
    if not hits:
        return Assessment(AnswerVerdict.OFF_TRACK, "尚未覆盖这道题的关键条件，请结合原文补充判断依据。")
    if cited_paragraph != question.source.paragraph_id:
        return Assessment(AnswerVerdict.OFF_TRACK, "回答方向符合示例规则，还需要选择支持它的原文段落。")
    return Assessment(AnswerVerdict.PASS, "已满足示例检查项，并绑定了原文位置。可继续下一层。")


@dataclass(frozen=True)
class ReadingState:
    stage: int = 1
    attempts: int = 0
    passed: bool = False
    saw_explanation: bool = False
    completed: bool = False

    def __post_init__(self):
        if type(self.stage) is not int or self.stage not in range(1, 6):
            raise ValueError("stage must be an integer in 1..5")
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("attempts must be a nonnegative integer")
        if any(type(flag) is not bool for flag in (
            self.passed, self.saw_explanation, self.completed
        )):
            raise ValueError("Reading flags must be booleans")
        if self.completed and (self.stage != 5 or not self.passed):
            raise ValueError("Only passed stage 5 can be complete")


def submit(state: ReadingState, assessment: Assessment) -> ReadingState:
    if state.completed:
        raise ValueError("Reading is complete")
    passed = assessment.verdict is AnswerVerdict.PASS
    return replace(state, passed=passed, attempts=state.attempts + (not passed))


def explain(state: ReadingState, *, confirmed: bool) -> ReadingState:
    if confirmed is not True:
        raise ValueError("Explanation requires explicit confirmation")
    if state.completed:
        raise ValueError("Reading is complete")
    return replace(state, passed=False, saw_explanation=True)


def advance(state: ReadingState) -> ReadingState:
    if state.completed:
        raise ValueError("Reading is already complete")
    if not state.passed:
        raise ValueError("Answer the current question before advancing")
    if state.stage == 5:
        return replace(state, completed=True)
    return ReadingState(stage=state.stage + 1)
