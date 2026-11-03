import copy
import random
import unittest
from dataclasses import replace

from qiyan_c.assets import ROOT, load_rules
from qiyan_c.contracts import Dimension, Intent, Mastery, TeachingRequest
from qiyan_c.prompts import assemble_prompt, for_the_model
from qiyan_c.teaching import compile_rules, decide, hard_ceiling, require_version
import json


class TeachingTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()

    def request(self, **kwargs):
        values = dict(intent=Intent.UNDERSTAND, dimension=Dimension.READING, mastery=Mastery.NOVICE)
        values.update(kwargs)
        return TeachingRequest(**values)

    def test_120_independently_specified_expected_cases(self):
        # Final values hand-specified independently of production base+penalty.
        ordinary = {
            Intent.UNDERSTAND: ((1, 2, 3, 3), (0, 1, 2, 2), (0, 1, 2, 2)),
            Intent.LOCATE: ((1, 2, 3, 3), (0, 1, 2, 2), (0, 1, 2, 2)),
            Intent.EVALUATE: ((1, 2, 3, 3), (1, 2, 3, 3), (0, 1, 2, 2)),
            Intent.REFLECT: ((1, 2, 3, 3), (0, 1, 2, 2), (0, 1, 2, 2)),
            Intent.OFF_TOPIC: ((0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)),
        }
        count = 0
        for intent in Intent:
            for m, mastery in enumerate(Mastery):
                for attempts in range(4):
                    for giveup in (False, True):
                        with self.subTest(intent=intent, mastery=mastery, attempts=attempts, giveup=giveup):
                            req = self.request(intent=intent, mastery=mastery, attempts=attempts, giveup=giveup)
                            expected = 0 if intent is Intent.OFF_TOPIC else 3 if giveup else ordinary[intent][m][attempts]
                            self.assertEqual(decide(req, self.rules).hint_level, expected)
                            count += 1
        self.assertEqual(count, 120)

    def test_10000_random_ceiling_and_first_two_attempts(self):
        rng = random.Random(20261103)
        for _ in range(10000):
            req = self.request(intent=rng.choice(list(Intent)), mastery=rng.choice(list(Mastery)),
                               dimension=rng.choice(list(Dimension)), scaffold=rng.randrange(4),
                               attempts=rng.choice([0, 1, 2, 3, 100, 10**20]), giveup=rng.choice([False, True]))
            directive = decide(req, self.rules)
            self.assertLessEqual(directive.hint_level, hard_ceiling(req))
            self.assertGreaterEqual(directive.hint_level, 0)
            if req.attempts < 2 and not req.giveup:
                self.assertLessEqual(directive.hint_level, 2)

    def test_all_dimensions_and_scaffolds_pass_through(self):
        for dimension in Dimension:
            for scaffold in range(4):
                result = decide(self.request(dimension=dimension, scaffold=scaffold), self.rules)
                self.assertEqual(result.dimension, dimension)
                self.assertEqual(result.scaffold_level, scaffold)

    def test_invalid_request_types_fail_closed(self):
        for kwargs in [dict(attempts=-1), dict(attempts=True), dict(attempts=1.5),
                       dict(giveup="false"), dict(scaffold=4), dict(scaffold=True),
                       dict(intent="understand"), dict(dimension="invalid"), dict(mastery=None)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.request(**kwargs)

    def test_rationale_has_attribution(self):
        result = decide(self.request(attempts=1), self.rules)
        for field in ("matrix=", "ceiling=", "attempts=1", "penalty=", "giveup="):
            self.assertIn(field, result.rationale)

    def test_rules_are_frozen_and_input_copy_isolated(self):
        data = json.loads((ROOT / "skills/teaching-engine/rules/hint_matrix.yaml").read_text(encoding="utf-8"))
        rules = compile_rules(data)
        data["base"]["understand"]["novice"][0] = 3
        self.assertEqual(decide(self.request(), rules).hint_level, 1)
        with self.assertRaises(TypeError):
            rules.matrix[("understand", "novice")] = (3, 3, 3, 3)

    def test_missing_and_invalid_rules_are_rejected(self):
        original = json.loads((ROOT / "skills/teaching-engine/rules/hint_matrix.yaml").read_text(encoding="utf-8"))
        for change in [lambda d: d.pop("version"), lambda d: d["base"].pop("understand"),
                       lambda d: d["penalties"].append(3),
                       lambda d: d["base"]["locate"]["novice"].__setitem__(0, True)]:
            data = copy.deepcopy(original); change(data)
            with self.assertRaises(ValueError):
                compile_rules(data)

    def test_explicit_pinning_does_not_silently_upgrade(self):
        newer = replace(self.rules, version="0.2.0-draft")
        self.assertIs(require_version(self.rules, "0.1.0-draft"), self.rules)
        with self.assertRaises(ValueError):
            require_version(newer, "0.1.0-draft")

    def test_prompts_only_inject_model_section_within_estimated_budget(self):
        root = ROOT / "skills/teaching-engine"
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        requests = [self.request(mastery=Mastery.INDEPENDENT), self.request(),
                    self.request(attempts=1), self.request(giveup=True)]
        for level, request in enumerate(requests):
            directive = decide(request, self.rules)
            self.assertEqual(directive.hint_level, level)
            bundle = assemble_prompt(directive, skill, (root / f"prompts/l{level}.md").read_text(encoding="utf-8"))
            self.assertLessEqual(bundle.token_count, 900)
            self.assertEqual(bundle.measurement, "utf8_byte_estimate")
            self.assertNotIn("For maintainers", bundle.text)
            self.assertNotIn("尚未与 B", bundle.text)

    def test_real_tokenizer_and_budget_failure(self):
        directive = decide(self.request(), self.rules)
        self.assertEqual(assemble_prompt(directive, "## For the model\nx", "hi", count_tokens=lambda _: 25).measurement, "tokenizer")
        with self.assertRaises(ValueError):
            assemble_prompt(directive, "## For the model\nx", "hi", count_tokens=lambda _: 901)
        with self.assertRaises(ValueError):
            for_the_model("wrong document")

    def test_off_topic_costs_zero_teaching_context(self):
        directive = decide(self.request(intent=Intent.OFF_TOPIC), self.rules)
        bundle = assemble_prompt(directive, "deliberately invalid", "")
        self.assertEqual((bundle.text, bundle.token_count), ("", 0))
        self.assertFalse(directive.active)
