"""Start the GUI simulation, activity monitor and plot in one isolated session."""

import atexit
import fcntl
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, EmitEvent, ExecuteProcess, IncludeLaunchDescription,
    LogInfo, SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


_session_lock = None


def generate_launch_description():
    global _session_lock
    _session_lock = open('/tmp/crane_x7_manual_activity.lock', 'a')
    try:
        fcntl.flock(_session_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _session_lock.close()
        _session_lock = None
        return LaunchDescription([
            LogInfo(msg='シミュレーションは既に起動中です。開いているGazebo・RViz・グラフを使用してください。'
                    '再起動する場合は、元の起動端末でCtrl+Cを押してから実行してください。'),
            EmitEvent(event=Shutdown(reason='Manual simulation already running')),
        ])
    # Launch may release the temporary module used to load this file. Keep a
    # strong reference to the open descriptor until the launch process exits.
    atexit.register(_session_lock.close)
    gazebo_launch = Path(get_package_share_directory('crane_x7_gazebo')) / 'launch'
    monitor = Path(__file__).resolve().parents[1] / 'activity_monitor.py'
    return LaunchDescription([
        DeclareLaunchArgument('plot', default_value='true'),
        DeclareLaunchArgument('nod', default_value='true'),
        DeclareLaunchArgument('nod_threshold', default_value='0.6'),
        DeclareLaunchArgument('nod_amplitude_deg', default_value='3.0'),
        DeclareLaunchArgument('nod_period', default_value='6.0'),
        # An already-running Gazebo server can otherwise receive the spawn
        # request while its ros2_control plugin is on a different ROS domain.
        SetEnvironmentVariable('ROS_DOMAIN_ID', '87'),
        SetEnvironmentVariable('GZ_PARTITION', f'crane_x7_manual_activity_{os.getpid()}'),
        # Spawner locks are shared even across ROS domains. Isolate these too.
        SetEnvironmentVariable('ROS_HOME', '/tmp/crane_x7_manual_ros'),
        SetEnvironmentVariable('ROS_LOG_DIR', '/tmp/crane_x7_manual_ros/log'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            str(gazebo_launch / 'crane_x7_with_table.launch.py'))),
        ExecuteProcess(cmd=[
            '/usr/bin/python3', str(monitor),
            '--ros-args', '-p', 'use_sim_time:=true',
        ], output='screen'),
        ExecuteProcess(cmd=[
            '/usr/bin/python3', str(monitor.with_name('drowsiness_node.py')),
            '--ros-args', '-p', 'use_sim_time:=true',
        ], output='screen'),
        ExecuteProcess(cmd=[
            '/usr/bin/python3', str(Path(__file__).resolve().parent / 'activity_plot.py'),
        ], condition=IfCondition(LaunchConfiguration('plot')), output='screen'),
        ExecuteProcess(cmd=[
            '/usr/bin/python3', str(monitor.with_name('sleep_expression.py')),
            '--ros-args', '-p', 'use_sim_time:=true',
            '-p', ['threshold:=', LaunchConfiguration('nod_threshold')],
            '-p', ['amplitude_deg:=', LaunchConfiguration('nod_amplitude_deg')],
            '-p', ['period:=', LaunchConfiguration('nod_period')],
        ], condition=IfCondition(LaunchConfiguration('nod')), output='screen'),
    ])
