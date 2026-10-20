"""고정 입력으로 14개 시나리오의 답변·경로·검색·시간을 저장한다. 실제 품질 판정은 별도 확인."""
import argparse
import asyncio
import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = [
    ("payments", ["payments-service 결제 응답이 느려지고 CPU가 치솟았어요, 원인 확인해주세요"], ["payments-service"], ["cpu-spike"]),
    ("cache", ["cache-service 메모리 사용률이 계속 올라가고 있어요"], ["cache-service"], ["memory-leak"]),
    ("disk", ["log-service 디스크 공간이 부족하다는 알림이 왔어요"], ["log-service"], ["disk-full"]),
    ("upstream", ["gateway-service에서 payments-service로 가는 요청이 타임아웃 나고 있어요"], ["gateway-service", "payments-service"], ["network-timeout"]),
    ("two-targets", ["web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘"], ["web-01", "auth-service"], ["high-latency"]),
    ("common-cause", ["payments-service랑 cache-service 둘 다 저하됐는데 공통 원인이 있는지 분석해줘"], ["payments-service", "cache-service"], ["cpu-spike", "memory-leak"]),
    ("alias", ["로그인 응답이 느려요, 원인 확인해주세요"], ["auth-service"], ["high-latency"]),
    ("unregistered", ["billing-service 응답이 느려요"], [], []),
    ("chat", ["안녕, 너는 누구야?"], [], []),
    ("memory", ["제 이름은 민수입니다", "제 이름이 뭐였죠?"], [], []),
    ("clarify-resume", ["응답이 느려요", "payments-service야"], ["payments-service"], ["cpu-spike"]),
    ("similar-runbooks", ["gateway-service 504 타임아웃인데 디스크 문제인지 확인해줘"], ["gateway-service"], ["network-timeout"]),
    ("wrong-number", ["payments-service CPU 급증 원인 확인해줘"], ["payments-service"], ["cpu-spike"]),
    ("partial-failure", ["payments-service랑 cache-service 둘 다 느려요"], ["payments-service", "cache-service"], ["cpu-spike"]),
]


async def evaluate(args):
    project = ROOT
    if args.baseline:
        project = ROOT / ".tools" / "eval-baseline"
        project.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(ROOT / ".tools" / "original-baseline.zip") as archive:
            if any(not (project / name).resolve().is_relative_to(project.resolve()) for name in archive.namelist()):
                raise ValueError("압축 경로가 작업 폴더를 벗어남")
            archive.extractall(project)
        # 양쪽에 같은 Windows 호환 보정만 적용한다.
        for path in project.rglob("*.py"):
            path.write_text(path.read_text(encoding="utf-8").replace(".read_text()", '.read_text(encoding="utf-8")'), encoding="utf-8")
    sys.path.insert(0, str(project))
    args.model = args.model or ("gpt-4o-mini" if args.backend == "openai" else "qwen3.5:2b")
    os.environ.update(LLM_BACKEND=args.backend, SUPERVISOR_VERSION="v2", LANGCHAIN_TRACING_V2="false",
                      OLLAMA_FAST_MODEL=args.model, OLLAMA_QUALITY_MODEL=args.model,
                      OPENAI_FAST_MODEL=args.model, OPENAI_QUALITY_MODEL=args.model)
    if args.backend == "openai":
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")  # server.py의 load_dotenv()는 cwd 기준이라 키를 명시적으로 읽는다.
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY가 .env에 없습니다.")
    import httpx
    # 모델 추론 설정은 원본과 개선판에 공통 적용한다. 프롬프트·판단 로직은 그대로 둔다.
    options = {"temperature": 0.0, "num_ctx": 8192, "num_predict": 700}
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    def configured(url, kwargs):
        if str(url).endswith("/api/chat") and "json" in kwargs:
            kwargs["json"] = {**kwargs["json"], "think": False, "options": options}
            url = base_url + "/api/chat"
        return url
    original_post, original_stream = httpx.post, httpx.AsyncClient.stream
    def post(url, **kwargs):
        kwargs["timeout"] = 120.0
        return original_post(configured(url, kwargs), **kwargs)
    def stream(client, method, url, **kwargs):
        return original_stream(client, method, configured(url, kwargs), **kwargs)
    httpx.post, httpx.AsyncClient.stream = post, stream
    import server

    scenario_time = "2026-10-20T00:00:00+00:00"  # 평가용 가상 시각. 양쪽 snapshot을 동일하게 유지한다.
    source = json.loads((ROOT / "data/monitoring.json").read_text(encoding="utf-8"))
    snapshot = {name: {"system_name": name, "status": data["status"], "cpu_percent": data["cpu_base"],
                       "memory_percent": data["memory_base"], "alerts": data["alerts"],
                       "last_checked": scenario_time, "scenario_time": scenario_time} for name, data in source.items()}
    class FixedMCP:
        failures = set()
        calls = []
        async def start(self):
            pass
        async def stop(self):
            pass
        async def find_prompt(self, name):
            return "ops"
        async def get_prompt(self, name, arguments, server="ops"):
            return f"시스템: {arguments['system_name']}\n모니터링 조회 후 관련 런북을 확인하세요."
        async def find_resource_template(self, name):
            return "ops", "runbook://incident-response/{incident_type}"
        async def read_resource(self, uri, server="ops"):
            return (ROOT / "data/runbooks" / (uri.rsplit("/", 1)[-1] + ".md")).read_text(encoding="utf-8")
        async def call_tool(self, name, arguments, server="ops"):
            target = arguments["system_name"]
            self.calls.append(target)
            if target in self.failures:
                raise ValueError("injected monitoring failure")
            return snapshot.get(target, {"system_name": target, "status": "unknown", "cpu_percent": 0,
                "memory_percent": 0, "alerts": ["not found"], "last_checked": scenario_time})
    server.MCPClient = FixedMCP
    os.environ["SESSION_DB"] = ":memory:"
    # 원본은 SESSION_DB 환경변수를 읽지 않으므로, 같은 임시 세션 저장소를 주입한다.
    store_type = server.SqliteSessionStore
    server.SqliteSessionStore = lambda *args, **kwargs: store_type(":memory:")
    rows = []
    async with server.lifespan(server.app):
        deps = server.app.state.deps
        original_write = deps.quality_llm.write
        injected_calls = 0
        async def wrong_write(*args, **kwargs):
            nonlocal injected_calls
            injected_calls += 1
            return "1) payments-service CPU 39%입니다. 2) CPU 수치가 높아서 장애가 발생했습니다.", {"usd": 0.0}
        for name, turns, targets, docs in CASES:
            injected_calls = 0
            deps.mcp.calls = []
            deps.mcp.failures = {"cache-service"} if name == "partial-failure" else set()
            deps.quality_llm.write = wrong_write if name == "wrong-number" else original_write
            started = time.perf_counter()
            try:
                responses = [await asyncio.wait_for(server.chat(server.ChatRequest(message=turn, thread_id=name)), 480) for turn in turns]
                rows.append({"case": name, "seconds": round(time.perf_counter() - started, 3), "queried_targets": deps.mcp.calls,
                             "expected_targets": targets, "expected_runbooks": docs, "responses": responses,
                             "wrong_draft_calls": injected_calls})
            except Exception as exc:
                rows.append({"case": name, "seconds": round(time.perf_counter() - started, 3), "error": type(exc).__name__})
    report = {"backend": args.backend, "version": "baseline" if args.baseline else "after",
              "purpose": "flow-only" if args.backend == "fake" else "quality-review", "model": args.model,
              "options": options, "think": False, "snapshot": snapshot, "results": rows}
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 1 if any("error" in row for row in rows) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("fake", "ollama", "openai"), default="fake")
    parser.add_argument("--model", help="기본: ollama=qwen3.5:2b, openai=gpt-4o-mini(생성·분류 공통)")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--out", default="results/after.json")
    raise SystemExit(asyncio.run(evaluate(parser.parse_args())))
