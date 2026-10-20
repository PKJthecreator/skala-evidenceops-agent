# Before/After 14개 시나리오 (2026-10-20)

조건: 같은 모델 `qwen3.5:2b`(temperature 0, ctx 8192, predict 700, think false), 같은 질의·고정 모니터링 값·런북.
원본은 `original-baseline` 태그의 코드(UTF-8 보정만 적용). `wrong-number`는 틀린 초안을, `partial-failure`는 cache-service 조회 실패를 양쪽에 동일하게 주입했다.
원본은 런북 검색 이벤트가 없어 런북 선택은 답변 내용으로만 판단했다(표에서 `-`). 14개 소규모 실행 1회이며 일반 정확도가 아니다.

| 시나리오 | 대상 처리 (Before → After) | 런북 선택 (After, 기대) | 수치 일치 | 시간 s (B → A) |
|---|---|---|---|---|
| payments | OK → OK | cpu-spike ✓ | B: 모델이 서술 / A: 코드 출력 | 26.0 → 31.3 |
| cache | OK → OK | **없음 ✗** (기대 memory-leak, 점수 0.55 미달) | A: 코드 출력, 원인 특정 안 함 | 23.0 → 8.0 |
| disk | OK → OK | disk-full ✓ | 〃 | 19.3 → 26.6 |
| upstream | OK → OK | network-timeout, cpu-spike ✓ | 〃 | 23.2 → 39.2 |
| two-targets | auth만 조회(web-01 누락) → 둘 다 조회 | high-latency ✓ | 〃 | 21.1 → 37.4 |
| common-cause | OK → OK | memory-leak, cpu-spike ✓ | 〃 | 20.9 → 44.4 |
| alias(로그인) | OK → OK | high-latency ✓ | B: 모니터링에 없는 p95·커넥션 풀 수치 서술 / A: 조회값만 | 19.9 → 29.4 |
| unregistered | **auth-service를 임의 조회 → 미등록 안내** | - | B: 다른 서비스 수치를 답함 | 18.6 → 2.3 |
| chat | OK → OK | - | - | 3.4 → 3.3 |
| memory | OK → OK | - | - | 7.4 → 0.0 |
| clarify-resume | **auth+payments 조회 → payments만** | high-latency (기대 cpu-spike ✗, 지연 질문이라 허용 가능하나 기대와 다름) | | 37.4 → 29.3 |
| similar-runbooks | OK → OK | network-timeout ✓ | | 19.9 → 29.9 |
| wrong-number | **틀린 초안(CPU 39%)이 그대로 최종 답변 → 차단, 조회값 91%만 표시** | cpu-spike ✓ | B ✗ / A ✓ | 10.2 → 7.8 |
| partial-failure | **ValueError로 실패 → 성공한 payments 근거 + 실패 안내** | cpu-spike ✓ | | 오류 → 26.7 |

## 요약
- 개선 확인: 미등록 서비스 임의 조회 제거, 되묻기 후 이어가기에서 불필요한 조회 제거, 틀린 수치 초안 차단, 부분 실패 보존, 대상 누락(web-01) 수정.
- 응답 시간: 양쪽 모두 완료한 13개 평균 약 19.3s → 22.2s로 느려졌다(검색·검수 단계 추가). 단일 실행이라 편차가 크다.
- 부족한 점: `cache-service` 메모리 질문에서 memory-leak 런북을 찾지 못했다(최소 점수 0.55). `clarify-resume`은 cpu-spike 대신 high-latency를 선택했다. 임계값·질의 보강은 후속 과제.
