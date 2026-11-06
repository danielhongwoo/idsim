# idsim 작업 규칙

idsim은 Interceptor Drone Simulator의 약자다. 설계와 로드맵은 docs/roadmap-architecture.md를 따른다.

## 문자 집합 규칙

- 저장소의 모든 텍스트 파일(문서, 소스 코드, 주석, 설정, 스크립트, 커밋 메시지)에는 완성형 한글(가-힣)과 아스키 문자만 쓴다.
- 그 외 유니코드 문자는 금지한다. 자주 섞여 들어오는 것: 가운뎃점, 화살표, 긴 줄표와 짧은 줄표, 곱셈 기호, 말줄임표, 전각 괄호와 따옴표, 이모지.
- 대체 표기
  - 가운뎃점으로 나열하던 것은 쉼표 "A, B" 또는 빗금 "A/B"로 쓴다.
  - 화살표는 "->", 양방향은 "<->"로 쓴다.
  - 긴 줄표와 짧은 줄표는 "-"로 쓴다. 범위는 "1-3"처럼 쓴다.
  - 곱셈과 개수는 "x N"으로, 말줄임표는 "..."로 쓴다.
- 검사 명령. 결과가 비어 있어야 한다.

```
grep -rnP '[^\x00-\x7F\x{AC00}-\x{D7A3}]' --exclude-dir=.git .
```

- 문서는 한국어로 쓴다. 기술 용어, 식별자, 명령어, 경로는 영문 아스키 그대로 둔다.

## 문서 구조 규칙

- `docs/architecture.md`: 목표와 범위, 레이어 구조, 기술 스택, 실행 환경, 테스트 전략. 설계가 바뀌면 여기를 고친다.
- `docs/roadmap.md`: Phase별 작업 항목, 완료 기준, 리스크, 확장 방향. 소요 시간 예상은 적지 않는다.
- `docs-for-agent/progress.md`: 진행 상황, 결정 기록, 미해결 사항, 다음 작업. 세션을 시작할 때 먼저 읽고, 작업 단위가 끝나면 갱신한다.
- 진행 상황("완료", "진행 중", "다음 작업" 같은 상태 정보)은 `docs/` 아래 문서에 적지 않는다. `docs/`는 설계와 계획만 담는다.

## 담당자 에이전트

`.claude/agents/`에 아홉 명을 정의한다. 각자 소유 영역이 있고, 접점에서 서로 검토한다.

| 이름 | 역할 | 소유 영역 |
| --- | --- | --- |
| architect | 레이어 경계, 인터페이스 계약, 식별 규칙의 최종 결정. 토론 주재와 결정 기록 | `docs/architecture.md`, `docs/interface.md`, `idsim_interfaces`, `proto/` 스키마 |
| px4-engineer | SITL, Offboard 절차, 파라미터, px4_msgs 버전, ULog | `Dockerfile.px4`, SITL 파라미터, `idsim_mission`의 PX4 접점 |
| ros2-engineer | CycloneDDS, QoS, 네임스페이스, 좌표 변환, 토픽 매핑, 노드 구조 | `idsim_common`, `config/cyclonedds.xml` |
| sim-engineer | Gazebo 월드, 표적 Actor, 브리지, 표적 어댑터, 성능 | `idsim_sim`, `Dockerfile.sim-base` |
| ops-service-engineer | Fleet Manager, 수집기, gRPC, proto 변환, Rust 게이트웨이 | `idsim_fleet`, `idsim_telemetry`, `proto/` 구현, `gateway/` |
| logging-engineer | rosbag2 정책, MCAP, ULog 정렬, replay 프로필, 인덱스 CLI | `idsim_logger`, `replay` 프로필 |
| devops-engineer | 이미지 레이어, versions.env, compose 생성, healthcheck, GitHub Actions | `docker/`, `config/fleet.yaml`, `tools/gen_compose.py`, `.github/` |
| test-engineer | 세 층의 테스트 전략, fixture, 판정 코드, 플래키 대응 | `tests/`, 각 패키지 `test/` |
| reviewer | 소유 영역 없음. 규칙과 원칙 준수, 가정의 근거만 검토. 읽기 전용 | 없음 |

소통 방식 세 가지.

- 설계 토론: 질문을 관련 담당자 둘셋에게 동시에 보내 답을 받고, architect가 충돌 지점을 짚어 재질문한 뒤 결정한다. reviewer가 근거를 검증하고, 결과는 `docs-for-agent/progress.md` 결정 기록에 남긴다.
- 구현: 담당자가 소유 영역을 구현하고, 접점 담당자와 reviewer가 검토한다. 접점 담당자의 승인 없이 머지하지 않는다.
- 장애 분석: 증상을 가진 담당자가 가설을 내고, 접점 담당자가 각자 영역에서 반증 실험을 돌린 뒤 결과를 모은다.

사용자만 정할 수 있는 사항(범위, 언어 선택, 비용)은 담당자가 결정하지 않고 `docs-for-agent/progress.md`의 미해결 사항에 올린다.
