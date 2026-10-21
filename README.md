# EvidenceOps

SKALA AI Capstone 제공 `all_total_vue` 개선 — 박기준.
서비스 대상을 확인하고, 기존 6개 런북을 RAG로 검색하며, 관측 사실을 조회 결과에서 직접 표시합니다.

## 실행 (Windows, Python 3.12)

```powershell
.\sh\setup_venv.ps1
.\sh\run.ps1
# 다른 터미널
.\sh\run.ps1 -Frontend
```

채팅 화면은 http://localhost:8600, API는 http://localhost:8100/docs 입니다.
Python이 PATH에 없으면 setup_venv.ps1의 `-PythonExe`에 실행 파일 경로를 지정합니다.
실행 정책으로 ps1이 차단되면 PowerShell에서 `.venv\Scripts\python.exe server.py`와 `web_demo_server.py`를 각각 직접 실행할 수 있습니다.
세션은 SQLite에 저장하며 실행할 때 삭제하지 않습니다.

로컬 모델은 현재 설치된 `qwen3.5:2b`를 기본값으로 재사용합니다. 런북 검색에는 `bge-m3`가 추가로 필요합니다.

```powershell
ollama pull bge-m3
.\sh\run.ps1 -Backend ollama
```

`fake`는 생성 모델 없는 흐름 확인용입니다. 런북 검색에는 Ollama 임베딩이 필요하며, 검색할 수 없으면 모니터링 사실과 제한 사항만 답합니다.
LangSmith와 유료 API는 기본 실행에 필요하지 않습니다. 키는 `.env`에만 보관합니다.

## 확인

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe eval\run_eval.py --backend ollama --out results\after.json
.\.venv\Scripts\python.exe eval\run_eval.py --backend ollama --baseline --out results\before.json
```

14개 시나리오의 답변·실제 조회 대상·검색 이벤트·응답 시간을 JSON으로 저장합니다. fake 결과는 품질 점수로 사용하지 않습니다.
수치와 런북 선택은 결과 JSON의 고정 snapshot·기대 문서와 대조합니다. 원본 비교는 `.tools/original-baseline.zip`이 있을 때 실행할 수 있습니다(원본 코드는 Git 태그 `original-baseline`에도 있습니다). 결과 요약은 [Before/After](results/before_after.md)에 있습니다.
양쪽 생성 모델·추론 설정·관측 시각·모니터링 값·런북은 동일하게 적용합니다. 평가에서는 고정된 시나리오 시각을 사용하며, 시간 비교는 모델 예열 후 별도로 반복합니다.

## 결정과 한계

- 서비스명·소수 별칭으로 대상을 확정합니다. 단서가 없으면 되묻고, 다른 thread로 보류 요청을 넘기지 않습니다.
- 소수 런북은 메모리에서 코사인 유사도로 검색해 장애 유형(incident_type)을 고르고, 본문은 기존 MCP Resource(`runbook://incident-response/{유형}`)로 읽습니다. 대상별 대표 문서 1개만 제시합니다. 복수 서비스는 각 서비스의 첫 알림에 ‘장애 대응 절차’ 문맥을 붙여 따로 검색하며, 알림이 없으면 선택을 보류합니다. 모든 복합 장애를 찾는 방식은 아닙니다. 문서 변경 시 서버를 재시작합니다. `RUNBOOK_MIN_SCORE`(기본 0.55)는 실제 모델 결과를 보고 조정할 수 있습니다.
- 대상·CPU·메모리·시각·알림은 코드로 표시하고, 생성된 수치 문장은 제거합니다. 문장 검사는 보수적인 규칙이며 인과 설명의 정확성을 보증하지 않아 원인 후보로 구분합니다.
- 일반 절차 질문은 검색한 런북의 전체 절차를 바로 보여줍니다. 진단 응답은 점검 항목 2개로 줄입니다. 도구는 현재 상태·CPU·메모리·알림만 제공하며, 로그·배포 이력·추세·p95는 별도 자료가 필요합니다.
- 흔한 이름 소개·회상 표현은 같은 대화의 사용자 발화에서 확인합니다. 자유로운 표현 전체를 처리하는 대화 기억 시스템은 아닙니다.
- 조회 실패·5분 넘은 관측은 정상으로 간주하지 않습니다. 생성 초안 토큰은 전송하지 않습니다.
- MCP는 원본 클라이언트의 Lock으로 직렬 처리합니다. 원본의 교육용 고정 sleep은 제거했으므로 시간 차이를 병렬화 효과로 해석하지 않습니다.

## 시연 기록 내보내기

질문·최종 답변·저장 시각은 `session.db`에 남습니다. 새로고침하면 화면은 새 대화로 시작하지만 기존 DB 기록은 유지됩니다. 진행 이벤트는 자동 저장하지 않으므로 시연 과정은 화면 캡처도 남깁니다.

```powershell
.\.venv\Scripts\python.exe sh\export_chat.py
```

`results/chat_history.md`를 PPT 작성 자료로 사용할 수 있습니다. 기본 내보내기 파일은 Git에서 제외됩니다.

계획은 [개선계획](AI-Mini-Project_과제1_개선계획.md), 현재 실행 확인과 남은 문제는 [진행 기록](doc/progress.md)을 참고하세요.
