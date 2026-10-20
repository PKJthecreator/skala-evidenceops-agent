"""기존 서비스와 별칭으로 조사 대상을 제한한다."""
import json
import re
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parent.parent / "data" / "monitoring.json").read_text(encoding="utf-8"))
ALIASES = {
    "auth-service": ("로그인", "인증", "auth"),
    "payments-service": ("결제", "payments", "payment", "pg"),
    "cache-service": ("캐시", "cache"),
    "gateway-service": ("게이트웨이", "gateway"),
    "log-service": ("로그 서버", "로그서버"),
    "web-01": ("웹 서버", "웹서버"),
}
SERVICE_ID = re.compile(r"(?<![a-z0-9-])[a-z][a-z0-9-]*-(?:service|\d+)(?![a-z0-9-])", re.I)
SYMPTOM = re.compile(r"느[려리]|지연|장애|다운|급증|저하|타임아웃|메모리|디스크|부족|오류|실패|분석|모니터링|확인|cpu|timeout|latency|incident|504|connection pool", re.I)
PROCEDURE = re.compile(r"절차|런북|runbook|대응\s*방법", re.I)
ACTION = re.compile(r"(?:재시작|재부팅|롤백|restart|rollback|failover).*(?:해\s*줘|해주세요|실행|시켜)", re.I)
NAME_INTRO = re.compile(r"(?:제|내)\s*이름은\s*([가-힣A-Za-z]{1,20}?)(?:입니다|이에요|예요|이야|야)[.!?]?\s*")


def name_reply(query: str, history: list[dict]) -> str | None:
    """흔한 이름 소개·회상은 사용자 발화만 읽어 화자 혼동을 막는다."""
    introduced = NAME_INTRO.fullmatch(query.strip())
    if introduced:
        return f"반갑습니다, {introduced[1]}님. 이 대화에서 이름을 기억하겠습니다."
    if re.fullmatch(r"(?:제|내)\s*이름(?:이|은)?\s*(?:뭐였죠|뭐였지|뭐야|뭐예요|뭐였나요|기억해)[.!?]?\s*", query.strip()):
        for message in reversed(history):
            match = NAME_INTRO.fullmatch(message["content"].strip()) if message["role"] == "user" else None
            if match:
                return f"{match[1]}님이라고 알려주셨습니다."
        return "아직 이 대화에서 이름을 알려주시지 않았습니다."
    return None


def targets_for(query: str) -> tuple[list[str], list[str]]:
    query = query.casefold()
    explicit = SERVICE_ID.findall(query)
    unknown = sorted(set(explicit) - CATALOG.keys())
    targets = {name for name in explicit if name in CATALOG}
    for name, aliases in ALIASES.items():
        if any(re.search(r"(?<![a-z0-9-])" + re.escape(alias) + r"(?![a-z0-9-])", query) for alias in aliases):
            targets.add(name)
    return sorted(targets), unknown


def classify(query: str, llm_route: str = "chat") -> tuple[str, list[str], str]:
    targets, unknown = targets_for(query)
    if ACTION.search(query) and not PROCEDURE.search(query):
        return "unsupported", [], "실제 재시작·롤백은 지원하지 않습니다. 상태 진단이나 대응 절차를 요청해 주세요."
    if unknown:
        return "clarify", [], "미등록 서비스: " + ", ".join(unknown) + ". 등록된 서비스명을 확인해 주세요: " + ", ".join(CATALOG)
    if PROCEDURE.search(query):
        return "runbook", targets, ""
    if targets or SYMPTOM.search(query) or llm_route == "incident":
        if targets:
            return "diagnose", targets, ""
        return "clarify", [], "어느 서비스인가요? 등록된 서비스: " + ", ".join(CATALOG)
    return "chat", [], ""
