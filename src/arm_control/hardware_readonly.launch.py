"""Standalone serial read -> activity -> drowsiness, with no motion controllers."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess,
                            IncludeLaunchDescription, RegisterEventHandler)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    scripts = Path(__file__).resolve().parent
    reader = ExecuteProcess(cmd=[
        '/usr/bin/python3', str(scripts / 'readonly_joint_states.py'),
        '--ros-args', '-p', ['source:=', LaunchConfiguration('source')],
        '-p', ['port:=', LaunchConfiguration('port')],
        '-p', ['baudrate:=', LaunchConfiguration('baudrate')],
        '-p', ['rate:=', LaunchConfiguration('rate')],
        '-p', 'use_sim_time:=false',
    ], output='both')
    return LaunchDescription([
        DeclareLaunchArgument('source', default_value='serial', choices=['serial', 'mock']),
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('baudrate', default_value='3000000'),
        DeclareLaunchArgument('rate', default_value='10.0'),
        # Includes child processes as well as the serial reader. On failure,
        # stop all nodes so stale activity cannot look like a healthy experiment.
        RegisterEventHandler(OnProcessExit(on_exit=[
            EmitEvent(event=Shutdown(reason='An observation process exited')),
        ])),
        reader,
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            str(scripts / 'hardware_observation.launch.py')),
            launch_arguments={'joint_states_topic': '/hardware_observation/joint_states'}.items()),
    ])
