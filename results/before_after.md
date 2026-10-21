# Before/After 14개 시나리오 (2026-10-21 재측정)

조건: 같은 모델 `qwen3.5:2b`(temperature 0, ctx 8192, predict 700, think false), 같은 질의·고정 모니터링 값(`scenario_time` 2026-10-20T00:00Z)·런북.
Before는 Git 태그 `original-baseline`과 같은 원본 코드(`.tools/original-baseline.zip`, UTF-8 보정만 적용), After는 현재 코드다. `wrong-number`는 틀린 초안을, `partial-failure`는 cache-service 조회 실패를 양쪽에 똑같이 주입했다.
원본에는 런북 검색 이벤트가 없어 Before의 런북 선택은 비교하지 않는다. 14개 시나리오를 한 번씩 실행한 결과이며, 일반 정확도로 해석하지 않는다.
10/21 재측정은 RAG 본문을 MCP Resource로 읽도록 바꾸고 알림 표시를 추가한 뒤의 결과다. 10/20 결과와 판정은 같고 응답 시간만 달라졌다.

| 시나리오 | 조회 대상 (Before → After) | 런북 선택 (After / 기대) | 수치·사실 표시 | 시간 s (B → A) |
|---|---|---|---|---|
| payments | payments → payments | cpu-spike ✓ | B: 모델이 서술 / A: 조회값을 코드로 출력 | 34.4 → 30.9 |
| cache | cache → cache | **없음 ✗** / memory-leak (점수 0.55 미달) | A: 조회값만, 원인 판단 보류 | 26.8 → 8.6 |
| disk | log → log | disk-full ✓ | 〃 | 23.6 → 28.5 |
| upstream | gateway·payments → 같음 | network-timeout, cpu-spike ✓ | 〃 | 26.0 → 42.4 |
| two-targets | **auth만 조회(web-01 누락) → 둘 다 조회** | high-latency ✓ (web-01은 알림이 없어 보류) | 〃 | 24.7 → 44.8 |
| common-cause | payments·cache → 같음 | memory-leak, cpu-spike ✓ | 〃 | 24.5 → 51.0 |
| alias(로그인) | auth → auth | high-latency ✓ | B: 알림 수치를 모델이 서술 / A: 조회값·알림을 코드로 출력 | 23.1 → 32.6 |
| unregistered | **auth-service 임의 조회 → 미등록 안내(조회 0회)** | — | B: 다른 서비스의 수치로 답변 | 22.7 → 2.2 |
| chat | — | — | — | 3.8 → 3.0 |
| memory | — | — | — | 7.4 → 0.0 |
| clarify-resume | **auth·payments 조회 → payments만** | high-latency ✗ / cpu-spike (지연 질문이라 참고 문서로는 가능) | | 39.2 → 32.7 |
| similar-runbooks | gateway → gateway | network-timeout ✓ | | 20.3 → 31.7 |
| wrong-number | payments → payments | cpu-spike ✓ | **B: 틀린 초안 “CPU 39%”가 최종 답변 / A: 초안 2회 모두 차단, 조회값 91.0%만 표시** | 10.6 → 8.3 |
| partial-failure | **ValueError로 전체 실패 → 성공한 payments 근거 + cache 실패 안내** | cpu-spike ✓ | | 오류 → 28.5 |

## 요약

| 지표 | Before | After |
|---|---|---|
| 의도하지 않은 대상 조회 (unregistered·clarify-resume) | 2건 | 0건 |
| 언급된 대상 누락 (two-targets) | 1건 | 0건 |
| 틀린 수치 초안이 최종 답변에 노출 | 1/1 | 0/1 |
| 부분 실패 시 응답 | 오류 | 부분 응답 |
| 런북 선택이 기대와 일치 (진단 11개) | 측정 불가(검색 없음) | 9/11 |
| 평균 응답 시간 (양쪽 모두 완료한 13개) | 22.1s | 24.4s (+10%) |

- 응답 시간: 대상별 검색과 검수 단계가 추가되어 복수 대상 질문(upstream·two-targets·common-cause)이 크게 느려졌다. 미등록·이름 질문은 LLM 호출이 없어 빨라졌다. 한 번씩 실행한 결과라 편차가 크다.
- 부족한 점: 단일 `cache-service` 질문은 임베딩 점수 차이가 작아(cpu-spike 0.544, memory-leak 0.530) 최소 점수를 넘지 못했다. `clarify-resume`은 cpu-spike 대신 high-latency를 골랐다. 생성 설명이 필터에서 대부분 제거되어 “원인을 특정할 수 없음” 응답이 많다.
