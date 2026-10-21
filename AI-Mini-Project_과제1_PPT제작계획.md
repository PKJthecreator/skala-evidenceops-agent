# AI Mini-Project 과제 1 — 발표 PPT 제작 계획

- 프로젝트: **EvidenceOps — 근거로 말하는 장애 진단 에이전트** (박기준, SKALA 4기 광주 2반)
- 작성: 2026-10-21. 발표·제출: 10/22(Day3). 근거 자료: 이 저장소의 코드·`results/`·`doc/`

## 1. 기준: 평가 항목에 맞춘 구성

과제 안내서(AI-Mini-Project_20261004_2)의 평가 항목과 순서를 그대로 따른다.

| 평가 항목 | 배점 | PPT에서 답할 질문 | 담당 슬라이드 |
|---|---|---|---|
| 기능 구현 완성도 | 30 | 개선안이 실제로 동작하는가? | 6–9, 12(시연) |
| Before/After 실측 비교 | 10 (보너스) | 같은 입력으로 수치 차이를 보였는가? | 11 |
| 기술 요소 반영 | 30 | Multi-Agent·MCP·RAG·DI·LangSmith·모듈화·단위 테스트 | 5, 10 |
| 한계·트레이드오프 | 20 | 개선이 새로 만든 약점을 스스로 짚었는가? | 13 |
| 발표 PPT | 20 | 문제 → 개선 포인트 → Before/After 수치 → 한계·추가 개선 순서인가? | 전체 흐름 |

핵심 메시지 한 줄: **“대상을 임의로 고르지 않고, 조회한 근거로만 사실을 말한다.”**

## 2. 슬라이드 구성 (15장, 발표 약 8–10분)

| # | 제목 | 핵심 내용 | 시각 자료 | 근거 파일 |
|---|---|---|---|---|
| 1 | 표지 | EvidenceOps / 과제1 Base AI Agent 개선 / 이름·반·GitHub 주소 | 로고 없이 제목 중심 | — |
| 2 | 한눈에 보는 결과 | 숫자 3개: 미등록 서비스 임의 조회 제거, 틀린 수치 초안 노출 차단, 부분 실패 시 오류 → 부분 응답 | 큰 숫자 카드 3개 | `results/before_after.md` |
| 3 | 문제: Base의 실제 약점 | ① 대상이 없거나 미등록이면 auth-service를 임의 조회 ② 키워드 매핑·무조건 `db-down` 폴백 ③ LLM 초안의 수치가 그대로 최종 답변·스트림에 노출 ④ 한 대상 조회 실패 시 전체 오류 | Base 답변 원문 인용 2개 (billing-service, CPU 39%) | `results/before.json`, Base `agent/graph.py` |
| 4 | 개선 목표와 범위 | 핵심 3개(대상 확인·런북 RAG·근거 기반 응답) + 최소 오류 처리. 보류: Hybrid·Reranker·Vector DB·HITL·LLM-as-Judge — 이유는 “2.5일, 6개 런북” | 범위 표 (한 일 / 안 한 일) | 개선계획 2·6절 |
| 5 | 아키텍처 Before → After | LangGraph 노드 흐름에서 바뀐 노드만 색칠: route(의도·대상 확정) → plan → gate → research(MCP Tool) → replan_check(RAG → MCP Resource) → analysis → write → validate → finalize | 좌우 비교 다이어그램 | `agent/graph.py` |
| 6 | 개선 1 — 대상 확인 | 서비스 카탈로그 + 별칭(로그인→auth-service), 미등록 안내, 대상 없으면 되묻기 → SQLite `pending`(thread 단위) → 다음 답으로 이어서 진단. 재시작·롤백 실행 요청은 지원 범위 안내 | 대화 캡처: “응답이 느려요 → payments-service야” | `agent/intent.py`, `agent/session_store.py` |
| 7 | 개선 2 — 런북 RAG | 6개 런북을 bge-m3로 임베딩(메모리), 코사인 유사도, 최소 점수 0.55. 대상별로 따로 검색해 서비스 간 혼입 방지. RAG는 장애 유형만 고르고 본문은 MCP Resource로 읽음. `db-down` 기본값 제거 | 검색 흐름도 + `RetrievalCompleted` 이벤트 화면 | `agent/retrieval.py`, `replan_check_node` |
| 8 | 개선 3 — 근거 기반 응답 | 사실(상태·CPU·메모리·관측 시각·알림)은 코드가 조회값으로 출력하고 근거 ID `[E1]` 부여. LLM 설명은 ‘원인 후보’로만, 숫자·단정·다른 서비스 문장은 필터 → 재작성 1회. SSE는 초안 토큰을 보내지 않고 진행 이벤트 + 최종 답변만 | 최종 답변 구조 캡처(확인된 사실 / 참고 런북 / 원인 후보 / 제한 사항) | `agent/evidence.py`, `server.py` |
| 9 | 오류 처리 | 부분 실패 보존, 5분 넘은 관측은 오래된 값으로 표시·진단 제외, 호출 상한(MCP 5s·임베딩 60s·LLM 120s), 타임아웃만 재시도(Wave 9), MCP `isError` 처리 | 부분 실패 답변 캡처 | `research_node`, `agent/retry.py` |
| 10 | 기술 요소 매핑 | 아래 3절 표를 한 장으로 | 표 | 각 파일 |
| 11 | Before/After 실측 | 14개 시나리오, 같은 모델·옵션·고정 데이터. 대상 처리 / 런북 선택 / 수치 일치 / 응답 시간 4열 표. **느려진 결과도 그대로** 표시 | 표 + 평균 응답시간 막대 2개 | `results/before_after.md` |
| 12 | 시연 | 아래 4절의 4개 장면 (라이브 또는 녹화) | 웹 채팅 화면 | `web_chat.html` |
| 13 | 한계·트레이드오프 | 아래 5절 | 표 (약점 / 원인 / 영향 / 대응) | `results/`, 임베딩 점수 |
| 14 | 추가 개선 계획 | Hybrid(BM25+RRF)·런북 메타데이터, 복수 런북 선택, LLM-as-Judge로 수치 인용 채점, HITL `interrupt()`로 재시작 승인, LangSmith 데이터셋 평가 | 로드맵 3단계 | 개선계획 6절 |
| 15 | 마무리 / Q&A | 핵심 메시지 반복, GitHub·보고서 주소 | — | — |

## 3. 기술 요소 매핑 (슬라이드 10)

| 평가 기술 요소 | 이 프로젝트에서의 위치 | 발표 포인트 |
|---|---|---|
| Multi-Agent | `agent/graph.py` Supervisor 그래프(route·plan·gate·research·analysis·write·validate) | Base 구조 유지, 대상 확정과 검증을 코드 권한으로 이동 |
| MCP | `mcp_server.py` Tool(`get_monitoring_status`)·Resource(런북)·Prompt(진단 절차), `agent/mcp_client.py` | 3가지 capability 모두 실제 흐름에서 사용 |
| RAG | `agent/retrieval.py` | Vector DB 없이 6개 문서를 메모리 색인 — 규모에 맞춘 선택 |
| 의존성 주입 | `agent/deps.py` `SupervisorDeps` + `functools.partial` | 검색기도 DI로 주입 → 테스트에서 모의 객체로 교체 |
| LangSmith | 각 노드 `@traceable`, 검색은 `runbook_search`(retriever) span | 트레이스 캡처 1장(키가 있으면) |
| 모듈화 | `intent.py`·`retrieval.py`·`evidence.py` 신규 분리 | 그래프 노드는 흐름만, 판단 로직은 모듈로 |
| 단위 테스트 | `tests/test_core.py` 21개(표준 unittest) | 그래프·SSE 경로까지 모의 MCP/LLM으로 검증 |
| 세션(Stateless) | `agent/session_store.py` SQLite + `pending` 테이블 | 되묻기 상태도 프로세스 밖에 저장 |

## 4. 시연 시나리오 (슬라이드 12)

`.\sh\run.ps1 -Backend ollama` + `.\sh\run.ps1 -Frontend` → http://localhost:8600. 장면마다 진행 이벤트가 보이게 캡처한다.

1. **되묻기 → 이어가기**: “응답이 느려요” → “payments-service야”
2. **미등록 서비스**: “billing-service 응답이 느려요” → 임의 조회 없이 안내
3. **복수 대상 + 대상별 런북**: “payments-service와 cache-service 상태를 각각 확인해 줘”
4. **일반 절차**: “DB 다운 절차 알려줘” → 현재 장애 진단이 아님을 명시

라이브 시연 실패 대비: 같은 장면의 캡처·녹화를 미리 슬라이드에 넣는다(로컬 2B 모델은 응답에 20–40초 걸린다).
Before 쪽 화면이 필요하면 `git worktree add ..\evidenceops-base original-baseline`로 원본을 따로 띄워 같은 질문을 캡처한다. 시간이 없으면 `results/before.json`의 답변 원문을 인용한다.

## 5. 한계·트레이드오프 (슬라이드 13, 20점 항목)

| 새로 생긴 약점 | 근거 | 대응 / 다음 단계 |
|---|---|---|
| 응답이 느려짐 | 검색·검수 단계 추가로 평균 응답 시간 증가(11번 표) | 런북 벡터 캐시는 이미 적용. 다음: 검색·조회 병렬화 |
| 임베딩 점수 차이가 작음 | 단일 cache 질문에서 cpu-spike 0.544 vs memory-leak 0.530 — 상위 1개가 뒤바뀜 | Hybrid(BM25)·런북 메타데이터 태그 |
| 대표 런북 1개, 첫 알림 기준 | 복합 장애의 모든 유형을 찾지 못함 | 알림 우선순위·복수 선택 평가 |
| 규칙 기반 문장 필터 | 안전하지만 LLM 설명을 많이 지워 “원인을 특정할 수 없음”이 자주 나옴 | LLM-as-Judge로 인용 정확도 채점 후 완화 |
| 이름·별칭 처리 범위 | 소수 정규식 패턴만 지원 | 필요 시 NER·카탈로그 확장 |
| MCP Lock 직렬 | 병렬 조회 효과가 제한됨 | 세션 풀 또는 서버별 Lock |
| 평가 규모 | 14개 시나리오·1회 실행, 합성 모니터링 데이터 | 일반 정확도로 해석하지 않음, 데이터셋 확장 |

## 6. 예상 질문과 답변 준비

| 질문 | 답변 요지 |
|---|---|
| 왜 Vector DB를 쓰지 않았나? | 런북 6개라 메모리 색인으로 충분. DB 도입은 운영 비용만 늘림. 문서가 늘면 영속 색인으로 전환 |
| 느려졌는데 개선인가? | 속도 대신 정확성·안전성을 택한 트레이드오프. 틀린 수치·임의 대상 진단을 막은 것이 목표 |
| LLM 설명이 다 지워지면? | 사실·런북 점검 항목은 항상 남고 “원인 특정 불가”로 정직하게 답함. 필터가 보수적이라는 점은 한계로 인정 |
| temperature 0인데 결과가 다른 이유? | 실모델은 완전 결정론이 아니고, 모니터링 데이터에 jitter가 있음. 평가는 고정 snapshot 사용 |
| AI 도구로 만든 코드인가? | 도구는 사용했지만 각 노드·필터·테스트를 직접 설명 가능 — `graph.py` 흐름을 화이트보드로 설명할 수 있게 준비 |

## 7. 제작 일정 (10/22)

| 시간 | 할 일 | 산출물 |
|---|---|---|
| 09:00–09:40 | 서버 재시작 후 시연 4장면 캡처, `sh/export_chat.py`로 대화 기록 내보내기 | PNG 4–6장, `results/chat_history.md` |
| 09:40–10:00 | (선택) LangSmith 키로 트레이스 1건 캡처 | PNG 1장 |
| 10:00–11:30 | 슬라이드 1–11 작성 | 초안 |
| 11:30–12:30 | 슬라이드 12–15, 발표 대본·시간 측정(10분 이내) | 완성본 |
| 12:30–13:00 | GitHub 푸시, Google Spread에 Git·보고서 주소 등록 | 제출 |

## 8. 디자인 원칙

- 16:9, 슬라이드당 메시지 1개. 제목을 결론 문장으로 쓴다(예: “틀린 수치는 최종 답변에 나가지 않는다”).
- 숫자는 크게, 코드는 5줄 이하로만 인용한다. 긴 코드는 파일 경로로 대신한다.
- Before는 회색, After는 강조색 한 가지로 통일한다.
- 캡처의 모니터링 수치는 “실습용 시뮬레이션 데이터”라고 각주를 단다.
- 검증하지 않은 표현(근본 원인 확인, 정확도 N% 향상, 실제 서버 조치)은 쓰지 않는다.
