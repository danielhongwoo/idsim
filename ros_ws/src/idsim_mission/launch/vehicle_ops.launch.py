# Copyright 2026 Daniel Hongwoo Lee
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""기체 하나의 운용 컨테이너(ops-N). decisions.md 쟁점 2.

component_container_isolated(이름 ops_container)에 Mission Executor 컴포넌트 하나를 load한다.
전이는 노드가 스스로 건다(lifecycle.self_start). launch의 autostart는 쓰지 않는다(launch_ros
0.26.13의 컨테이너 autostart는 전이를 걸지 못한다. p3a-results.md).

인자(기본값 없음. 생성기가 넘긴다)
  namespace      기체 네임스페이스. 예: /px4_1
  executor_name  노드 이름. 생성기 상수 하나에서 나온다(stack.json의 executor_node와 같다)
  params_file    /** 키에 use_sim_time과 vehicle.* 만 있는 params 파일
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():
    namespace = LaunchConfiguration("namespace")
    executor_name = LaunchConfiguration("executor_name")
    params_file = LaunchConfiguration("params_file")
    container = ComposableNodeContainer(
        name="ops_container",
        namespace=namespace,
        package="rclcpp_components",
        executable="component_container_isolated",
        composable_node_descriptions=[
            ComposableNode(
                package="idsim_mission",
                plugin="idsim_mission::MissionExecutorNode",
                name=executor_name,
                namespace=namespace,
                parameters=[params_file],
            )
        ],
        parameters=[params_file],
        output="screen",
        on_exit=Shutdown(),
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("namespace", description="vehicle namespace, e.g. /px4_1"),
            DeclareLaunchArgument("executor_name", description="executor node name"),
            DeclareLaunchArgument("params_file", description="params file with /** keys"),
            container,
        ]
    )
