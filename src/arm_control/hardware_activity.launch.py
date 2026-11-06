"""Real CRANE-X7 + MoveIt + state model; expression starts disabled."""

import grp
import os
from pathlib import Path
import stat

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
                            LogInfo, OpaqueFunction, SetEnvironmentVariable)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def check_serial_access(context):
    """Inspect permissions only; do not open the port or touch the robot."""
    port = LaunchConfiguration('port').perform(context)
    try:
        info = os.stat(port)
    except OSError as error:
        raise RuntimeError(f'実機USBポートを確認できません: {port}: {error}') from error
    if not stat.S_ISCHR(info.st_mode):
        raise RuntimeError(f'シリアルデバイスではありません: {port}')
    if not os.access(port, os.R_OK | os.W_OK):
        group = grp.getgrgid(info.st_gid).gr_name
        raise RuntimeError(
            f'{port} への読み書き権限が、この端末にありません。'
            f'この端末で newgrp {group} を実行し、ROS環境を読み込み直してください。'
            '実機ドライバは起動していません。')
    return []


def generate_launch_description():
    scripts = Path(__file__).resolve().parent
    driver = Path(get_package_share_directory('crane_x7_control')) / 'launch/crane_x7_control.launch.py'
    moveit = Path(get_package_share_directory('crane_x7_moveit_config')) / 'launch/run_move_group.launch.py'
    hardware_args = {
        'port_name': LaunchConfiguration('port'),
        'baudrate': LaunchConfiguration('baudrate'),
        'use_gazebo': 'false', 'use_mock_components': 'false', 'use_d435': 'true',
    }
    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('baudrate', default_value='3000000'),
        DeclareLaunchArgument('plot', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('camera_model_confirmed', default_value='false', choices=['true', 'false']),
        OpaqueFunction(function=check_serial_access),
        # Spawner file locks otherwise collide with other ROS domains/simulations.
        # Preserve the normal log location for troubleshooting.
        SetEnvironmentVariable('ROS_LOG_DIR', os.environ.get('ROS_LOG_DIR') or
                               str(Path.home() / '.ros/log')),
        SetEnvironmentVariable('ROS_HOME', '/tmp/crane_x7_hardware_ros'),
        LogInfo(msg='REAL HARDWARE: driver enables torque and writes position/PID at startup. '
                    'Stop the read-only launch first. Expression remains disabled until enabled.'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(driver)),
                                 launch_arguments={**hardware_args, 'control_update_rate': '50'}.items()),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(moveit)),
                                 launch_arguments=hardware_args.items()),
        *[ExecuteProcess(cmd=[
            '/usr/bin/python3', str(scripts / script),
            '--ros-args', '-p', 'use_sim_time:=false',
        ], output='both') for script in ('activity_monitor.py', 'drowsiness_node.py')],
        ExecuteProcess(cmd=[
            '/usr/bin/python3', str(scripts / 'hardware_sleep_expression.py'),
            '--ros-args', '-p', 'use_sim_time:=false',
            '-p', 'velocity_scaling:=0.03', '-p', 'acceleration_scaling:=0.02',
            '-p', 'amplitude_deg:=3.0', '-p', 'period:=6.0',
            '-p', ['camera_model_confirmed:=', LaunchConfiguration('camera_model_confirmed')],
        ], output='both'),
        ExecuteProcess(cmd=['/usr/bin/python3', str(scripts / 'simulation/activity_plot.py')],
                       condition=IfCondition(LaunchConfiguration('plot')), output='both'),
    ])
