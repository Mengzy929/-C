import unittest

from qiyan_c.assets import ROOT, load_rules
from qiyan_c.contracts import Dimension, Intent, Mastery, TeachingRequest
from qiyan_c.guard import SAFE_FALLBACK, detect
from qiyan_c.teaching import decide
from tools.capability_check import check_tree, violations

KNOWN = ("缓存策略减少平均查询耗时",)
VIOLATIONS = [
    "答案是缓存有效。", "正确答案：使用缓存。", "标准答案为使用缓存。",
    "结论就是应该使用缓存。", "答案如下：应当缓存。", "直接告诉你：缓存更好。",
    "The answer is caching.", "Correct answer: caching.", "The correct answer is caching.",
    "ANSWER: caching.", "缓存策略减少平均查询耗时。", "缓存策略，减少平均查询耗时！",
    "缓存策略\n减少平均查询耗时。", "```python\nprint('answer')\n```",
    "```javascript\nconsole.log('answer')\n```", "def solution(): return 1",
    "import subprocess", "以下是可直接提交的论文：…", "直接复制这段提交。",
    "1. 列出全部做法\n2. 接着给出完整步骤",
]
NORMAL = [
    "请指出原文中的位置。", "先比较两种流程。", "你能定位描述请求序列的句子吗？",
    "这段证据涉及哪些条件？", "请核对测量指标。", "请补充支持判断的依据。",
    "是否遗漏了资源成本？", "还有其他可能的解释吗？", "请考虑新场景的输入条件。",
    "可以先缩小到一段原文。", "先说说你已经理解的部分。", "请选择一个段落作为依据。",
    "请再次核对比较对象。", "你将如何控制测量顺序？", "需要补充哪些观测？",
    "结论是否得到支持？", "答案是什么，需要由你依据原文判断。", "请用自己的话重答。",
    "哪个条件发生了变化？", "请指出推理中缺失的一步。",
]


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.directive = decide(TeachingRequest(Intent.UNDERSTAND, Dimension.READING, Mastery.INDEPENDENT), load_rules())

    def test_20_constructed_violations_and_20_controls(self):
        caught = sum(not detect(t, self.directive, KNOWN).allowed for t in VIOLATIONS)
        false_alarms = sum(not detect(t, self.directive, KNOWN).allowed for t in NORMAL)
        self.assertEqual(len(VIOLATIONS), 20)
        self.assertGreaterEqual(caught / len(VIOLATIONS), .90)
        self.assertEqual(false_alarms, 0)

    def test_one_rewrite_then_suppress_no_unsafe_text(self):
        first = detect("答案是直接复制。", self.directive)
        second = detect("答案是直接复制。", self.directive, rewrites_used=1)
        self.assertEqual(first.action, "rewrite")
        self.assertEqual(second.action, "suppress")
        self.assertEqual(second.safe_text, SAFE_FALLBACK)
        self.assertNotIn("直接复制", second.safe_text)
        with self.assertRaises(ValueError): detect("x", self.directive, rewrites_used=2)

    def test_l3_can_explain_but_cannot_generate_code_or_ghostwrite(self):
        directive = decide(TeachingRequest(Intent.UNDERSTAND, Dimension.READING, Mastery.NOVICE, giveup=True), load_rules())
        self.assertTrue(detect("答案是缓存有效。", directive).allowed)
        self.assertFalse(detect("```python\nprint(1)\n```", directive).allowed)
        self.assertFalse(detect("以下是可直接提交的论文：…", directive).allowed)

    def test_blank_suppressed_and_safe_output_preserved(self):
        self.assertEqual(detect("  ", self.directive).action, "suppress")
        self.assertEqual(detect("请先定位原文。", self.directive).safe_text, "请先定位原文。")

    def test_known_limit_paraphrases_are_not_semantically_verified(self):
        # Explicitly records a limitation; does not pretend keyword scanning is NLI.
        self.assertTrue(detect("加上一层保存机制后，访问延迟下降了。", self.directive, KNOWN).allowed)


class CapabilityTests(unittest.TestCase):
    def test_pure_core_has_no_forbidden_capabilities(self):
        self.assertEqual(check_tree(), {})

    def test_scanner_rejects_alias_dynamic_import_and_store_writes(self):
        for source in ["import requests as r", "from urllib import request", "import openai",
                       "store.put('x', 'y')", "open('x', 'w')", "__import__('socket')",
                       "file.write('secret')", "datetime.now()"]:
            with self.subTest(source=source): self.assertTrue(violations(source))

    def test_browser_source_has_no_dynamic_html_or_internal_levels(self):
        script = (ROOT / "web/app.js").read_text(encoding="utf-8")
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", script)
        for value in ("L0", "L1", "L2", "L3", "forbidden", "scaffold_level"):
            self.assertNotIn(value, script + html)
        self.assertIn('role="alert"', html)
        self.assertIn('aria-live="polite"', html)
