#!/usr/bin/env bash
# ROS 2와 px4 underlay 환경을 읽은 뒤 명령을 실행한다.
set -e
# shellcheck disable=SC1090
. "/opt/ros/${ROS_DISTRO}/setup.bash"
# shellcheck disable=SC1091
. /opt/px4_ws/install/setup.bash
# 프로젝트 overlay가 빌드되어 있으면 함께 읽는다
if [ -f /opt/idsim/ros_ws/install/setup.bash ]; then
  # shellcheck disable=SC1091
  . /opt/idsim/ros_ws/install/setup.bash
fi
exec "$@"
