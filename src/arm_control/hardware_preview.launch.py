"""Display measured joint angles and candidate camera geometry without motor writes."""

from pathlib import Path

from crane_x7_description.robot_description_loader import RobotDescriptionLoader
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    scripts = Path(__file__).resolve().parent
    loader = RobotDescriptionLoader()
    loader.use_d435 = 'true'
    # Only parse this model for display. No hardware component is instantiated.
    loader.use_mock_components = 'true'
    tf_remaps = [('/tf', '/hardware_observation/tf'),
                 ('/tf_static', '/hardware_observation/tf_static')]
    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('source', default_value='serial', choices=['serial', 'mock']),
        DeclareLaunchArgument('rviz', default_value='true', choices=['true', 'false']),
        LogInfo(msg='READ-ONLY PREVIEW: candidate D435 mount, not yet verified against hardware. '
                    'No control driver, MoveIt or expression node is started.'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            str(scripts / 'hardware_readonly.launch.py')),
            launch_arguments={'port': LaunchConfiguration('port'),
                              'source': LaunchConfiguration('source')}.items()),
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             name='preview_robot_state_publisher', namespace='hardware_observation',
             parameters=[{'robot_description': ParameterValue(loader.load(), value_type=str),
                          'use_sim_time': False}],
             remappings=[('/joint_states', '/hardware_observation/joint_states'), *tf_remaps],
             output='both'),
        Node(package='rviz2', executable='rviz2', name='hardware_preview_rviz',
             arguments=['-d', str(scripts / 'hardware_preview.rviz')],
             parameters=[{'use_sim_time': False}], remappings=tf_remaps,
             condition=IfCondition(LaunchConfiguration('rviz')), output='both'),
    ])
