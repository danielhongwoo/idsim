# 사용: set -a; . docker/versions.env; set +a; docker buildx bake -f docker/docker-bake.hcl <타깃> --load
# 변수는 versions.env를 export한 환경변수에서 읽는다. 기본값을 두지 않는다.
variable "UBUNTU_IMAGE" {}
variable "ROS_DISTRO" {}
variable "GZ_RELEASE" {}
variable "PX4_TAG" {}
variable "PX4_MSGS_REF" {}
variable "PX4_ROS_COM_REF" {}
variable "PX4_GZ_MODELS_REF" {}
variable "XRCE_AGENT_TAG" {}
variable "REGISTRY" {}
# 레지스트리 태그의 <키>. CI가 Dockerfile과 versions.env 해시로 채운다. 로컬 기본은 local
variable "KEY" { default = "local" }

group "default" {
  targets = ["ros-base", "xrce-agent"]
}

target "_common" {
  context  = "docker"
  platforms = ["linux/amd64"]
}

target "ros-base" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.ros-base"
  args = {
    UBUNTU_IMAGE = UBUNTU_IMAGE
    ROS_DISTRO   = ROS_DISTRO
  }
  tags = ["idsim/ros-base:local", "${REGISTRY}/ros-base:${KEY}"]
}

# sim-base, px4, ros-ws는 ros-base 로컬 태그를 named context로 받는다.
# Dockerfile 쪽에서는 ARG BASE_IMAGE로 받아 FROM ${BASE_IMAGE}로 쓴다.
target "sim-base" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.sim-base"
  contexts   = { "idsim-ros-base" = "target:ros-base" }
  args = {
    BASE_IMAGE        = "idsim-ros-base"
    GZ_RELEASE        = GZ_RELEASE
    PX4_GZ_MODELS_REF = PX4_GZ_MODELS_REF
  }
  tags = ["idsim/sim-base:local", "${REGISTRY}/sim-base:${KEY}"]
}

target "px4" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.px4"
  contexts   = { "idsim-sim-base" = "target:sim-base" }
  args = {
    BASE_IMAGE        = "idsim-sim-base"
    PX4_TAG           = PX4_TAG
    PX4_GZ_MODELS_REF = PX4_GZ_MODELS_REF
  }
  tags = ["idsim/px4:local", "${REGISTRY}/px4:${KEY}"]
}

target "ros-ws" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.ros-ws"
  contexts   = { "idsim-ros-base" = "target:ros-base" }
  args = {
    BASE_IMAGE   = "idsim-ros-base"
    PX4_MSGS_REF = PX4_MSGS_REF
    PX4_ROS_COM_REF = PX4_ROS_COM_REF
  }
  tags = ["idsim/ros-ws:local", "${REGISTRY}/ros-ws:${KEY}"]
}

target "xrce-agent" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.xrce-agent"
  args = {
    UBUNTU_IMAGE   = UBUNTU_IMAGE
    XRCE_AGENT_TAG = XRCE_AGENT_TAG
  }
  tags = ["idsim/xrce-agent:local", "${REGISTRY}/xrce-agent:${KEY}"]
}
