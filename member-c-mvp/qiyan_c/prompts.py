"""Pure prompt assembly. Caller supplies texts and optional real tokenizer."""

from collections.abc import Callable

from .contracts import PromptBundle, TeachingDirective


def for_the_model(skill_text: str) -> str:
    marker = "## For the model"
    if marker not in skill_text:
        raise ValueError("Missing For the model section")
    section = skill_text.split(marker, 1)[1]
    return section.split("\n## ", 1)[0].strip()


def assemble_prompt(
    directive: TeachingDirective,
    skill_text: str,
    level_template: str,
    *,
    count_tokens: Callable[[str], int] | None = None,
    budget: int = 900,
) -> PromptBundle:
    if type(budget) is not int or budget <= 0:
        raise ValueError("budget must be a positive integer")
    if not directive.active:
        return PromptBundle("", 0, "skipped")
    text = "\n\n".join((
        for_the_model(skill_text), level_template.strip(),
        "必须追问：" + "；".join(directive.must_ask),
        "禁止：" + ", ".join(directive.forbidden),
    ))
    count = count_tokens(text) if count_tokens else len(text.encode("utf-8"))
    if type(count) is not int or count < 0:
        raise ValueError("Tokenizer must return a nonnegative integer")
    if count > budget:
        raise ValueError(f"Teaching context exceeds budget: {count} > {budget}")
    return PromptBundle(text, count, "tokenizer" if count_tokens else "utf8_byte_estimate")
