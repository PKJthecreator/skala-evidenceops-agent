# 출력 수정 후 실행 확인

- 모드: 로컬 Ollama / 실습용 모니터링
- 모델: ollama:qwen3.5:2b
- 용도: 단일 사례 출력 확인 (공식 Before/After 성능 측정 아님)
- 전체 소요: 48.49초
- 질문: payments-service CPU가 급증했어요. 원인 확인해줘

확인된 사실
[E1] payments-service: 상태=degraded, CPU 89.2%, 메모리 54.1%, 관측 2026-10-20T13:22:20.246002

참고 런북
[E2] payments-service / cpu-spike — Runbook: CPU 급증 대응 절차 (참고 절차)
- get_monitoring_status로 CPU 사용률과 최근 배포/트래픽 변화 시점을 확인한다.
- 반복 호출, 배치 작업 중복 실행 같은 특정 요청 패턴이 원인인지 최근 로그에서 확인한다.

[E3] payments-service / high-latency — Runbook: 응답 지연(High Latency) 대응 절차 (참고 절차)
- get_monitoring_status로 p95 지연시간과 커넥션 풀 사용률을 확인한다.
- 정상화 후 느린 쿼리 로그를 분석해 근본 원인을 문서화하고 후속 최적화 티켓을 등록한다.

원인 후보·확인 사항 (추정)
확인하세요: get_monitoring_status 명령어를 사용하여 현재 CPU 사용률과 최근 트래픽 패턴을 다시 확인해 주세요.
