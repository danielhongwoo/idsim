# 사용: set -a; . docker/versions.env; set +a; docker buildx bake -f docker/docker-bake.hcl <타깃> --load
# 변수는 versions.env를 export한 환경변수에서 읽는다. 기본값을 두지 않는다.
# UBUNTU_APT_MIRROR, UBUNTU_APT_SECURITY_MIRROR를 환경변수로 덮어쓰는 것은 build_images.py 경로에 한한다 (versions.env를 source하는 직접 bake에서는 versions.env가 이긴다).
variable "UBUNTU_IMAGE" {}
variable "UBUNTU_APT_MIRROR" {}
variable "UBUNTU_APT_SECURITY_MIRROR" {}
variable "ROS_DISTRO" {}
variable "ROS_APT_KEY_FPR" {}
variable "GZ_RELEASE" {}
variable "PX4_TAG" {}
variable "PX4_MSGS_REF" {}
variable "PX4_ROS_COM_REF" {}
variable "PX4_GZ_MODELS_REF" {}
variable "XRCE_AGENT_TAG" {}
variable "XRCE_FASTCDR_REF" {}
variable "XRCE_FASTDDS_REF" {}
variable "REGISTRY" {}
# 레지스트리 태그의 <키>. 이미지마다 다르다. tools/ci/image_keys.py --format env 가 계산한다
# (Dockerfile, 이 파일의 해당 target 블록, COPY 하는 파일, 그 이미지가 ARG로 쓰는 versions.env 줄, 베이스 키의 해시).
# 로컬 기본은 local. CI(tools/ci/build_images.py)는 --set 으로 태그를 직접 넣는다.
variable "KEY_ROS_BASE" { default = "local" }
variable "KEY_SIM_BASE" { default = "local" }
variable "KEY_PX4" { default = "local" }
variable "KEY_ROS_WS" { default = "local" }
variable "KEY_XRCE_AGENT" { default = "local" }

group "default" {
  targets = ["ros-base", "xrce-agent"]
}

target "_common" {
  context   = "docker"
  platforms = ["linux/amd64"]
}

target "ros-base" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.ros-base"
  args = {
    UBUNTU_IMAGE    = UBUNTU_IMAGE
    UBUNTU_APT_MIRROR = UBUNTU_APT_MIRROR
    UBUNTU_APT_SECURITY_MIRROR = UBUNTU_APT_SECURITY_MIRROR
    ROS_DISTRO      = ROS_DISTRO
    ROS_APT_KEY_FPR = ROS_APT_KEY_FPR
  }
  tags = ["idsim/ros-base:local", "${REGISTRY}/ros-base:${KEY_ROS_BASE}"]
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
  tags = ["idsim/sim-base:local", "${REGISTRY}/sim-base:${KEY_SIM_BASE}"]
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
  tags = ["idsim/px4:local", "${REGISTRY}/px4:${KEY_PX4}"]
}

target "ros-ws" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.ros-ws"
  contexts   = { "idsim-ros-base" = "target:ros-base" }
  args = {
    BASE_IMAGE      = "idsim-ros-base"
    PX4_MSGS_REF    = PX4_MSGS_REF
    PX4_ROS_COM_REF = PX4_ROS_COM_REF
  }
  tags = ["idsim/ros-ws:local", "${REGISTRY}/ros-ws:${KEY_ROS_WS}"]
}

target "xrce-agent" {
  inherits   = ["_common"]
  dockerfile = "Dockerfile.xrce-agent"
  args = {
    UBUNTU_IMAGE     = UBUNTU_IMAGE
    UBUNTU_APT_MIRROR = UBUNTU_APT_MIRROR
    UBUNTU_APT_SECURITY_MIRROR = UBUNTU_APT_SECURITY_MIRROR
    XRCE_AGENT_TAG   = XRCE_AGENT_TAG
    XRCE_FASTCDR_REF = XRCE_FASTCDR_REF
    XRCE_FASTDDS_REF = XRCE_FASTDDS_REF
  }
  tags = ["idsim/xrce-agent:local", "${REGISTRY}/xrce-agent:${KEY_XRCE_AGENT}"]
}
