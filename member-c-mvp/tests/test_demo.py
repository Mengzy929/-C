import json
import threading
import unittest
from http.client import HTTPConnection

from qiyan_c.demo import DemoSession, QUESTIONS, make_server

NOW = "2026-11-03T12:00:00+08:00"


class DemoSessionTests(unittest.TestCase):
    def setUp(self):
        self.session = DemoSession()

    def action(self, action, request_id="r1", **kwargs):
        return self.session.apply(action, request_id, {"question_id": QUESTIONS[self.session.state.stage - 1].id, **kwargs}, now=NOW)

    def test_public_view_does_not_leak_reference_answer(self):
        view = self.session.snapshot()
        serialized = json.dumps(view, ensure_ascii=False)
        self.assertNotIn(QUESTIONS[0].reference_answer, serialized)
        self.assertNotIn("hint_level", serialized)
        self.assertEqual(view["explanation"], "")

    def test_duplicate_answer_does_not_increment_failures_or_events(self):
        first = self.action("answer", answer="不知道", paragraph_id=None)
        second = self.action("answer", answer="不知道", paragraph_id=None)
        self.assertEqual(first, second)
        self.assertEqual(self.session.state.attempts, 1)
        self.assertEqual(len(self.session.ledger.events), 1)

    def test_conflicting_request_id_fails_without_mutation(self):
        self.action("answer", answer="不知道", paragraph_id=None)
        before = self.session.snapshot()
        with self.assertRaises(ValueError): self.action("answer", answer="different", paragraph_id=None)
        self.assertEqual(before, self.session.snapshot())

    def test_explanation_requires_confirmation_and_reanswer(self):
        with self.assertRaises(ValueError): self.action("explain", confirmed=False)
        self.assertEqual(len(self.session.ledger.events), 0)
        view = self.action("explain", confirmed=True)
        self.assertTrue(view["explanation"])
        self.assertFalse(view["state"]["passed"])
        self.assertEqual(len(view["events"]), 3)
        with self.assertRaises(ValueError): self.action("next", request_id="next")
        self.action("explain", request_id="explain-again", confirmed=True)
        self.assertEqual(len(self.session.ledger.events), 3)
        view = self.action("answer", request_id="answer", answer=QUESTIONS[0].reference_answer, paragraph_id="p1")
        self.assertTrue(view["feedback"]["after_explanation"])
        self.assertTrue(view["state"]["passed"])

    def test_five_stage_local_integration_and_retry_after_advance(self):
        first_response = None
        for question in QUESTIONS:
            payload = {"question_id": question.id, "answer": question.reference_answer,
                       "paragraph_id": question.source.paragraph_id}
            answer_id = f"answer-{question.stage}"
            result = self.session.apply("answer", answer_id, payload, now=NOW)
            self.assertTrue(result["state"]["passed"])
            if question.stage == 1: first_response = result
            self.action("next", request_id=f"next-{question.stage}")
        self.assertTrue(self.session.state.completed)
        retry = self.session.apply("answer", "answer-1", {
            "question_id": QUESTIONS[0].id, "answer": QUESTIONS[0].reference_answer,
            "paragraph_id": QUESTIONS[0].source.paragraph_id,
        }, now="2026-11-04T12:00:00+08:00")
        self.assertEqual(retry, first_response)
        self.assertEqual(len(self.session.history), 5)

    def test_invalid_and_stale_actions_are_atomic(self):
        before = self.session.snapshot()
        for action, payload in [
            ("unknown", {"question_id": "demo-q1"}),
            ("answer", {"question_id": "demo-q2", "answer": "x"}),
            ("answer", {"question_id": "demo-q1", "answer": "x" * 4001}),
            ("answer", {"question_id": "demo-q1", "answer": "x", "paragraph_id": "missing"}),
        ]:
            with self.assertRaises(ValueError): self.session.apply(action, "bad", payload, now=NOW)
            self.assertEqual(self.session.snapshot(), before)

    def test_sessions_are_isolated_and_rules_are_pinned(self):
        another = DemoSession()
        self.action("hint")
        self.assertEqual(len(another.ledger.events), 0)
        self.assertEqual(self.session.pinned_rules.version, "0.1.0-draft")


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        status, result = response.status, response.read()
        connection.close()
        return status, result

    def post(self, path, data):
        status, raw = self.request("POST", path, json.dumps(data), {"Content-Type": "application/json"})
        return status, json.loads(raw)

    def test_http_create_answer_and_retry(self):
        status, created = self.post("/api/session", {})
        self.assertEqual(status, 200)
        data = {"session_id": created["session_id"], "action": "answer", "action_id": "h1",
                "payload": {"question_id": "demo-q1", "answer": "缓存影响查询耗时", "paragraph_id": "p1"}}
        status, first = self.post("/api/action", data)
        self.assertEqual(status, 200)
        self.assertTrue(first["view"]["state"]["passed"])
        self.assertEqual(self.post("/api/action", data)[1], first)

    def test_http_assets_and_unknown_paths(self):
        for path in ("/", "/app.js", "/style.css"):
            self.assertEqual(self.request("GET", path)[0], 200)
        self.assertEqual(self.request("GET", "/../fixtures/reading_demo.json")[0], 404)

    def test_malformed_json_and_wrong_origin(self):
        self.assertEqual(self.request("POST", "/api/session", "{")[0], 400)
        self.assertEqual(self.request("POST", "/api/session", "[]")[0], 400)
        self.assertEqual(self.request("POST", "/api/session", "{}", {"Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.post("/api/action", {"session_id": "unknown"})[0], 404)
