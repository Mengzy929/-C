"use strict";
const $ = id => document.getElementById(id);
const titles = ["定位问题", "核对证据", "识别边界", "替代解释", "迁移思考"];
const feedbackLabels = {pass: "✓ 满足示例检查项", off_track: "↗ 继续补充依据", empty: "○ 先形成具体回答", wrong: "! 请核对原文"};
let sessionId = null, view = null, busy = false, pendingRequest = null;

function text(tag, value, className) {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  return element;
}

function setBusy(value) {
  busy = value;
  const completed = view?.state.completed;
  for (const id of ["submit", "hint", "explain", "answer", "source"]) $(id).disabled = value || !view || completed;
  $("reset").disabled = value;
  $("next").disabled = value || !view?.state.passed || completed;
  $("submit").textContent = value ? "处理中…" : "提交我的理解 ↗";
  $("answer-form").setAttribute("aria-busy", String(value));
  renderSourceButtons();
}

function showError(message, retryable = false) {
  $("error-text").textContent = message;
  $("error").hidden = false;
  $("retry").hidden = !retryable;
}

async function post(path, data) {
  const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || "本地服务未能完成请求。");
    error.serverResponse = true;
    throw error;
  }
  return result;
}

function render() {
  const sourceId = $("source").value;
  const q = view.question;
  $("notice").textContent = view.notice;
  $("paper-title").textContent = view.document.title;
  $("question-title").textContent = q.title;
  $("question-step").textContent = "YOUR THINKING / 阅读思考";
  $("question-index").textContent = String(q.stage).padStart(2, "0") + " / 05";
  $("question-text").textContent = q.text;
  $("steps").replaceChildren(...titles.map((title, i) => {
    const li = document.createElement("li");
    li.className = i + 1 < q.stage || view.state.completed ? "done" : i + 1 === q.stage ? "current" : "";
    if (i + 1 === q.stage) li.setAttribute("aria-current", "step");
    li.append(text("span", i + 1 < q.stage || view.state.completed ? "✓" : String(i + 1), "step-number"), text("span", title));
    return li;
  }));
  $("source").replaceChildren(new Option("请选择一个段落", ""), ...view.document.paragraphs.map((p, i) => new Option(`段落 ${i + 1} · 第 ${p.page ?? "未知"} 页`, p.id)));
  $("source").value = sourceId;
  $("paragraphs").replaceChildren(...view.document.paragraphs.map((p, i) => {
    const article = document.createElement("article"); article.className = "paragraph";
    const meta = document.createElement("div"); meta.className = "paragraph-meta";
    const button = text("button", "选为依据", "source-button"); button.type = "button";
    button.setAttribute("aria-label", `选择段落 ${i + 1} 作为依据`);
    button.setAttribute("aria-pressed", String(sourceId === p.id));
    button.disabled = busy || view.state.completed;
    button.addEventListener("click", () => {$("source").value = p.id; render(); $("answer").focus();});
    meta.append(text("span", `段落 ${i + 1} / 第 ${p.page ?? "未知"} 页`, "paragraph-label"), button);
    const content = document.createElement("p");
    if (q.source.paragraph_id === p.id) {
      const {start_utf16: start, end_utf16: end} = q.source;
      content.append(document.createTextNode(p.text.slice(0, start)), text("mark", p.text.slice(start, end)), document.createTextNode(p.text.slice(end)));
    } else content.textContent = p.text;
    article.append(meta, content); return article;
  }));
  $("hint-card").hidden = !view.hint;
  $("hint-text").textContent = view.hint;
  $("explanation-card").hidden = !view.explanation;
  $("explanation-text").textContent = view.explanation;
  $("feedback").hidden = !view.feedback;
  if (view.feedback) {
    $("feedback").className = "feedback " + view.feedback.verdict;
    $("feedback-title").textContent = feedbackLabels[view.feedback.verdict] ?? "示例反馈";
    $("feedback-text").textContent = view.feedback.text + (view.feedback.after_explanation ? " 本次为看过解释后的重答，不计作独立完成。" : "");
  }
  $("next").textContent = q.stage === 5 ? "完成这次练习 ✓" : "继续下一步 →";
  $("complete").hidden = !view.state.completed;
  $("history-empty").hidden = view.history.length > 0;
  $("history").replaceChildren(...view.history.map((record, i) => {
    const card = document.createElement("article"); card.className = "history-entry";
    card.append(text("h3", `第 ${i + 1} 次作答 · ${titles[record.stage - 1]}${record.after_explanation ? " · 解释后重答" : ""}`), text("p", record.answer || "（未填写）"), text("p", record.feedback, "history-feedback"));
    return card;
  }));
  $("event-count").textContent = `${view.events.length} 条本次事件`;
  $("events").replaceChildren(...view.events.map(event => text("li", `${event.label}${event.details.due_at ? " · 复习意向日期 " + event.details.due_at.slice(0, 10) : ""}`)));
  $("export").disabled = false;
  setBusy(busy);
}

async function start() {
  if (busy) return;
  setBusy(true); $("error").hidden = true;
  try {
    const result = await post("/api/session", {});
    sessionId = result.session_id; view = result.view; pendingRequest = null;
    $("answer").value = ""; $("source").value = ""; render();
  } catch (error) {showError("无法载入练习。请确认本地 Python 服务仍在运行，再点击“新练习”。");}
  finally {setBusy(false);}
}

async function act(action, payload = {}, retry = false) {
  if (busy || !view) return;
  setBusy(true); $("error").hidden = true;
  if (!retry) pendingRequest = {session_id: sessionId, action, action_id: crypto.randomUUID(), payload: {question_id: view.question.id, ...payload}};
  try {
    const result = await post("/api/action", pendingRequest);
    view = result.view; pendingRequest = null;
    if (action === "next") {$("answer").value = ""; $("source").value = "";}
    render();
    if (view.state.completed) $("complete").focus();
  } catch (error) {
    if (error.serverResponse) {pendingRequest = null; showError("请求未完成：" + error.message);}
    else showError("与本地服务的连接中断。可重试同一请求，避免重复记录。", true);
  } finally {setBusy(false); renderSourceButtons();}
}

function renderSourceButtons() {
  for (const button of document.querySelectorAll(".source-button")) button.disabled = busy || !view || view.state.completed;
}

$("answer-form").addEventListener("submit", event => {event.preventDefault(); act("answer", {answer: $("answer").value, paragraph_id: $("source").value || null});});
$("hint").addEventListener("click", () => act("hint"));
$("next").addEventListener("click", () => act("next"));
$("source").addEventListener("change", render);
$("explain").addEventListener("click", () => $("explain-dialog").showModal());
$("cancel-explain").addEventListener("click", () => $("explain-dialog").close());
$("confirm-explain").addEventListener("click", () => {$("explain-dialog").close(); act("explain", {confirmed: true});});
$("retry").addEventListener("click", () => {if (pendingRequest) act(pendingRequest.action, {}, true);});
$("reset").addEventListener("click", start);
$("export").addEventListener("click", () => {
  if (!view) return;
  const blob = new Blob([JSON.stringify({scope: "offline_synthetic_demo", ...view}, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = "qiyan-c-demo-record.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
setBusy(false); start();
