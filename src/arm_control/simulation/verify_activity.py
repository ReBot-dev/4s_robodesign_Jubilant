#!/usr/bin/env python3
"""Exercise the Gazebo arm and save measured joint states/activity as evidence."""

import csv
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from controller_manager_msgs.srv import ListHardwareComponents
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float32, String
from trajectory_msgs.msg import JointTrajectoryPoint


JOINTS = [
    'crane_x7_shoulder_fixed_part_pan_joint',
    'crane_x7_shoulder_revolute_part_tilt_joint',
    'crane_x7_upper_arm_revolute_part_twist_joint',
    'crane_x7_upper_arm_revolute_part_rotate_joint',
    'crane_x7_lower_arm_fixed_part_joint',
    'crane_x7_lower_arm_revolute_part_joint',
    'crane_x7_wrist_joint',
]


class Verification(Node):
    def __init__(self):
        super().__init__('verify_activity')
        self.phase = 'startup'
        self.joints = None
        self.activity = None
        self.rows = []
        self.activity_samples = []
        self.actions = []
        self.description = None
        self.create_subscription(String, '/robot_description', self.on_description,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_subscription(JointState, '/joint_states', self.on_joints,
                                 qos_profile_sensor_data)
        self.create_subscription(Float32, '/activity', self.on_activity, 10)
        self.expression = self.create_publisher(Bool, '/expression_active', 10)
        self.arm = ActionClient(self, FollowJointTrajectory,
                                '/crane_x7_arm_controller/follow_joint_trajectory')

    def on_description(self, msg):
        self.description = msg.data

    def on_activity(self, msg):
        self.activity = msg.data
        self.activity_samples.append((self.phase, msg.data))

    def on_joints(self, msg):
        self.joints = msg
        self.rows.append({
            'phase': self.phase,
            'stamp': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            'speed_norm': math.sqrt(sum(v * v for v in msg.velocity)),
            'activity': self.activity,
            'names': list(msg.name),
            'position': list(msg.position),
            'velocity': list(msg.velocity),
            'effort': list(msg.effort),
        })

    def wait_until(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError(f'Timeout during {self.phase}')
            rclpy.spin_once(self, timeout_sec=0.02)

    def sample(self, seconds):
        start = self.get_clock().now().nanoseconds
        self.wait_until(lambda: (self.get_clock().now().nanoseconds - start) * 1e-9 >= seconds,
                        timeout=max(30, seconds * 5))

    def future_result(self, future, timeout=30):
        self.wait_until(future.done, timeout)
        return future.result()

    def move(self, positions):
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = JOINTS
        for seconds, target in positions:
            goal.trajectory.points.append(JointTrajectoryPoint(
                positions=target, time_from_start=Duration(sec=seconds)))
        handle = self.future_result(self.arm.send_goal_async(goal))
        if not handle.accepted:
            raise RuntimeError('Trajectory rejected')
        result = self.future_result(handle.get_result_async())
        self.actions.append({'phase': self.phase, 'status': result.status,
                             'error_code': result.result.error_code})
        assert result.status == GoalStatus.STATUS_SUCCEEDED, result.result
        assert result.result.error_code == 0, result.result

    def run(self):
        # Do not send trajectories unless the connected hardware is Gazebo.
        hardware = self.create_client(ListHardwareComponents,
                                      '/controller_manager/list_hardware_components')
        if not hardware.wait_for_service(timeout_sec=30):
            raise TimeoutError('controller_manager is unavailable')
        components = self.future_result(hardware.call_async(ListHardwareComponents.Request()))
        # gz_ros2_control on this installation leaves plugin_name empty in the
        # service response. Also verify the actual published robot description.
        self.wait_until(lambda: self.description is not None)
        plugins = [p.text for p in ET.fromstring(self.description).findall(
            './ros2_control/hardware/plugin')]
        assert plugins and all(p == 'gz_ros2_control/GazeboSimSystem' for p in plugins), plugins
        reported = [c.plugin_name or c.class_type for c in components.component]
        assert components.component and all(not p or p in plugins for p in reported), reported
        assert self.arm.wait_for_server(timeout_sec=30), 'Arm action is unavailable'
        self.wait_until(lambda: self.joints is not None and self.activity is not None)
        self.expression.publish(Bool(data=False))
        self.phase = 'stationary'
        self.sample(3)
        initial = dict(zip(self.joints.name, self.joints.position))
        origin = [initial[name] for name in JOINTS]
        target = origin.copy()
        target[0] += 0.3
        self.phase = 'moving'
        self.move([(3, target), (6, origin)])
        self.phase = 'stopped'
        self.sample(3)
        self.expression.publish(Bool(data=True))
        self.sample(0.2)
        self.phase = 'during_expression'
        self.move([(3, target), (6, origin)])
        self.expression.publish(Bool(data=False))
        self.phase = 'released'
        self.sample(3)

        summary = {'hardware_plugins': plugins, 'actions': self.actions, 'phases': {}}
        for phase in ('stationary', 'moving', 'stopped', 'during_expression', 'released'):
            rows = [r for r in self.rows if r['phase'] == phase]
            values = [value for label, value in self.activity_samples if label == phase]
            assert rows and values, f'Missing data in {phase}'
            elapsed = rows[-1]['stamp'] - rows[0]['stamp']
            summary['phases'][phase] = {
                'joint_messages': len(rows),
                'joint_state_hz_sim_time': (len(rows) - 1) / elapsed,
                'activity_min': min(values), 'activity_max': max(values),
                'activity_final': values[-1],
                'speed_norm_max': max(r['speed_norm'] for r in rows),
                'pan_position_range': max(r['position'][r['names'].index(JOINTS[0])]
                                          for r in rows) - min(
                    r['position'][r['names'].index(JOINTS[0])] for r in rows),
            }
        summary['joint_state_example'] = self.rows[-1]
        phases = summary['phases']
        summary['checks'] = {
            'stationary_activity_low': phases['stationary']['activity_final'] < 0.1,
            'moving_activity_high': phases['moving']['activity_max'] > 0.9,
            'arm_really_moved': phases['moving']['pan_position_range'] > 0.25,
            'stopped_activity_decays': phases['stopped']['activity_final'] < 0.1,
            'expression_arm_really_moved': phases['during_expression']['pan_position_range'] > 0.25,
            'activity_counts_during_expression': phases['during_expression']['activity_max'] > 0.9,
        }
        output = Path(__file__).resolve().parent / 'results'
        output.mkdir(exist_ok=True)
        (output / 'activity_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        with (output / 'activity_samples.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=self.rows[0].keys())
            writer.writeheader()
            for row in self.rows:
                writer.writerow({k: json.dumps(v) if isinstance(v, list) else v
                                 for k, v in row.items()})
        print(json.dumps(summary, indent=2), flush=True)
        assert all(summary['checks'].values()), summary['checks']


def main():
    rclpy.init()
    node = Verification()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.expression.publish(Bool(data=False))
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
