"""Heuristic checks, NOT general semantic verification. No model or IO."""

import re
import unicodedata

from .contracts import GuardResult, TeachingDirective

SAFE_FALLBACK = "这次提示未通过检查。请先定位原文中的相关句子，再尝试说明你的依据。"


def _normalize(text: str) -> str:
    return "".join(
        c.casefold() for c in unicodedata.normalize("NFKC", text)
        if c.isalnum()
    )


def detect(
    text: str,
    directive: TeachingDirective,
    known_answers: tuple[str, ...] = (),
    *,
    rewrites_used: int = 0,
) -> GuardResult:
    if type(rewrites_used) is not int or rewrites_used not in (0, 1):
        raise ValueError("Only zero or one completed rewrite is permitted")
    if not isinstance(text, str) or not text.strip():
        return GuardResult(False, ("empty_output",), "suppress", SAFE_FALLBACK)
    reasons = []
    if "code_generation" in directive.forbidden and re.search(
        r"```\s*(?:python|javascript|typescript|cpp|c\+\+|java|bash|sh)\b"
        r"|\bdef\s+\w+\s*\(|\bimport\s+(?:os|subprocess)\b"
        r"|以下(?:是|为).{0,8}(?:完整|可运行)代码", text, re.I
    ):
        reasons.append("code_generation")
    if "paper_ghostwriting" in directive.forbidden and re.search(
        r"(?:以下|下面)(?:是|为).{0,8}(?:可直接提交的|代写的)(?:论文|正文)"
        r"|(?:直接复制|照抄).{0,8}(?:提交|论文)", text
    ):
        reasons.append("paper_ghostwriting")
    if "direct_answer" in directive.forbidden:
        if re.search(
            r"(?:标准答案|正确答案|答案|结论)(?:(?:就是|为|是)(?!否|什么|哪|怎样|如何|怎么|何)|如下|[:：])"
            r"|(?:the\s+)?(?:correct\s+)?answer\s*(?:is|:)"
            r"|直接告诉你[：:]", text, re.I
        ):
            reasons.append("answer_marker")
        normalized = _normalize(text)
        if any(
            len(_normalize(answer)) >= 6 and _normalize(answer) in normalized
            for answer in known_answers
        ):
            reasons.append("known_answer_leak")
    if "structured_solution" in directive.forbidden and len(
        re.findall(r"(?m)^\s*(?:\d+[.)、]|[-*])\s*\S", text)
    ) >= 2:
        reasons.append("structured_solution")
    if reasons:
        return GuardResult(
            False, tuple(reasons), "rewrite" if rewrites_used == 0 else "suppress",
            SAFE_FALLBACK,
        )
    return GuardResult(True, (), "display", text)
