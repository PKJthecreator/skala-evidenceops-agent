# 캡처 질문 수정 후 실행 확인

실제 로컬 MCP·Ollama·임베딩 확인. 합성 모니터링 데이터이며 공식 Before/After 성능 측정은 아닙니다.

## cpu (50.45초)

질문: payments-service CPU가 급증했어요. 원인 확인해줘

확인된 사실
[E1] payments-service: 상태=degraded, CPU 93.8%, 메모리 56.4%, 관측 2026-10-20T13:55:26.339820

참고 런북
[E2] payments-service / cpu-spike — Runbook: CPU 급증 대응 절차 (참고 절차)
- get_monitoring_status로 현재 CPU 사용률과 알림을 확인한다. 최근 배포/트래픽 변화 시점은 별도 배포 기록과 트래픽 대시보드에서 확인한다.
- 반복 호출, 배치 작업 중복 실행 같은 특정 요청 패턴이 원인인지 최근 로그에서 확인한다.

원인 판단
현재 근거만으로 원인을 특정할 수 없습니다. 참고 런북의 점검 항목을 확인해 주세요.

## resume (36.41초)

질문: 응답이 느려요

어느 서비스인가요? 등록된 서비스: auth-service, web-01, payments-service, cache-service, gateway-service, log-service

질문: cache-service야

확인된 사실
[E1] cache-service: 상태=degraded, CPU 39.9%, 메모리 88.0%, 관측 2026-10-20T13:58:15.057674

참고 런북
[E2] cache-service / high-latency — Runbook: 응답 지연(High Latency) 대응 절차 (참고 절차)
- get_monitoring_status로 서비스의 현재 상태와 알림을 확인한다. p95 지연시간과 커넥션 풀 사용률은 별도 APM과 DB 대시보드에서 확인한다.
- 정상화 후 느린 쿼리 로그를 분석해 근본 원인을 문서화하고 후속 최적화 티켓을 등록한다.

원인 판단
현재 근거만으로 원인을 특정할 수 없습니다. 참고 런북의 점검 항목을 확인해 주세요.

## unregistered (2.27초)

질문: billing-service 응답이 느려요

미등록 서비스: billing-service. 등록된 서비스명을 확인해 주세요: auth-service, web-01, payments-service, cache-service, gateway-service, log-service

## procedure (2.52초)

질문: DB 다운 절차 알려줘

일반 대응 절차입니다. 현재 장애나 원인을 확인한 결과는 아닙니다.

참고 런북
[E1] 일반 절차 / db-down — Runbook: DB Down 대응 절차 (참고 절차)
- 등록된 서비스의 현재 상태와 알림은 get_monitoring_status로 확인한다. DB 장애 여부는 별도 DB 모니터링에서 확인한다.
- 커넥션 풀/리플리케이션 상태를 점검하고 필요 시 failover 노드로 전환한다.
- 서비스 정상화 확인 후 원인 분석과 재발 방지 대책을 문서화한다.

## multiple (48.19초)

질문: payments-service와 cache-service 상태를 각각 확인해 줘

확인된 사실
[E1] cache-service: 상태=degraded, CPU 43.9%, 메모리 89.9%, 관측 2026-10-20T14:01:53.614381
[E2] payments-service: 상태=degraded, CPU 95.0%, 메모리 57.0%, 관측 2026-10-20T14:01:53.303040

참고 런북
[E3] cache-service / memory-leak — Runbook: 메모리 누수(Memory Leak) 대응 절차 (참고 절차)
- get_monitoring_status로 현재 메모리 사용률과 알림을 확인한다. 시간별 메모리 추세는 별도 모니터링 대시보드에서 확인하며, 단일 관측만으로 누수를 확정하지 않는다.
- 힙 덤프 또는 프로파일링 도구로 어떤 객체가 계속 쌓이는지 확인한다.

[E4] payments-service / cpu-spike — Runbook: CPU 급증 대응 절차 (참고 절차)
- get_monitoring_status로 현재 CPU 사용률과 알림을 확인한다. 최근 배포/트래픽 변화 시점은 별도 배포 기록과 트래픽 대시보드에서 확인한다.
- 반복 호출, 배치 작업 중복 실행 같은 특정 요청 패턴이 원인인지 최근 로그에서 확인한다.

원인 후보·확인 사항 (추정)
cache-service 는 메모리 사용률이 급격히 상승하고 힙이 거의 가득 차 있어 메모리 누수나 캐시 무제한 증가 등 원인이 있을 가능성이 있습니다.

## name (0.01초)

질문: 제 이름은 기준입니다

반갑습니다, 기준님. 이 대화에서 이름을 기억하겠습니다.

질문: 제 이름이 뭐였죠?

기준님이라고 알려주셨습니다.
