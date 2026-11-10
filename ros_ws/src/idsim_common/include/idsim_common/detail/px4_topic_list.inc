// PX4 v1.17.0 dds_topics.yaml에 있는 토픽 65개의 기술자 목록. 이 파일이 유일한 출처다.
//
// 이 파일은 idsim_common/px4_topics.hpp만 include한다. 다른 곳에서 include하지 않는다.
// 형식: IDSIM_PX4_TOPIC(기술자 이름, px4_msgs 타입, 방향, "논리 이름", 발행 허용)
// - 논리 이름은 dds_topics.yaml의 topic에서 /fmu/in/ 또는 /fmu/out/과 _v<N> 접미사를 뗀 것이다.
//   접미사는 타입의 MESSAGE_VERSION에서 컴파일 시점에 파생한다(_v<N>을 여기에 쓰면 컴파일 오류).
// - 논리 이름과 타입 이름이 다른 항목이 있다(vehicle_gps_position은 SensorGps). 타입에서 이름을
//   만들지 않는다. 같은 타입을 여러 토픽이 쓰므로 타입 -> 이름 역조회도 없다.
// - key는 (방향, 논리 이름)이다. mode_completed는 in과 out 양쪽에 있다.
// - 골든 tests/fixtures/px4/<PX4_TAG>/topics.txt와 양방향으로 일치해야 한다(test_topics_golden).
//
// /fmu/in 발행 허용(Allowed)은 1a에서 offboard_control_mode, trajectory_setpoint,
// vehicle_command 셋뿐이다.
// 나머지 /fmu/in은 Restricted이며 공개 API(topic_name, create_publisher)로 쓸 수 없다.
// Restricted -> Allowed로 바꾸려면 한 PR 안에 다음 다섯 가지가 함께 있어야 한다.
//   (1) 아래 항목의 Restricted를 Allowed로 변경, (2) px4-engineer 접점 승인,
//   (3) docs-for-agent/progress.md 결정 기록,
//   (4) test_topics_traits의 허용 목록 기대 집합 갱신,
//   (5) docs/interface.md 공개 /fmu/in 목록 갱신.
// 이 차단은 실수 방지 수준이며 보안 경계가 아니다.
//
// /fmu/out은 idsim이 발행하지 않으므로 모두 Restricted로 둔다(구독만 가능).

// ---- /fmu/in 발행 허용 ----
IDSIM_PX4_TOPIC(OffboardControlMode, px4_msgs::msg::OffboardControlMode, In, "offboard_control_mode", Allowed)
IDSIM_PX4_TOPIC(TrajectorySetpoint, px4_msgs::msg::TrajectorySetpoint, In, "trajectory_setpoint", Allowed)
IDSIM_PX4_TOPIC(VehicleCommand, px4_msgs::msg::VehicleCommand, In, "vehicle_command", Allowed)

// ---- /fmu/in 차단: 외부 모드 프로토콜 ----
// ROS 2 Interface Library의 외부 모드 등록, arming check, 모드 실행기, 설정 덮어쓰기.
// idsim은 외부 모드를 등록하지 않는다.
IDSIM_PX4_TOPIC(ArmingCheckReply, px4_msgs::msg::ArmingCheckReply, In, "arming_check_reply", Restricted)
IDSIM_PX4_TOPIC(ConfigControlSetpoints, px4_msgs::msg::VehicleControlMode, In, "config_control_setpoints", Restricted)
IDSIM_PX4_TOPIC(ConfigOverridesRequest, px4_msgs::msg::ConfigOverrides, In, "config_overrides_request", Restricted)
IDSIM_PX4_TOPIC(MessageFormatRequest, px4_msgs::msg::MessageFormatRequest, In, "message_format_request", Restricted)
IDSIM_PX4_TOPIC(ModeCompletedIn, px4_msgs::msg::ModeCompleted, In, "mode_completed", Restricted)
IDSIM_PX4_TOPIC(RegisterExtComponentRequest, px4_msgs::msg::RegisterExtComponentRequest, In, "register_ext_component_request", Restricted)
IDSIM_PX4_TOPIC(UnregisterExtComponent, px4_msgs::msg::UnregisterExtComponent, In, "unregister_ext_component", Restricted)
IDSIM_PX4_TOPIC(VehicleCommandModeExecutor, px4_msgs::msg::VehicleCommand, In, "vehicle_command_mode_executor", Restricted)

// ---- /fmu/in 차단: 제어기 우회 ----
// 위치 제어기를 건너뛰는 자세, 각속도, 추력, 토크, 액추에이터 직접 명령.
IDSIM_PX4_TOPIC(ActuatorMotors, px4_msgs::msg::ActuatorMotors, In, "actuator_motors", Restricted)
IDSIM_PX4_TOPIC(ActuatorServos, px4_msgs::msg::ActuatorServos, In, "actuator_servos", Restricted)
IDSIM_PX4_TOPIC(LandingGear, px4_msgs::msg::LandingGear, In, "landing_gear", Restricted)
IDSIM_PX4_TOPIC(VehicleAttitudeSetpoint, px4_msgs::msg::VehicleAttitudeSetpoint, In, "vehicle_attitude_setpoint", Restricted)
IDSIM_PX4_TOPIC(VehicleRatesSetpoint, px4_msgs::msg::VehicleRatesSetpoint, In, "vehicle_rates_setpoint", Restricted)
IDSIM_PX4_TOPIC(VehicleThrustSetpoint, px4_msgs::msg::VehicleThrustSetpoint, In, "vehicle_thrust_setpoint", Restricted)
IDSIM_PX4_TOPIC(VehicleTorqueSetpoint, px4_msgs::msg::VehicleTorqueSetpoint, In, "vehicle_torque_setpoint", Restricted)

// ---- /fmu/in 차단: 보류 ----
// 위치 제어 계열이지만 1a에서 쓰지 않는다. 1b에서 공개를 검토한다.
IDSIM_PX4_TOPIC(GotoSetpoint, px4_msgs::msg::GotoSetpoint, In, "goto_setpoint", Restricted)

// ---- /fmu/in 차단: 추정기 주입 ----
// EKF2와 충돌 회피에 외부 측정값을 넣는다. SITL의 시뮬레이션 센서와 섞이면 추정이 틀어진다.
IDSIM_PX4_TOPIC(AuxGlobalPosition, px4_msgs::msg::VehicleGlobalPosition, In, "aux_global_position", Restricted)
IDSIM_PX4_TOPIC(DistanceSensor, px4_msgs::msg::DistanceSensor, In, "distance_sensor", Restricted)
IDSIM_PX4_TOPIC(ObstacleDistance, px4_msgs::msg::ObstacleDistance, In, "obstacle_distance", Restricted)
IDSIM_PX4_TOPIC(SensorOpticalFlow, px4_msgs::msg::SensorOpticalFlow, In, "sensor_optical_flow", Restricted)
IDSIM_PX4_TOPIC(VehicleMocapOdometry, px4_msgs::msg::VehicleOdometry, In, "vehicle_mocap_odometry", Restricted)
IDSIM_PX4_TOPIC(VehicleVisualOdometry, px4_msgs::msg::VehicleOdometry, In, "vehicle_visual_odometry", Restricted)

// ---- /fmu/in 차단: 수동 입력 ----
// RC 입력 위장.
IDSIM_PX4_TOPIC(ManualControlInput, px4_msgs::msg::ManualControlSetpoint, In, "manual_control_input", Restricted)

// ---- /fmu/in 차단: 상태 위장 ----
// 동반 컴퓨터와 텔레메트리 링크 상태를 PX4에 보고한다.
IDSIM_PX4_TOPIC(OnboardComputerStatus, px4_msgs::msg::OnboardComputerStatus, In, "onboard_computer_status", Restricted)
IDSIM_PX4_TOPIC(TelemetryStatus, px4_msgs::msg::TelemetryStatus, In, "telemetry_status", Restricted)

// ---- /fmu/in 차단: 기체 형식 불일치 ----
// 고정익과 로버 전용. idsim 기체는 멀티콥터다.
IDSIM_PX4_TOPIC(FixedWingLateralSetpoint, px4_msgs::msg::FixedWingLateralSetpoint, In, "fixed_wing_lateral_setpoint", Restricted)
IDSIM_PX4_TOPIC(FixedWingLongitudinalSetpoint, px4_msgs::msg::FixedWingLongitudinalSetpoint, In, "fixed_wing_longitudinal_setpoint", Restricted)
IDSIM_PX4_TOPIC(LateralControlConfiguration, px4_msgs::msg::LateralControlConfiguration, In, "lateral_control_configuration", Restricted)
IDSIM_PX4_TOPIC(LongitudinalControlConfiguration, px4_msgs::msg::LongitudinalControlConfiguration, In, "longitudinal_control_configuration", Restricted)
IDSIM_PX4_TOPIC(RoverAttitudeSetpoint, px4_msgs::msg::RoverAttitudeSetpoint, In, "rover_attitude_setpoint", Restricted)
IDSIM_PX4_TOPIC(RoverPositionSetpoint, px4_msgs::msg::RoverPositionSetpoint, In, "rover_position_setpoint", Restricted)
IDSIM_PX4_TOPIC(RoverRateSetpoint, px4_msgs::msg::RoverRateSetpoint, In, "rover_rate_setpoint", Restricted)
IDSIM_PX4_TOPIC(RoverSpeedSetpoint, px4_msgs::msg::RoverSpeedSetpoint, In, "rover_speed_setpoint", Restricted)
IDSIM_PX4_TOPIC(RoverSteeringSetpoint, px4_msgs::msg::RoverSteeringSetpoint, In, "rover_steering_setpoint", Restricted)
IDSIM_PX4_TOPIC(RoverThrottleSetpoint, px4_msgs::msg::RoverThrottleSetpoint, In, "rover_throttle_setpoint", Restricted)

// ---- /fmu/out(구독 전용) ----
IDSIM_PX4_TOPIC(AirspeedValidated, px4_msgs::msg::AirspeedValidated, Out, "airspeed_validated", Restricted)
IDSIM_PX4_TOPIC(ArmingCheckRequest, px4_msgs::msg::ArmingCheckRequest, Out, "arming_check_request", Restricted)
IDSIM_PX4_TOPIC(BatteryStatus, px4_msgs::msg::BatteryStatus, Out, "battery_status", Restricted)
IDSIM_PX4_TOPIC(CollisionConstraints, px4_msgs::msg::CollisionConstraints, Out, "collision_constraints", Restricted)
IDSIM_PX4_TOPIC(EstimatorStatusFlags, px4_msgs::msg::EstimatorStatusFlags, Out, "estimator_status_flags", Restricted)
IDSIM_PX4_TOPIC(FailsafeFlags, px4_msgs::msg::FailsafeFlags, Out, "failsafe_flags", Restricted)
IDSIM_PX4_TOPIC(GimbalDeviceAttitudeStatus, px4_msgs::msg::GimbalDeviceAttitudeStatus, Out, "gimbal_device_attitude_status", Restricted)
IDSIM_PX4_TOPIC(HomePosition, px4_msgs::msg::HomePosition, Out, "home_position", Restricted)
IDSIM_PX4_TOPIC(ManualControlSetpoint, px4_msgs::msg::ManualControlSetpoint, Out, "manual_control_setpoint", Restricted)
IDSIM_PX4_TOPIC(MessageFormatResponse, px4_msgs::msg::MessageFormatResponse, Out, "message_format_response", Restricted)
IDSIM_PX4_TOPIC(ModeCompletedOut, px4_msgs::msg::ModeCompleted, Out, "mode_completed", Restricted)
IDSIM_PX4_TOPIC(PositionSetpointTriplet, px4_msgs::msg::PositionSetpointTriplet, Out, "position_setpoint_triplet", Restricted)
IDSIM_PX4_TOPIC(RegisterExtComponentReply, px4_msgs::msg::RegisterExtComponentReply, Out, "register_ext_component_reply", Restricted)
IDSIM_PX4_TOPIC(SensorCombined, px4_msgs::msg::SensorCombined, Out, "sensor_combined", Restricted)
IDSIM_PX4_TOPIC(TimesyncStatus, px4_msgs::msg::TimesyncStatus, Out, "timesync_status", Restricted)
IDSIM_PX4_TOPIC(TransponderReport, px4_msgs::msg::TransponderReport, Out, "transponder_report", Restricted)
IDSIM_PX4_TOPIC(VehicleAttitude, px4_msgs::msg::VehicleAttitude, Out, "vehicle_attitude", Restricted)
IDSIM_PX4_TOPIC(VehicleCommandAck, px4_msgs::msg::VehicleCommandAck, Out, "vehicle_command_ack", Restricted)
IDSIM_PX4_TOPIC(VehicleControlMode, px4_msgs::msg::VehicleControlMode, Out, "vehicle_control_mode", Restricted)
IDSIM_PX4_TOPIC(VehicleGlobalPosition, px4_msgs::msg::VehicleGlobalPosition, Out, "vehicle_global_position", Restricted)
IDSIM_PX4_TOPIC(VehicleGpsPosition, px4_msgs::msg::SensorGps, Out, "vehicle_gps_position", Restricted)
IDSIM_PX4_TOPIC(VehicleLandDetected, px4_msgs::msg::VehicleLandDetected, Out, "vehicle_land_detected", Restricted)
IDSIM_PX4_TOPIC(VehicleLocalPosition, px4_msgs::msg::VehicleLocalPosition, Out, "vehicle_local_position", Restricted)
IDSIM_PX4_TOPIC(VehicleOdometry, px4_msgs::msg::VehicleOdometry, Out, "vehicle_odometry", Restricted)
IDSIM_PX4_TOPIC(VehicleStatus, px4_msgs::msg::VehicleStatus, Out, "vehicle_status", Restricted)
IDSIM_PX4_TOPIC(VtolVehicleStatus, px4_msgs::msg::VtolVehicleStatus, Out, "vtol_vehicle_status", Restricted)
IDSIM_PX4_TOPIC(Wind, px4_msgs::msg::Wind, Out, "wind", Restricted)
