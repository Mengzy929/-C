"""Run offline checks and write reproducible local measurements to reports/."""

import json
import platform
import statistics
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qiyan_c.assets import load_rules
from qiyan_c.contracts import Dimension, Intent, Mastery, TeachingRequest
from qiyan_c.guard import detect
from qiyan_c.prompts import assemble_prompt
from qiyan_c.teaching import decide
from tools.capability_check import check_tree


def main():
    tests = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    rules = load_rules()
    req = TeachingRequest(Intent.UNDERSTAND, Dimension.READING, Mastery.NOVICE)
    timings = []
    for _ in range(200): decide(req, rules)
    for _ in range(10000):
        started = time.perf_counter_ns(); decide(req, rules)
        timings.append((time.perf_counter_ns() - started) / 1_000_000)
    skill_root = ROOT / "skills/teaching-engine"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    prompts = {}
    requests = [replace(req, mastery=Mastery.INDEPENDENT), req,
                replace(req, attempts=1), replace(req, giveup=True)]
    for level, request in enumerate(requests):
        directive = decide(request, rules)
        bundle = assemble_prompt(directive, skill, (skill_root / f"prompts/l{level}.md").read_text(encoding="utf-8"))
        prompts[f"level_{level}"] = bundle.token_count
    sys.path.insert(0, str(ROOT / "tests"))
    from test_guard_capabilities import KNOWN, NORMAL, VIOLATIONS
    low_directive = decide(replace(req, mastery=Mastery.INDEPENDENT), rules)
    caught = sum(not detect(t, low_directive, KNOWN).allowed for t in VIOLATIONS)
    false_alarms = sum(not detect(t, low_directive, KNOWN).allowed for t in NORMAL)
    report = {
        "python": platform.python_version(), "platform": platform.platform(),
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "basic_decision_cases": 120, "random_invariant_cases": 10000,
        "capability_violations": check_tree(),
        "guard": {"constructed_violations": len(VIOLATIONS), "caught": caught,
                  "recall": caught / len(VIOLATIONS), "normal_controls": len(NORMAL),
                  "false_alarms": false_alarms,
                  "limitation": "Constructed development fixtures, not held-out semantic accuracy."},
        "decision_latency_ms": {"samples": len(timings), "warmup": 200,
                                "median": statistics.median(timings),
                                "p99": sorted(timings)[9899], "includes_io": False},
        "prompt_utf8_byte_estimates_not_real_model_tokens": prompts,
        "rule_version": rules.version,
    }
    reports = ROOT / "reports"; reports.mkdir(exist_ok=True)
    (reports / "checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if result.wasSuccessful() and not check_tree() else 1


if __name__ == "__main__":
    raise SystemExit(main())
