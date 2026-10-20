"""python -m unittest discover -s tests -v (표준 라이브러리 사용)."""
import asyncio
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.evidence import checked_status, render_answer, safe_notes
from agent.intent import classify, targets_for
from agent.retrieval import RunbookSearch, normalized
from agent.session_store import SqliteSessionStore
from sh.export_chat import export_chat

ROOT = Path(__file__).resolve().parent.parent


def monitoring(target="payments-service", age=0):
    now = datetime.now(timezone.utc)
    return {"system_name": target, "status": "degraded", "cpu_percent": 93.0,
            "memory_percent": 55.0, "last_checked": (now - timedelta(seconds=age)).isoformat(),
            "alerts": ["CPU utilization high"]}


class CoreTests(unittest.TestCase):
    def test_target_aliases_and_boundaries(self):
        self.assertEqual(targets_for("결제랑 cache-service가 느려요"), (["cache-service", "payments-service"], []))
        self.assertEqual(classify("로그인 응답이 느려요")[1], ["auth-service"])
        self.assertEqual(classify("billing-service 로그인 실패")[0], "clarify")
        self.assertEqual(targets_for("billing-auth-service 느려요")[0], [])

    def test_chat_clarify_and_procedure(self):
        self.assertEqual(classify("안녕, 너는 누구야?")[0], "chat")
        self.assertEqual(classify("응답이 느려요")[0], "clarify")
        self.assertEqual(classify("DB 다운 절차 알려줘")[0], "runbook")
        self.assertEqual(classify("payments-service 재시작해줘")[0], "unsupported")
        self.assertEqual(classify("재시작 절차 알려줘")[0], "runbook")

    def test_observations_are_validated_and_stale_is_explicit(self):
        data = checked_status(monitoring(age=600), "payments-service")
        answer = render_answer([{"source": "monitoring", "data": data, "evidence_id": "E1"}])
        self.assertIn("CPU 93.0%", answer)
        self.assertIn("메모리 55.0%", answer)
        self.assertIn("오래된 관측", answer)
        for change in ({"cpu_percent": math.nan}, {"memory_percent": -1}, {"cpu_percent": True},
                       {"system_name": "auth-service"}, {"status": "unknown"}, {"alerts": [1]}):
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                checked_status({**monitoring(), **change}, "payments-service")

    def test_generated_numbers_and_other_targets_are_removed(self):
        notes, rejected = safe_notes("1) CPU 39%가 원인입니다.\n2) 메모리 93%를 확인하세요.\nauth-service를 점검하세요.\n트래픽 변화를 확인하세요.", ["payments-service"])
        self.assertTrue(rejected)
        self.assertEqual(notes, "트래픽 변화를 확인하세요.")
        self.assertEqual(safe_notes("재시작하면 됩니다.", [])[0], "")

    def test_missing_is_not_healthy_or_zero(self):
        answer = render_answer([{"source": "missing", "target": "cache-service", "data": "조회 실패"}])
        self.assertIn("조회 실패", answer)
        self.assertNotIn("healthy", answer)
        self.assertNotIn("CPU 0", answer)

    def test_empty_markdown_headings_are_not_explanations(self):
        draft = "## 원인 후보**\n- CPU 39%를 확인하세요.\n## 확인 절차**"
        notes, rejected = safe_notes(draft, ["payments-service"])
        self.assertEqual(notes, "")
        self.assertTrue(rejected)
        notes, _ = safe_notes("**원인 후보**\n- 트래픽 변화를 확인하세요.\n**확인 절차:**", [])
        self.assertEqual(notes, "트래픽 변화를 확인하세요.")

    def test_filler_and_unsupported_tool_advice_are_removed(self):
        notes, rejected = safe_notes("가능성이 있습니다.\n확인하세요.\n가능성이 있습니다.\nget_monitoring_status 명령어로 배포 이력을 확인하세요.\n트래픽은 별도 대시보드에서 확인하세요.", [])
        self.assertTrue(rejected)
        self.assertEqual(notes, "트래픽은 별도 대시보드에서 확인하세요.")

    def test_runbook_is_a_short_checklist_with_a_source(self):
        text = (ROOT / "data/runbooks/cpu-spike.md").read_text(encoding="utf-8")
        answer = render_answer([
            {"source": "monitoring", "data": checked_status(monitoring(), "payments-service"), "evidence_id": "E1"},
            {"source": "runbook", "data": text, "doc_id": "cpu-spike", "target": "payments-service", "evidence_id": "E2"},
        ])
        self.assertIn("[E2]", answer)
        self.assertIn("cpu-spike", answer)
        self.assertIn("최근 배포/트래픽", answer)
        self.assertNotIn("5. 정상화 후", answer)
        self.assertIn("원인을 특정할 수 없습니다", answer)

    def test_pending_persists_and_is_thread_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sessions.db"
            store = SqliteSessionStore(path)
            store.set_pending("a", "응답이 느려요")
            store.append("a", "user", "제 이름은 민수입니다")
            store.close()
            store = SqliteSessionStore(path)
            try:
                self.assertEqual(store.get_pending("a"), "응답이 느려요")
                self.assertIsNone(store.get_pending("b"))
                self.assertEqual(store.load("a")[0]["content"], "제 이름은 민수입니다")
                store.set_pending("a", None)
                self.assertIsNone(store.get_pending("a"))
            finally:
                store.close()

    def test_invalid_vectors_are_rejected(self):
        self.assertEqual(normalized([3, 4]), [0.6, 0.8])
        for vector in ([], [0, 0], [float("inf"), 1], [float("nan")], ["x"]):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                normalized(vector)

    def test_chat_export_is_read_only_and_can_select_a_thread(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "chat.db"
            output = Path(folder) / "chat.md"
            store = SqliteSessionStore(db)
            store.append("a", "user", "payments-service 진단해줘")
            store.append("a", "assistant", "확인된 사실: CPU 90%")
            store.append("b", "user", "다른 대화")
            store.close()
            self.assertEqual(export_chat(db, output, "a"), 2)
            text = output.read_text(encoding="utf-8")
            self.assertIn("payments-service 진단해줘", text)
            self.assertIn("CPU 90%", text)
            self.assertNotIn("다른 대화", text)
            store = SqliteSessionStore(db)
            try:
                self.assertEqual(len(store.load("a")), 2)
                self.assertEqual(len(store.load("b")), 1)
            finally:
                store.close()


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_ranking_cache_and_no_match(self):
        requests = []
        class Client:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def post(self, url, json):
                requests.append(json)
                vectors = [[1, 0] if "cpu" in text else [0.6, 0.8] if "memory" in text else [-1, -1] for text in json["input"]]
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"embeddings": vectors})
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "cpu.md").write_text("# cpu\nCPU 대응", encoding="utf-8")
            Path(folder, "memory.md").write_text("# memory\n메모리 대응", encoding="utf-8")
            retriever = RunbookSearch(Path(folder))
            with patch.dict(sys.modules, {"httpx": SimpleNamespace(AsyncClient=Client)}):
                self.assertEqual([d["doc_id"] for d in await retriever.search("cpu")], ["cpu"])
                self.assertEqual(await retriever.search("unrelated"), [])
            self.assertEqual([len(request["input"]) for request in requests], [3, 1])


STACK_AVAILABLE = all(importlib.util.find_spec(name) for name in ("fastapi", "langgraph", "langsmith", "mcp", "httpx", "dotenv"))


@unittest.skipUnless(STACK_AVAILABLE, "requirements.txt 설치 후 그래프·SSE 테스트 실행")
class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from agent.deps import SupervisorDeps
        from agent.fake_llm import FastLLM
        from agent.graph import build_graph
        self.calls = []
        self.failed_targets = set()
        self.age = 0
        self.search_queries = []
        self.writer_calls = 0
        owner = self
        class MCP:
            async def find_prompt(self, name):
                return "ops"
            async def get_prompt(self, *args, **kwargs):
                return "상태를 조회하고 근거를 확인하세요."
            async def call_tool(self, name, arguments):
                target = arguments["system_name"]
                owner.calls.append(target)
                if target in owner.failed_targets:
                    raise ValueError("injected failure")
                return monitoring(target, owner.age)
        class Retriever:
            async def search(self, query):
                owner.search_queries.append(query)
                doc_id = "db-down" if "DB 다운" in query else "cpu-spike"
                return [{"doc_id": doc_id, "text": (ROOT / f"data/runbooks/{doc_id}.md").read_text(encoding="utf-8")}]
        class WrongWriter:
            async def write(self, query, collected, attempt, feedback, on_token=None):
                owner.writer_calls += 1
                draft = "payments-service CPU 39%가 원인입니다."
                if on_token:
                    on_token(draft)
                return draft, {"usd": 0.0}
        self.store = SqliteSessionStore(":memory:")
        self.deps = SupervisorDeps(FastLLM("fake", 0), WrongWriter(), MCP(), self.store, "v2", Retriever())
        self.graph = build_graph(self.deps)

    async def asyncTearDown(self):
        self.store.close()

    async def invoke(self, query, thread="test"):
        return await self.graph.ainvoke({"query": query, "thread_id": thread, "history": self.store.load(thread), "events": [], "cost_usd": 0.0})

    async def test_clarification_resume_and_scope(self):
        first = await self.invoke("응답이 느려요")
        self.assertEqual(first["intent"], "clarify")
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.store.get_pending("another"))
        second = await self.invoke("payments-service야")
        self.assertIn("응답이 느려요", second["query"])
        self.assertEqual(self.calls, ["payments-service"])
        self.assertIsNone(self.store.get_pending("test"))

    async def test_unregistered_does_not_call_monitoring(self):
        result = await self.invoke("billing-service 응답이 느려요")
        self.assertIn("미등록", result["final"])
        self.assertEqual(self.calls, [])

    async def test_wrong_draft_never_becomes_a_fact(self):
        result = await self.invoke("payments-service CPU 급증")
        self.assertIn("CPU 93.0%", result["final"])
        self.assertNotIn("CPU 39%", result["final"])
        self.assertEqual(result["validation_attempts"], 2)
        self.assertNotIn("auth-service", self.calls)
        self.assertNotIn("web-01", self.calls)

    async def test_partial_failure_keeps_success(self):
        self.failed_targets.add("cache-service")
        result = await self.invoke("payments-service랑 cache-service 둘 다 느려요")
        self.assertIn("CPU 93.0%", result["final"])
        self.assertIn("cache-service: 모니터링 미확보", result["final"])

    async def test_all_failure_and_stale(self):
        self.failed_targets.add("payments-service")
        result = await self.invoke("payments-service 진단해줘")
        self.assertIn("확인된 관측 사실이 없습니다", result["final"])
        self.failed_targets.clear()
        self.age = 600
        result = await self.invoke("payments-service 진단해줘")
        self.assertIn("오래된 관측", result["final"])
        self.assertFalse(any(c["source"] == "runbook" for c in result["collected"]))

    async def test_procedure_and_cancel(self):
        result = await self.invoke("DB 다운 절차 알려줘")
        self.assertEqual(result["intent"], "runbook")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.writer_calls, 0)
        self.assertNotIn("확인된 관측 사실이 없습니다", result["final"])
        self.assertNotIn("원인 후보", result["final"])
        self.assertIn("서비스 정상화", result["final"])
        await self.invoke("응답이 느려요")
        await self.invoke("취소")
        self.assertIsNone(self.store.get_pending("test"))

    async def test_multi_target_search_does_not_mix_other_targets(self):
        await self.invoke("payments-service와 cache-service 상태를 각각 확인해 줘")
        self.assertEqual(len(self.search_queries), 2)
        self.assertIn("cache-service", self.search_queries[0])
        self.assertNotIn("payments-service", self.search_queries[0])
        self.assertIn("payments-service", self.search_queries[1])
        self.assertNotIn("cache-service", self.search_queries[1])
        self.assertIn("모니터링 알림에 대한 장애 대응 절차:", self.search_queries[0])
        self.search_queries.clear()
        async def no_alerts(name, arguments):
            return {**monitoring(arguments["system_name"]), "alerts": []}
        self.deps.mcp.call_tool = no_alerts
        result = await self.invoke("payments-service와 cache-service 상태 확인해 줘")
        self.assertEqual(self.search_queries, [])
        self.assertIn("알림이 없어 대표 런북을 선택하지 않음", result["final"])

    async def test_user_name_is_not_the_assistants_identity(self):
        async def wrong_identity(*args, **kwargs):
            return "저는 기준입니다.", {"usd": 0.0}
        self.deps.fast_llm.chat = wrong_identity
        intro = await self.invoke("제 이름은 기준입니다")
        self.assertIn("기준님", intro["final"])
        self.assertNotIn("저는", intro["final"])
        self.store.append("test", "user", "제 이름은 기준입니다")
        self.store.append("test", "assistant", "저는 민수입니다")
        recall = await self.invoke("제 이름이 뭐였죠?")
        self.assertIn("기준님", recall["final"])
        self.assertNotIn("민수", recall["final"])
        self.assertNotIn("저는", recall["final"])
        unknown = await self.invoke("제 이름이 뭐였죠?", thread="another")
        self.assertIn("알려주시지 않았습니다", unknown["final"])
        self.assertNotIn("기준", unknown["final"])

    async def test_sse_only_emits_final_answer(self):
        import server
        server.app.state.deps = self.deps
        server.app.state.graph = self.graph
        response = await server.chat_stream("payments-service CPU 급증", "stream")
        chunks = [chunk async for chunk in response.body_iterator]
        events = [json.loads(line[6:]) for line in "".join(chunks).splitlines() if line.startswith("data: {")]
        self.assertFalse(any(e["type"] == "AnswerToken" for e in events))
        self.assertEqual(sum(e["type"] == "FinalAnswer" for e in events), 1)
        self.assertNotIn("CPU 39%", "".join(chunks))
        self.assertEqual(len(self.store.load("stream")), 2)


if __name__ == "__main__":
    unittest.main()
