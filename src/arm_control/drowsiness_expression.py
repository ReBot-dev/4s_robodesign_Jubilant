#!/usr/bin/env python3
"""眠気がしきい値以上の間、Gazeboの肩をsin波で上下に動かす。"""

import math
import xml.etree.ElementTree as ET

from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
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
NOD_JOINT = JOINTS[1]


def make_cycle(origin, amplitude, period, lower, upper):
    """現在姿勢を中心に1往復。その他の関節は保持する。[rad, s]"""
    center = origin[1]
    if not lower <= center - amplitude <= center + amplitude <= upper:
        raise ValueError('肩の中心角度 ± 振り幅が関節可動域を超えます')
    points = []
    count = max(80, math.ceil(period * 20))
    for i in range(count + 1):
        t = period * i / count
        positions = list(origin)
        # theta = 中心角度 + 振り幅 * sin(2π * 経過時間 / 周期)
        positions[1] = center + amplitude * math.sin(2 * math.pi * t / period)
        velocities = [0.0] * len(JOINTS)
        velocities[1] = amplitude * 2 * math.pi / period * math.cos(2 * math.pi * t / period)
        # 開始・終了点では静止。間の点ではsinの速度を与える。
        if i in (0, count):
            positions[1] = center
            velocities[1] = 0.0
        ns = round((t + 0.1) * 1e9)
        points.append(JointTrajectoryPoint(
            positions=positions, velocities=velocities,
            time_from_start=Duration(sec=ns // 1_000_000_000,
                                     nanosec=ns % 1_000_000_000)))
    return points


class DrowsinessExpression(Node):
    HARDWARE_PLUGIN = 'gz_ros2_control/GazeboSimSystem'

    def __init__(self, node_name='drowsiness_expression', amplitude_deg=5.0, period=4.0):
        super().__init__(node_name)
        for name, default in [('threshold', 0.6), ('amplitude_deg', amplitude_deg), ('period', period)]:
            self.declare_parameter(name, default, ParameterDescriptor(read_only=True))
        self.threshold = self.get_parameter('threshold').value
        self.amplitude = math.radians(self.get_parameter('amplitude_deg').value)
        self.period = self.get_parameter('period').value
        if not all(math.isfinite(v) for v in (self.threshold, self.amplitude, self.period)):
            raise ValueError('パラメータは有限値にしてください')
        if not 0 <= self.threshold <= 1 or not 0 < self.amplitude <= math.radians(10):
            raise ValueError('thresholdは0〜1、amplitude_degは0より大きく10以下です')
        if not 2 <= self.period <= 60:
            raise ValueError('periodは2〜60秒です')

        self.sleepiness = 0.0
        self.sleep_stamp = None
        self.joint_stamp = None
        self.positions = None
        self.origin = None
        self.limits = None
        self.velocity_limit = None
        self.model_verified = False
        self.pending = False
        self.goal_handle = None
        self.cancel_requested = False
        self.blocked = False
        self.active = False
        self.next_start = 0.0
        self.last_tick = None
        self.expression = self.create_publisher(Bool, '/expression_active', 10)
        self.expression_velocity = self.create_publisher(
            JointState, '/expression_joint_velocity', 10)
        self.arm = ActionClient(self, FollowJointTrajectory,
                                '/crane_x7_arm_controller/follow_joint_trajectory')
        self.create_subscription(Float32, '/drowsiness', self.on_drowsiness, 10)
        self.create_subscription(JointState, '/joint_states', self.on_joints,
                                 qos_profile_sensor_data)
        self.create_subscription(String, '/robot_description', self.on_description,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_timer(0.05, self.update)

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_description(self, msg):
        try:
            root = ET.fromstring(msg.data)
            plugins = [p.text for p in root.findall('./ros2_control/hardware/plugin')]
            self.model_verified = bool(plugins) and all(
                p == self.HARDWARE_PLUGIN for p in plugins)
            limit = root.find(f"./joint[@name='{NOD_JOINT}']/limit")
            self.limits = (float(limit.attrib['lower']), float(limit.attrib['upper']))
            self.velocity_limit = float(limit.attrib['velocity'])
        except (ET.ParseError, AttributeError, KeyError, ValueError):
            self.model_verified = False
        if not self.model_verified:
            self.get_logger().error(
                f'対象モデル（{self.HARDWARE_PLUGIN}）を確認できないため動作を送信しません')

    def on_drowsiness(self, msg):
        if math.isfinite(msg.data):
            self.sleepiness = min(1.0, max(0.0, msg.data))
            self.sleep_stamp = self.now()
            if self.sleepiness < self.threshold:
                self.blocked = False

    def on_joints(self, msg):
        values = dict(zip(msg.name, msg.position))
        if all(name in values and math.isfinite(values[name]) for name in JOINTS):
            self.positions = [values[name] for name in JOINTS]
            self.joint_stamp = self.now()

    def inputs_fresh(self, now):
        return all(stamp is not None and 0 <= now - stamp < 1.0
                   for stamp in (self.sleep_stamp, self.joint_stamp))

    def update(self):
        now = self.now()
        rewound = self.last_tick is not None and now < self.last_tick
        self.last_tick = now
        if rewound:
            self.next_start = now
            self.sleep_stamp = self.joint_stamp = None
        if self.active:
            self.expression.publish(Bool(data=True))
        if (not self.inputs_fresh(now) or not self.model_verified) and self.goal_handle is not None:
            if not self.cancel_requested:
                self.cancel_requested = True
                self.goal_handle.cancel_goal_async()
        if self.pending or self.goal_handle is not None:
            return
        if now < self.next_start:
            return  # 停止直後の残留速度も活動度に含めない。
        if self.active:
            self.active = False
            self.expression.publish(Bool(data=False))
        if self.sleepiness < self.threshold:
            self.origin = None
        if (self.blocked or not self.model_verified or not self.inputs_fresh(now)
                or self.sleepiness < self.threshold or not self.arm.server_is_ready()):
            return
        try:
            if self.amplitude * 2 * math.pi / self.period > self.velocity_limit:
                raise ValueError('sin波の最大速度が関節速度上限を超えます')
            origin = self.positions if self.origin is None else self.origin
            points = make_cycle(origin, self.amplitude, self.period, *self.limits)
        except ValueError as error:
            self.get_logger().error(str(error))
            self.blocked = True
            return
        self.active = True
        self.origin = list(origin)
        self.expression.publish(Bool(data=True))
        self.pending = True
        # 活動度ノードへフラグが届く猶予を確保してから動き始める。
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = JOINTS
        goal.trajectory.points = points
        self.arm.send_goal_async(
            goal, feedback_callback=self.on_feedback).add_done_callback(self.on_goal)

    def on_feedback(self, message):
        # 活動度ノードが表現の動きだけを差し引けるよう、指令角速度を伝える。
        feedback = message.feedback
        self.expression_velocity.publish(JointState(
            name=list(feedback.joint_names), velocity=list(feedback.desired.velocities)))

    def on_goal(self, future):
        self.pending = False
        try:
            handle = future.result()
            if not handle.accepted:
                raise RuntimeError('上下動の軌道が拒否されました')
            self.goal_handle = handle
            self.cancel_requested = False
            handle.get_result_async().add_done_callback(self.on_result)
        except Exception as error:
            self.get_logger().error(str(error))
            self.blocked = True
            self.next_start = self.now() + 0.3

    def on_result(self, future):
        try:
            result = future.result()
            if (result.status != GoalStatus.STATUS_SUCCEEDED
                    or result.result.error_code != FollowJointTrajectory.Result.SUCCESSFUL):
                raise RuntimeError(f'上下動が中断されました: {result.result.error_string}')
        except Exception as error:
            self.get_logger().warning(str(error))
            # 他の操作が割り込んだら取り返さず、次のしきい値到達まで待つ。
            self.blocked = True
        self.goal_handle = None
        # 軌道は終了済み。古い指令で手動操作を打ち消さないよう、すぐ解除する。
        self.expression_velocity.publish(JointState())
        self.next_start = self.now() + 0.3


def main():
    # Ctrl+C後にもキャンセルと表現フラグ解除を配信できるようにする。
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = DrowsinessExpression()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            if node.goal_handle is not None:
                future = node.goal_handle.cancel_goal_async()
                rclpy.spin_until_future_complete(node, future, timeout_sec=1.0)
            node.expression.publish(Bool(data=False))
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
