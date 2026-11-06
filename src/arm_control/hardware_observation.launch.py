"""Observe existing hardware joint states; never start a driver or motion node."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, LogInfo
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    scripts = Path(__file__).resolve().parent
    # These scripts use absolute topic names, so namespace alone is insufficient.
    remaps = [
        '-r', '__ns:=/hardware_observation',
        '-r', ['/joint_states:=', LaunchConfiguration('joint_states_topic')],
        '-r', '/activity:=/hardware_observation/activity',
        '-r', '/drowsiness:=/hardware_observation/drowsiness',
        '-r', '/expression_active:=/hardware_observation/expression_active',
        '-r', '/expression_joint_velocity:=/hardware_observation/expression_joint_velocity',
    ]
    return LaunchDescription([
        DeclareLaunchArgument('joint_states_topic', default_value='/joint_states',
                              description='Existing hardware JointState topic (absolute name).'),
        LogInfo(msg='Observation only: no driver, controller, MoveIt or expression node is started. '
                    'Check joint_states reception separately; drowsiness rises even without input.'),
        *[
            ExecuteProcess(cmd=[
                '/usr/bin/python3', str(scripts / script),
                '--ros-args', '-p', 'use_sim_time:=false', *remaps,
            ], output='screen')
            for script in ('activity_monitor.py', 'drowsiness_node.py')
        ],
    ])
