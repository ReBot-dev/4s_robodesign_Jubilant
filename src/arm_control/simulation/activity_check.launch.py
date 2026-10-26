"""Gazebo CRANE-X7 + activity monitor, without MoveIt or a display."""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from crane_x7_description.robot_description_loader import RobotDescriptionLoader
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node, SetParameter


def generate_launch_description():
    gazebo_share = get_package_share_directory('crane_x7_gazebo')
    description_share = get_package_share_directory('crane_x7_description')
    loader = RobotDescriptionLoader()
    loader.use_gazebo = 'true'
    loader.gz_control_config_package = 'crane_x7_control'
    loader.gz_control_config_file_path = 'config/crane_x7_controllers.yaml'
    return LaunchDescription([
        SetParameter(name='use_sim_time', value=True),
        ExecuteProcess(
            cmd=['gz', 'sim', '-s', '-r', os.path.join(gazebo_share, 'worlds', 'table.sdf')],
            additional_env={
                'GZ_SIM_SYSTEM_PLUGIN_PATH': os.environ.get('LD_LIBRARY_PATH', ''),
                'GZ_SIM_RESOURCE_PATH': os.path.dirname(description_share),
            },
            output='screen',
        ),
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             parameters=[{'robot_description': loader.load()}]),
        Node(package='ros_gz_sim', executable='create',
             arguments=['-topic', '/robot_description', '-name', 'crane_x7', '-z', '1.015']),
        Node(package='ros_gz_bridge', executable='parameter_bridge',
             arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock']),
        Node(package='controller_manager', executable='spawner',
             arguments=['joint_state_controller']),
        Node(package='controller_manager', executable='spawner',
             arguments=['crane_x7_arm_controller']),
        Node(package='controller_manager', executable='spawner',
             arguments=['crane_x7_gripper_controller']),
        ExecuteProcess(cmd=[
            '/usr/bin/python3', str(Path(__file__).resolve().parents[1] / 'activity_monitor.py'),
            '--ros-args', '-p', 'use_sim_time:=true',
        ], output='screen'),
        ExecuteProcess(cmd=[
            '/usr/bin/python3', str(Path(__file__).resolve().parents[1] / 'drowsiness_node.py'),
            '--ros-args', '-p', 'use_sim_time:=true',
        ], output='screen'),
    ])
