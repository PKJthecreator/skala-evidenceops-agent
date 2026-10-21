"""v2 Supervisor — 실제 langgraph.StateGraph (Wave 4·5·6·7·8·10b·15 통합).

route → (chat 직행 | incident 파이프라인)
incident: plan(확정 대상 + MCP Prompt) → gate → research(대상별 격리·재시도)
          → replan_check(런북 검색) → analysis(needs_analysis=True일 때만
          실제 실행) → write → validate(반려 시 재작성) → finalize

모든 노드는 SupervisorDeps를 functools.partial로 주입받는 순수 함수다(Wave 13).
각 노드는 @traceable로 LangSmith에 계층 트리로 기록된다.
"""
import asyncio
import re
import time
from functools import partial
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langsmith import traceable

from .deps import SupervisorDeps
from .retry import with_retry
from .intent import SERVICE_ID, SYMPTOM, classify, name_reply, targets_for
from .evidence import checked_status, render_answer, safe_notes


async def _sync_call(fn, *args):
    return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=120)


class AgentState(TypedDict, total=False):
    query: str
    thread_id: str
    history: list[dict]
    route: str
    needs_analysis: bool
    tasks: list[dict]
    gate_removed: int
    collected: list[dict]
    replan_rounds: int
    retry_count: int
    parallel_elapsed: float
    draft: str
    validation_attempts: int
    validation_feedback: str
    final: str
    last_prompt: str
    cost_usd: float
    events: list[dict]
    intent: str
    targets: list[str]
    validated_notes: str


def _cost(state: AgentState, usage: dict) -> float:
    return round(state.get("cost_usd", 0.0) + usage["usd"], 6)


@traceable(name="route_node")
async def route_node(state: AgentState, deps: SupervisorDeps) -> dict:
    query = state["query"]
    thread = state["thread_id"]
    if re.fullmatch(r"취소(?:해\s*줘|해\s*주세요)?[.!?]?", query.strip()):
        deps.session_store.set_pending(thread, None)
        return {"route": "clarify", "intent": "clarify", "targets": [], "final": "보류한 요청을 취소했습니다.", "events": []}
    remembered = name_reply(query, state.get("history", []))
    if remembered:
        deps.session_store.set_pending(thread, None)
        return {"route": "chat", "intent": "chat", "targets": [], "final": remembered,
                "events": state.get("events", []) + [{"type": "RouteDecided", "route": "chat", "targets": []},
                                                      {"type": "Finalize", "pipeline": "name-recall"}]}
    pending = deps.session_store.get_pending(thread)
    if pending and targets_for(query)[0] and not SYMPTOM.search(query):
        query = pending + "\n확인 대상: " + query
    try:
        result, usage = await _sync_call(deps.fast_llm.route, query)
    except Exception:
        result, usage = {"route": "chat", "needs_analysis": False}, {"usd": 0.0}
    intent, targets, reply = classify(query, result["route"])
    deps.session_store.set_pending(thread, SERVICE_ID.sub("", query) if intent == "clarify" else None)
    event = {"type": "RouteDecided", "route": intent, "targets": targets}
    return {"query": query, "route": "chat" if intent == "chat" else "incident", "intent": intent,
            "targets": targets, "final": reply, "needs_analysis": result["needs_analysis"],
            "cost_usd": _cost(state, usage),
            "events": state.get("events", []) + [event]}


@traceable(name="chat_answer_node")
async def chat_answer_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """히스토리 기반 대화. 초안 토큰 없이 최종 답변만 반환한다."""
    try:
        reply, usage = await asyncio.wait_for(deps.fast_llm.chat(
            state["query"], state.get("history", [])), timeout=120)
    except Exception:
        reply, usage = "대화 응답을 생성하지 못했습니다. 잠시 후 다시 요청해 주세요.", {"usd": 0.0}
    return {"final": reply, "last_prompt": usage.get("prompt"),
            "cost_usd": _cost(state, usage),
            "events": state["events"] + [{"type": "Finalize", "pipeline": "chat-direct"}]}


@traceable(name="plan_node")
async def plan_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 4 — Plan/Task 분해. Wave 2의 MCP Prompt가 표준 절차를 깔아준다.

    resource와 마찬가지로 이름을 어느 서버가 들고 있는지 미리 가정하지 않고,
    find_prompt()로 연결된 서버들을 먼저 조회해 찾은 뒤에만 get_prompt를 보낸다."""
    targets = state["targets"]
    usage, result = {"usd": 0.0}, {"needs_analysis": False, "tasks": []}
    if state["intent"] != "runbook":
        try:
            prompt_server = await asyncio.wait_for(deps.mcp.find_prompt("incident_analysis_prompt"), 5)
            procedure = await asyncio.wait_for(deps.mcp.get_prompt(
                "incident_analysis_prompt", {"system_name": targets[0], "symptom": state["query"]}, server=prompt_server), 5)
            result, usage = await _sync_call(deps.fast_llm.plan, state["query"] + "\n대상: " + ", ".join(targets), procedure)
        except Exception:
            pass  # 계획 LLM/Prompt 실패 시에도 코드로 확정한 대상은 조사한다.
    tasks = [{"id": f"task-{i}", "agent": "research", "kind": "monitoring", "target": target, "status": "pending"}
             for i, target in enumerate(targets) if state["intent"] != "runbook"]
    if result.get("needs_analysis") and any(t.get("agent") == "analysis" for t in result.get("tasks", [])):
        tasks.append({"id": "task-analysis", "agent": "analysis", "kind": "pattern-analysis", "status": "pending"})
    event = {"type": "PlanCreated", "task_count": 1 if state["intent"] == "runbook" else len(tasks),
             "targets": targets}
    return {"tasks": tasks, "needs_analysis": result["needs_analysis"],
            "cost_usd": _cost(state, usage), "events": state["events"] + [event]}


@traceable(name="gate_node")
async def gate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 — 권위 게이트. needs_analysis=False인데 섞여 들어온 analysis task를
    프롬프트가 아니라 코드로 강제 제거한다."""
    tasks = state["tasks"]
    if not state.get("needs_analysis", False):
        kept = [t for t in tasks if t["agent"] != "analysis"]
        removed = len(tasks) - len(kept)
    else:
        kept, removed = tasks, 0
    event = {"type": "GateApplied", "removed_analysis_tasks": removed}
    return {"tasks": kept, "gate_removed": removed,
            "events": state["events"] + [event]}


@traceable(name="research_node")
async def research_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 15 가드 + Wave 10b 병렬 + Wave 9 재시도 + Wave 2 Tool/Resource 실호출."""
    tasks = state["tasks"]
    research_indices = [i for i, t in enumerate(tasks)
                        if t["agent"] == "research" and t["status"] == "pending"]
    # Wave 15 — 객체가 아니라 '실행할 목록'을 검사한다 (not research_agent 버그의 수정판)
    if not research_indices:
        return {"events": state["events"] +
                [{"type": "ResearchSkipped", "reason": "pending research task 0개"}]}

    retry_total = state.get("retry_count", 0)

    async def run_one(idx: int) -> dict:
        task = tasks[idx]
        attempts = 0
        async def fetch():
            nonlocal attempts
            attempts += 1
            return await asyncio.wait_for(deps.mcp.call_tool("get_monitoring_status", {"system_name": task["target"]}), 5)
        try:
            data, retries = await with_retry(fetch)
            data = checked_status(data, task["target"])
            return {"idx": idx, "source": "monitoring", "data": data, "retries": retries}
        except Exception as exc:
            return {"idx": idx, "source": "missing", "data": "모니터링 미확보 (" + type(exc).__name__ + ")", "retries": max(0, attempts - 1)}

    started = time.perf_counter()
    results = await asyncio.gather(*(run_one(i) for i in research_indices))
    elapsed = round(time.perf_counter() - started, 2)

    new_tasks = [dict(t) for t in tasks]
    collected = list(state.get("collected", []))
    events = list(state["events"])
    for r in results:
        new_tasks[r["idx"]]["status"] = "failed" if r["source"] == "missing" else "done"
        collected.append({"source": r["source"], "data": r["data"], "target": new_tasks[r["idx"]]["target"], "evidence_id": f"E{len(collected) + 1}"})
        retry_total += r["retries"]
        events.append({"type": "TaskCompleted", "id": new_tasks[r["idx"]]["id"],
                       "source": r["source"], "target": new_tasks[r["idx"]]["target"],
                       "retries": r["retries"]})
    return {"tasks": new_tasks, "collected": collected, "retry_count": retry_total,
            "parallel_elapsed": elapsed, "events": events}


@traceable(name="replan_check_node")
async def replan_check_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """고정 유형 기본값 대신 실제 증상·알림으로 런북을 검색한다."""
    collected = list(state.get("collected", []))
    events = list(state["events"])
    queries = []
    for observation in [c for c in collected if c["source"] == "monitoring" and not c["data"]["stale"]]:
        target, alerts = observation["target"], observation["data"]["alerts"]
        if len(state["targets"]) > 1:
            if not alerts:
                collected.append({"source": "missing", "target": target, "data": "알림이 없어 대표 런북을 선택하지 않음"})
                continue
            # ponytail: 첫 알림을 대표로 사용; 알림 우선순위·개별 증상 분리는 복합 장애 지원 시 추가.
            query = target + "\n모니터링 알림에 대한 장애 대응 절차: " + alerts[0]
        else:
            query = state["query"] + "\n" + " ".join(alerts)
        queries.append((target, query))
    if state["intent"] == "runbook":
        queries = [("일반 절차", state["query"])]
    for target, query in queries:
        try:
            documents = await asyncio.wait_for(deps.retriever.search(query), 65)
            for doc in documents:
                # RAG는 incident_type만 고르고, 본문은 기존 MCP Resource로 읽는다 (Wave 2).
                server, template = await asyncio.wait_for(deps.mcp.find_resource_template("get_incident_runbook"), 5)
                text = await asyncio.wait_for(deps.mcp.read_resource(template.format(incident_type=doc["doc_id"]), server=server), 5)
                collected.append({"source": "runbook", "data": text, "doc_id": doc["doc_id"],
                                  "target": target, "evidence_id": f"E{len(collected) + 1}"})
            events.append({"type": "RetrievalCompleted", "target": target, "doc_ids": [d["doc_id"] for d in documents]})
            if not documents:
                collected.append({"source": "missing", "target": target, "data": "일치하는 런북 근거 없음"})
        except Exception as exc:
            collected.append({"source": "missing", "target": target, "data": "런북 검색 미확보 (" + type(exc).__name__ + ")"})
    events.append({"type": "ReplanCheck", "round": 0, "is_sufficient": True})
    return {"collected": collected, "events": events}


@traceable(name="analysis_node")
async def analysis_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 보완 — needs_analysis=True가 정당한 경우(모델의 자기모순이 아니라
    실제로 패턴 비교가 필요하다고 판단한 경우)를 위한 실행 경로. gate가 살려둔
    agent=='analysis' task가 있을 때만 수집된 monitoring 결과들을 비교 분석한다."""
    tasks = state["tasks"]
    pending = [t for t in tasks if t["agent"] == "analysis" and t["status"] == "pending"]
    if not pending:
        return {"events": state["events"] +
                [{"type": "AnalysisSkipped", "reason": "analysis task 0개"}]}
    monitoring = [c for c in state.get("collected", []) if c["source"] == "monitoring" and not c["data"]["stale"]]
    if len(monitoring) < 2:
        return {"events": state["events"] + [{"type": "AnalysisSkipped", "reason": "비교할 최신 관측 부족"}]}
    try:
        summary, usage = await _sync_call(deps.fast_llm.analyze, monitoring)
    except Exception:
        return {"events": state["events"] + [{"type": "AnalysisSkipped", "reason": "분석 응답 미확보"}]}
    new_tasks = [dict(t) for t in tasks]
    for t in new_tasks:
        if t["agent"] == "analysis" and t["status"] == "pending":
            t["status"] = "done"
    collected = state.get("collected", []) + [{"source": "analysis", "data": summary}]
    event = {"type": "AnalysisCompleted", "length": len(summary)}
    return {"tasks": new_tasks, "collected": collected,
            "cost_usd": _cost(state, usage), "events": state["events"] + [event]}


@traceable(name="write_node")
async def write_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """초안은 내부에만 보관한다. 생성 실패해도 관측 사실을 지우지 않는다."""
    attempt = state.get("validation_attempts", 0) + 1
    collected = [c for c in state.get("collected", []) if c["source"] in {"runbook", "analysis"}
                 or c["source"] == "monitoring" and not c["data"]["stale"]]
    draft, usage = "", {"usd": 0.0}
    if any(c["source"] == "runbook" for c in collected):
        try:
            draft, usage = await asyncio.wait_for(deps.quality_llm.write(
                state["query"], collected, attempt, state.get("validation_feedback")), timeout=120)
        except Exception:
            pass  # 생성 실패 시에도 확인된 관측·런북은 반환한다.
    return {"draft": draft, "last_prompt": usage.get("prompt"),
            "cost_usd": _cost(state, usage),
            "events": state["events"] + [{"type": "DraftWritten", "attempt": attempt,
                                          "length": len(draft)}]}


@traceable(name="validate_node")
async def validate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """생성 수치·상태 단정은 제거하고, 재작성은 한 번만 허용한다."""
    attempts = state.get("validation_attempts", 0) + 1
    notes, rejected = safe_notes(state["draft"], state["targets"])
    feedback = "관측 수치·상태·원인을 단정하지 말고, 숫자 없이 원인 후보와 확인 절차만 설명하세요." if rejected and attempts < 2 else None
    verdict = "불합격" if feedback else "제한 응답" if rejected else "합격"
    event = {"type": "Validation", "attempt": attempts, "verdict": verdict}
    return {"validation_attempts": attempts, "validation_feedback": feedback, "validated_notes": notes,
            "events": state["events"] + [event]}


@traceable(name="finalize_node")
async def finalize_node(state: AgentState, deps: SupervisorDeps) -> dict:
    return {"final": render_answer(state.get("collected", []), state.get("validated_notes", ""), state["intent"]),
            "events": state["events"] + [{"type": "Finalize", "pipeline": "incident-v2"}]}


def _after_route(state: AgentState) -> str:
    if state.get("final"):
        return "done"
    return "chat_answer" if state["route"] == "chat" else "plan"


def _after_replan_check(state: AgentState) -> str:
    if state["intent"] == "runbook":
        return "finalize"
    last = state["events"][-1]
    return "analysis" if last.get("is_sufficient") else "research"


def _after_validate(state: AgentState) -> str:
    return "finalize" if state.get("validation_feedback") is None else "write"


def build_graph(deps: SupervisorDeps):
    g = StateGraph(AgentState)
    node = lambda fn: partial(fn, deps=deps)   # Wave 13 — 명시적 의존성 주입
    g.add_node("route", node(route_node))
    g.add_node("chat_answer", node(chat_answer_node))
    g.add_node("plan", node(plan_node))
    g.add_node("gate", node(gate_node))
    g.add_node("research", node(research_node))
    g.add_node("replan_check", node(replan_check_node))
    g.add_node("analysis", node(analysis_node))
    g.add_node("write", node(write_node))
    g.add_node("validate", node(validate_node))
    g.add_node("finalize", node(finalize_node))

    g.set_entry_point("route")
    g.add_conditional_edges("route", _after_route,
                            {"chat_answer": "chat_answer", "plan": "plan", "done": END})
    g.add_edge("chat_answer", END)
    g.add_edge("plan", "gate")
    g.add_edge("gate", "research")
    g.add_edge("research", "replan_check")
    g.add_conditional_edges("replan_check", _after_replan_check,
                            {"analysis": "analysis", "research": "research", "finalize": "finalize"})
    g.add_edge("analysis", "write")
    g.add_edge("write", "validate")
    g.add_conditional_edges("validate", _after_validate,
                            {"finalize": "finalize", "write": "write"})
    g.add_edge("finalize", END)
    return g.compile()
