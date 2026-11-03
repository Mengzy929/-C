import unittest
from dataclasses import replace

from qiyan_c.assets import load_fixture
from qiyan_c.events import Ledger, LearningEvent, giveup_events, reduce_events
from qiyan_c.reading import (
    AnswerVerdict, Assessment, DocTree, Paragraph, QuoteSpan, ReadingState, Section,
    advance, assess_demo, build_index, explain, locate, submit, utf16_offsets,
)


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.index, self.questions = load_fixture()

    def test_all_five_questions_have_exact_source(self):
        self.assertEqual([q.stage for q in self.questions], [1, 2, 3, 4, 5])
        for question in self.questions:
            paragraph, start, end = locate(self.index, question.source)
            self.assertEqual(paragraph.text[start:end], question.source.quote)

    def test_nested_tree_and_duplicate_ids(self):
        self.assertIn("observations", self.index.sections)
        doc = DocTree("x", "1", "x", (Section("a", "a", (Paragraph("p", "a"),)),
                                           Section("b", "b", (Paragraph("p", "b"),))))
        with self.assertRaises(ValueError): build_index(doc)
        with self.assertRaises(ValueError): build_index(replace(doc, sections=(Section("a", "x"), Section("a", "y"))))

    def test_bad_location_never_silently_highlights(self):
        span = self.questions[0].source
        for wrong in [replace(span, doc_version="2"), replace(span, doc_id="other"),
                      replace(span, paragraph_id="missing"), replace(span, start=-1),
                      replace(span, start=True), replace(span, quote="fabricated"),
                      replace(span, end=99999), replace(span, end=span.start)]:
            with self.subTest(span=wrong), self.assertRaises(ValueError): locate(self.index, wrong)

    def test_unicode_and_utf16_offsets(self):
        raw = "前😀\n缓存策略，后文"
        index = build_index(DocTree("u", "1", "u", (Section("s", "s", (Paragraph("p", raw),)),)))
        span = QuoteSpan("u", "1", "p", 3, 7, "缓存策略")
        self.assertEqual(utf16_offsets(index, span), (4, 8))
        self.assertEqual(locate(index, span)[0].text[3:7], "缓存策略")

    def test_four_feedback_states(self):
        q = self.questions[0]
        self.assertEqual(assess_demo(q, "不知道", None).verdict, AnswerVerdict.EMPTY)
        self.assertEqual(assess_demo(q, "研究的是吞吐量", "p1").verdict, AnswerVerdict.WRONG)
        self.assertEqual(assess_demo(q, "缓存能影响查询耗时", None).verdict, AnswerVerdict.OFF_TRACK)
        self.assertEqual(assess_demo(q, "缓存能影响查询耗时", "p1").verdict, AnswerVerdict.PASS)
        self.assertEqual(assess_demo(q, "很有道理", "p1").verdict, AnswerVerdict.OFF_TRACK)

    def test_reference_answers_pass_fixture_rubrics(self):
        for q in self.questions:
            self.assertEqual(assess_demo(q, q.reference_answer, q.source.paragraph_id).verdict, AnswerVerdict.PASS)

    def test_no_skipping_or_automatic_pass_after_explanation(self):
        state = ReadingState()
        with self.assertRaises(ValueError): advance(state)
        with self.assertRaises(ValueError): explain(state, confirmed=False)
        after = explain(state, confirmed=True)
        self.assertTrue(after.saw_explanation)
        self.assertFalse(after.passed)
        with self.assertRaises(ValueError): advance(after)
        self.assertFalse(state.saw_explanation)

    def test_retry_count_and_stage_reset(self):
        state = submit(ReadingState(), Assessment(AnswerVerdict.EMPTY, "x"))
        self.assertEqual(state.attempts, 1)
        self.assertEqual(state.stage, 1)
        state = explain(state, confirmed=True)
        state = submit(state, Assessment(AnswerVerdict.PASS, "x"))
        self.assertTrue(state.saw_explanation)
        state = advance(state)
        self.assertEqual(state, ReadingState(stage=2))

    def test_five_stage_end_to_end_state_machine(self):
        state = ReadingState()
        for q in self.questions:
            state = submit(state, assess_demo(q, q.reference_answer, q.source.paragraph_id))
            state = advance(state)
        self.assertTrue(state.completed)
        with self.assertRaises(ValueError): advance(state)
        with self.assertRaises(ValueError): submit(state, Assessment(AnswerVerdict.PASS, "x"))

    def test_invalid_state_is_rejected(self):
        for kwargs in [dict(stage=0), dict(stage=True), dict(attempts=-1), dict(completed=True), dict(passed="true")]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): ReadingState(**kwargs)


class EventTests(unittest.TestCase):
    def test_dedup_is_idempotent_and_does_not_mutate(self):
        event = LearningEvent("e1", "q1", "answer", "2026-11-03T10:00:00+08:00")
        original = Ledger()
        once = reduce_events(original, (event, event))
        twice = reduce_events(once, (event,))
        self.assertEqual(once, twice)
        self.assertEqual(len(twice.events), 1)
        self.assertEqual(original.events, ())

    def test_duplicate_id_with_different_content_rejected(self):
        event = LearningEvent("e1", "q1", "answer", "2026-11-03T10:00:00+08:00")
        with self.assertRaises(ValueError): reduce_events(Ledger((event,)), (replace(event, kind="other"),))

    def test_giveup_three_events_due_in_five_days_not_scheduled(self):
        events = giveup_events("q1", "2026-11-03T10:00:00+08:00")
        self.assertEqual(len(events), 3)
        self.assertEqual(dict(events[0].details)["weight"], "-0.8")
        self.assertEqual(dict(events[2].details)["due_at"], "2026-11-08T10:00:00+08:00")
        self.assertEqual(dict(events[2].details)["scheduled"], "false")

    def test_review_bounds_and_timezone(self):
        for days in (2, 8, True):
            with self.assertRaises(ValueError): giveup_events("q", "2026-11-03T10:00:00+08:00", review_days=days)
        with self.assertRaises(ValueError): giveup_events("q", "2026-11-03T10:00:00")
