"""Loopback-only demonstration adapter. NOT the team's Session Gateway.

    python -m qiyan_c.demo --port 8765
    python -m qiyan_c.demo --check
"""

import argparse
import hashlib
import json
import secrets
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .assets import ROOT, load_fixture, load_rules
from .contracts import Dimension, Intent, Mastery, TeachingRequest
from .events import LearningEvent, Ledger, giveup_events, reduce_events
from .guard import detect
from .reading import ReadingState, advance, assess_demo, explain, submit, utf16_offsets
from .teaching import decide

RULES = load_rules()
INDEX, QUESTIONS = load_fixture()

EVENT_LABELS = {
    "answer_submitted": "提交回答", "hint_used": "查看提示",
    "explicit_giveup": "确认查看解释（负向事件意向）",
    "scaffold_failure": "记录一次需要支持的事件",
    "review_requested": "复习意向，尚未调度", "stage_advanced": "继续阅读",
}


class DemoSession:
    """Volatile local driver; core functions above remain stateless and pure."""

    def __init__(self):
        self.state = ReadingState()
        self.ledger = Ledger()
        self.feedback = None
        self.hint = ""
        self.explanation = ""
        self.history = []
        self.processed = {}
        self.pinned_rules = RULES

    def snapshot(self):
        question = QUESTIONS[self.state.stage - 1]
        start, end = utf16_offsets(INDEX, question.source)
        return {
            "notice": "离线合成样文 · 关键词规则判答 · 不核验引用 · 数据仅保存在本次服务进程",
            "document": {
                "title": INDEX.doc.title,
                "paragraphs": [asdict(p) for p in INDEX.paragraphs.values()],
            },
            "question": {
                "id": question.id, "stage": question.stage, "total": 5,
                "title": question.title, "text": question.text,
                "source": {"paragraph_id": question.source.paragraph_id,
                           "start_utf16": start, "end_utf16": end},
            },
            "state": asdict(self.state), "feedback": self.feedback,
            "hint": self.hint, "explanation": self.explanation,
            "history": list(self.history),
            "events": [{"id": e.id, "label": EVENT_LABELS[e.kind], "at": e.occurred_at,
                        "details": dict(e.details)} for e in self.ledger.events],
        }

    def apply(self, action: str, action_id: str, payload: dict, *, now: str):
        if not isinstance(action_id, str) or not 1 <= len(action_id) <= 128:
            raise ValueError("action_id must be a nonempty stable request ID")
        fingerprint = hashlib.sha256(json.dumps(
            [action, payload], ensure_ascii=False, sort_keys=True
        ).encode("utf-8")).hexdigest()
        if action_id in self.processed:
            old_fingerprint, result = self.processed[action_id]
            if fingerprint != old_fingerprint:
                raise ValueError("Request ID was reused with different content")
            return result
        question = QUESTIONS[self.state.stage - 1]
        if payload.get("question_id") != question.id:
            raise ValueError("Question changed; refresh before submitting")
        if self.state.completed:
            raise ValueError("Reading is complete; start a new demonstration")
        state, ledger = self.state, self.ledger
        feedback, hint, explanation = self.feedback, self.hint, self.explanation
        history = list(self.history)
        events = []
        if action == "answer":
            answer = payload.get("answer")
            source = payload.get("paragraph_id")
            if not isinstance(answer, str) or len(answer) > 4000:
                raise ValueError("Answer must be a string of at most 4000 characters")
            if source is not None and source not in INDEX.paragraphs:
                raise ValueError("Selected paragraph does not exist")
            assessment = assess_demo(question, answer, source)
            state = submit(state, assessment)
            feedback = {"verdict": assessment.verdict.value, "text": assessment.feedback,
                        "after_explanation": state.saw_explanation}
            history.append({"question_id": question.id, "stage": question.stage,
                            "answer": answer, "source": source,
                            "feedback": assessment.feedback,
                            "after_explanation": state.saw_explanation})
            events.append(LearningEvent(action_id, question.id, "answer_submitted", now,
                                        (("verdict", assessment.verdict.value),)))
        elif action == "hint":
            directive = decide(TeachingRequest(
                Intent.UNDERSTAND, Dimension.READING, Mastery.GUIDED, attempts=state.attempts
            ), self.pinned_rules)
            # This demo learner uses guided mastery, whose normal maximum is 2.
            # Never expose a level-3 explanation through the generic hint action.
            candidate = question.hints[min(directive.hint_level, 2)]
            guarded = detect(candidate, directive, (question.reference_answer,))
            hint = guarded.safe_text
            events.append(LearningEvent(action_id, question.id, "hint_used", now))
        elif action == "explain":
            state = explain(state, confirmed=payload.get("confirmed"))
            directive = decide(TeachingRequest(
                Intent.UNDERSTAND, Dimension.READING, Mastery.GUIDED,
                attempts=state.attempts, giveup=True,
            ), self.pinned_rules)
            guarded = detect(question.reference_answer, directive)
            explanation = guarded.safe_text
            feedback = None
            if not self.state.saw_explanation:
                events.extend(giveup_events(question.id, now))
        elif action == "next":
            state = advance(state)
            events.append(LearningEvent(action_id, question.id, "stage_advanced", now))
            feedback, hint, explanation = None, "", ""
        else:
            raise ValueError("Unknown demo action")
        ledger = reduce_events(ledger, tuple(events))
        self.state, self.ledger = state, ledger
        self.feedback, self.hint, self.explanation = feedback, hint, explanation
        self.history = history
        result = self.snapshot()
        self.processed[action_id] = (fingerprint, result)
        return result


def make_server(port: int = 8765):
    sessions = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Do not print students' text, query strings or request bodies.
            pass

        def send(self, status, data, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            paths = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                     "/style.css": ("style.css", "text/css")}
            asset = paths.get(urlsplit(self.path).path)
            if asset is None:
                self.send(404, {"error": "Not found"})
                return
            self.send(200, (ROOT / "web" / asset[0]).read_bytes(), asset[1] + "; charset=utf-8")

        def do_POST(self):
            # Browser requests must originate from this local page. No CORS.
            origin = self.headers.get("Origin")
            expected = f"http://{self.headers.get('Host', '')}"
            if origin and origin != expected:
                self.send(403, {"error": "Origin is not allowed"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32768:
                    raise ValueError("Request body must be 1..32768 bytes")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Request must be an object")
                with lock:
                    if self.path == "/api/session":
                        if len(sessions) >= 64:
                            self.send(503, {"error": "演示会话已满，请重启本地服务。"})
                            return
                        session_id = secrets.token_urlsafe(24)
                        sessions[session_id] = DemoSession()
                        self.send(200, {"session_id": session_id,
                                        "view": sessions[session_id].snapshot()})
                    elif self.path == "/api/action":
                        session = sessions.get(data.get("session_id"))
                        if session is None:
                            self.send(404, {"error": "本次演示已失效，请重新开始。"})
                            return
                        payload = data.get("payload")
                        if not isinstance(payload, dict):
                            raise ValueError("payload must be an object")
                        result = session.apply(data.get("action"), data.get("action_id"), payload,
                                               now=datetime.now(timezone.utc).isoformat())
                        self.send(200, {"view": result})
                    else:
                        self.send(404, {"error": "Not found"})
            except (ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
                self.send(400, {"error": str(error)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Member C offline demonstration")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true", help="Check assets and print a decision")
    args = parser.parse_args()
    if args.check:
        directive = decide(TeachingRequest(Intent.UNDERSTAND, Dimension.READING, Mastery.NOVICE), RULES)
        print(json.dumps({"rules": RULES.version, "questions": len(QUESTIONS),
                          "directive": asdict(directive)}, ensure_ascii=False, indent=2))
        return
    server = make_server(args.port)
    print(f"Member C demo: http://127.0.0.1:{server.server_port}", flush=True)
    print("Synthetic fixture; memory only. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
