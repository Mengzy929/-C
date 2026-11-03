"""Local startup IO only. Core functions consume already-loaded objects."""

import json
from pathlib import Path

from .reading import DocTree, Paragraph, Question, QuoteSpan, Section, build_index, locate
from .teaching import compile_rules

ROOT = Path(__file__).resolve().parent.parent


def load_rules():
    # JSON is a valid YAML 1.2 subset, so no third-party YAML parser is needed.
    path = ROOT / "skills/teaching-engine/rules/hint_matrix.yaml"
    return compile_rules(json.loads(path.read_text(encoding="utf-8")))


def load_fixture():
    data = json.loads((ROOT / "fixtures/reading_demo.json").read_text(encoding="utf-8"))

    def section(raw):
        return Section(raw["id"], raw["title"], tuple(
            Paragraph(p["id"], p["text"], p.get("page")) for p in raw.get("paragraphs", [])
        ), tuple(section(c) for c in raw.get("children", [])))

    raw = data["document"]
    doc = DocTree(raw["id"], raw["version"], raw["title"],
                  tuple(section(s) for s in raw["sections"]), raw["synthetic"])
    index = build_index(doc)
    questions = []
    for q in data["questions"]:
        paragraph = index.paragraphs[q["paragraph_id"]]
        quote = q["quote"]
        start = paragraph.text.find(quote)
        span = QuoteSpan(doc.id, doc.version, paragraph.id, start, start + len(quote), quote)
        locate(index, span)
        if len(q["hints"]) != 3 or q["stage"] != len(questions) + 1:
            raise ValueError("Fixture needs three hints and ordered stages 1..5")
        questions.append(Question(
            q["id"], q["stage"], q["title"], q["question"], span,
            tuple(tuple(g) for g in q["keyword_groups"]), tuple(q["contradictions"]),
            q["reference_answer"], tuple(q["hints"]),
        ))
    if len(questions) != 5:
        raise ValueError("Fixture must cover five reading stages")
    return index, tuple(questions)
