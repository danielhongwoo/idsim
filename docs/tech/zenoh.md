# Zenoh(지상 링크)

지상 링크에 쓰는 Zenoh와 그 ROS 2 bridge(`zenoh-bridge-ros2dds`)에 대해 이 저장소에서 확인한 성질이다. 구성(bridge 버전, 설정, 기동 순서, router 위치)은 정하지 않았고, 정하면 `docs/architecture.md`에 적는다. 정할 것은 `docs/roadmap.md`에 있다.

## 왜 쓰는가

기체의 DDS 버스를 기체 안에 두고 무선 구간에는 DDS discovery를 쓰지 않기 위해서다. Zenoh의 bridge는 ROS 2의 토픽, service, action을 중계하므로 계약(`ExecuteMission`, `VehicleState`, `MissionEvent`)을 다른 형식으로 다시 정의하지 않아도 되고 전달 대상을 설정으로 제한할 수 있다. 근거와 대안 비교는 `docs/architecture.md`의 "기술 스택 선정 근거"에 있다(측정하지 않은 설계 판단이다).

## 확인 수준

아래 절의 문장에는 확인 수준을 붙인다. [관찰]은 실행해서 본 것, [소스]는 소스를 읽어 확인한 것, [추론]은 본 범위를 넘어 일반화하거나 원인을 끌어낸 것, [미확인]은 보지 않은 것이다. 표시가 없는 문장은 [관찰]이다.

## 확인한 범위

- bridge: 공식 Docker 이미지 1.10.2, 비교로 1.9.0. 두 bridge를 router mode로 직접 이었다.
- 기체 쪽: ROS 2 Jazzy, `rmw_cyclonedds_cpp`(CycloneDDS 0.10.5), 저장소 `config/cyclonedds.xml`, 실제 SITL 스택 1대. 지상 쪽: 별도 DDS 도메인, CycloneDDS 기본 설정(multicast).
- 개발 호스트(Apple Silicon Mac, OrbStack) 한 대 안에서만 보았다. 무선 구간의 지연과 손실, 기체 여러 대, router를 따로 둔 구성은 보지 않았다.
- 배포물: 공식 이미지는 linux/amd64와 linux/arm64 manifest를 함께 제공한다(1.10.2에서 확인, 1.9.0은 arm64로 받아 실행만 함). GitHub 릴리스에 aarch64 Linux 바이너리가 있다(목록만 확인).

## 동작 방식

- DDS 도메인마다 bridge를 하나씩 두고 bridge끼리 Zenoh로 잇는다. bridge는 자기 도메인의 ROS 2 노드를 찾아 그 토픽, service, action을 Zenoh 쪽에 공지하고, 반대편 bridge가 같은 이름의 endpoint를 자기 도메인에 만든다.
- 노드 정보가 없는 DDS 참가자(uXRCE-DDS Agent)만 쓰는 토픽은 반대편 목록에 나오지 않았지만, 반대편에서 이름을 알고 구독하면 전달되었다. [추론] bridge는 ROS 2 노드에 묶인 endpoint만 공지한다.
- 전달 대상은 bridge 설정의 allow(토픽 발행과 구독, service, action을 방향별로)로 제한한다. 제한이 없으면 기체 쪽의 PX4 토픽, lifecycle과 parameter service, `/clock`이 지상에서 보이고, 지상에서 발행한 토픽이 기체 쪽에 생긴다.
- bridge 안의 DDS 구현은 CycloneDDS이고 `CYCLONEDDS_URI` 설정을 따른다. 들어 있는 판은 1.9.0이 0.11.0, 1.10.2가 11.0.1이다(bridge가 광고하는 vendor 문자열).
- `ROS_DISTRO`가 없으면 bridge는 iron으로 가정한다는 경고를 낸다. 그 상태에서도 본 범위의 동작은 같았다.

## 확인된 성질

- 계약 전달: `ExecuteMission`의 goal, feedback, result, cancel이 지상에서 동작한다. `VehicleState`(임시 발행자로만 봄)와 `MissionEvent`는 타입 이름, type hash, reliability, durability가 원래 발행자와 같게 전달된다. 메시지의 stamp는 기체 쪽 시각 그대로다.
- allow로 기체에서 지상 방향의 전달을 계약 셋으로 제한할 수 있다.
- `/clock`은 allow에 넣어야 전달된다. 넣지 않으면 지상의 `use_sim_time` true 노드는 시계가 0에 머문다.
- 지상에 먼저 떠 있는 구독자가 있으면 그 토픽의 사건을 빠짐없이 받았다.

## 알려진 한계

계약이나 구성을 정할 때 고려해야 하는 성질이다. 대응은 정하지 않았다.

- discovery와 bridge의 DDS 설정: [소스] bridge 1.10.2에 든 CycloneDDS 11.0.1은 선택된 network interface 밖으로 들어온 참가자 알림(SPDP)을 버린다. 노드 쪽의 0.10.5에는 이 검사가 없다. 노드와 같은 저장소 설정(unicast peer 127.0.0.1, interface 자동 선택)을 bridge에 주면 bridge보다 늦게 뜬 노드와 서로 찾지 못했고, 먼저 떠 있던 노드는 찾았다. [추론] 늦게 뜬 노드의 알림이 loopback으로 들어와 버려진다. bridge 전용 설정의 interface 목록에 loopback을 넣거나 1.9.0을 쓰면 순서와 상관없이 찾았다. 재시작한 Executor는 약 30 s 뒤에 다시 찾았다(이유는 [미확인]). 1.10.0과 1.10.1은 보지 않았다.
- action route가 다시 만들어진 뒤의 중복 요청: 기체 쪽 bridge가 살아 있는 동안 그 action의 route가 지워졌다가 다시 만들어지면(action server 재시작, 또는 server가 없는 동안 지상 client가 공지되었다 물러난 뒤 server가 뜸), 그 뒤의 service 요청(send_goal, get_result)이 같은 요청 id로 두 번 전달되었다(1.10.2. 1.9.0은 같은 결과로 끝난 것만 봄). route가 한 번만 만들어지면 기동 순서와 상관없이 정상이었다. [소스] `handle_goal`이 수락을 돌려주는 rclcpp_action server는 같은 goal id를 두 번 받으면 노드 코드가 잡을 수 없는 위치에서 예외를 던지고, 지금의 Executor는 프로세스가 끝났다. 중복된 cancel과 get_result에는 중복 자체로 예외를 던지는 경로가 없다([소스], cancel의 중복 전달은 [미확인]). 이때 지상이 같은 goal의 접수 사건을 두 번 받은 경우가 있었다. 관련 upstream issue(#702, #703)와 수정 PR(#705)이 열려 있고 이것으로 고쳐지는지는 [미확인].
- 늦게 생긴 구독: 지상에서 새로 만든 구독을 기체 쪽 bridge가 알기 전에 나간 사건은 오지 않았다. 구독을 action client보다 먼저 같은 노드에서 만들어도 goal 직후의 사건이 빠졌다. [추론] 반대편 bridge가 새 구독을 알기까지 걸리는 시간이 goal 왕복보다 길고, action 경로는 이 공지를 기다리지 않는다. VOLATILE에서만 보았다.
- bridge 재시작: bridge 프로세스를 멈췄다 다시 띄우면 이후의 토픽과 feedback은 다시 오지만 멈춘 동안의 것은 오지 않는다. 멈추기 전에 기다리던 result 요청은 답을 받지 못했고, action client는 이를 따로 알리지 않았다.
- action 내부 토픽(`_action/feedback`, `_action/status`)은 반대편 bridge가 광고하는 type hash가 원래와 다르다. 동작에는 영향이 없었고 원인은 [미확인].
- 같은 이름의 노드가 겹쳐 떴다 사라지면 bridge가 새 노드의 구독 route까지 거두었다.
- 1.10.2는 CycloneDDS trace의 `trace` 범주를 켜면 시작 직후 SIGSEGV로 끝난다.

## 확인하지 못한 것

- bridge는 살아 있고 둘 사이의 링크만 끊겼다 이어지는 경우.
- allow를 둔 조건에서 지상에서 기체 방향의 발행, service 호출, `/fmu/in/*`. 한쪽에만 allow를 둔 조합.
- 단절 중과 재연결 뒤의 cancel, 재연결 뒤 result 재조회.
- goal 실행 중에 지상 client 프로세스만 다시 떠도 action route가 다시 만들어지는지(비행 중 중복 요청이 생기는 경로가 있는지).
- loopback만 넣은 bridge 설정에서 action과 토픽 전달, 다른 호스트의 참가자와 잇는 것.
- 긴 미션에서의 사건 유실, 300 s보다 긴 action(bridge의 get_result 대기 기본값이 300 s).
