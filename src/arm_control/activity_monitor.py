#!/usr/bin/env python3
"""CRANE-X7 の /joint_states から「動いているかどうか」を 0〜1 の活動度として出すノード."""
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float32

EXPRESSION_FLAG_TIMEOUT = 0.5      # [s] 表現ノードは20 Hzでフラグを配信する
EXPRESSION_COMMAND_TIMEOUT = 0.3   # [s] 古い指令で別の動きを打ち消さない
EXPRESSION_MIN_DURATION = 0.1      # [s] 指令と実測のずれを活動と誤認しないための持続時間


def remove_command(measured, commanded):
    """同じ向きの実測速度から、指令された分だけを取り除く。"""
    if measured * commanded <= 0.0:
        return measured
    return math.copysign(max(0.0, abs(measured) - abs(commanded)), measured)


class ActivityMonitor(Node):
    def __init__(self):
        super().__init__('activity_monitor')
        self.declare_parameter('vel_threshold', 0.05)  # [rad/s] これ以上なら「動いている」
        self.declare_parameter('smoothing', 0.1)       # ローパス係数 (0〜1, 大きいほど反応が速い)

        self.activity = 0.0
        self.motion_duration = 0.0
        self.expression_active = False
        self.expression_stamp = None
        self.expression_velocity = {}
        self.expression_velocity_stamp = None
        self.prev_pos = None
        self.prev_time = None

        self.create_subscription(JointState, '/joint_states', self.on_joint_states,
                                 qos_profile_sensor_data)
        self.create_subscription(Bool, '/expression_active', self.on_expression, 10)
        self.create_subscription(JointState, '/expression_joint_velocity',
                                 self.on_expression_velocity, 10)
        self.pub = self.create_publisher(Float32, '/activity', 10)

    def seconds(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_expression(self, msg: Bool):
        self.expression_active = msg.data
        self.expression_stamp = self.seconds()
        if not msg.data:
            self.expression_velocity = {}
            self.expression_velocity_stamp = None

    def on_expression_velocity(self, msg: JointState):
        if len(msg.name) != len(msg.velocity) or not all(math.isfinite(v) for v in msg.velocity):
            return
        self.expression_velocity = dict(zip(msg.name, msg.velocity))
        self.expression_velocity_stamp = self.seconds()

    def on_joint_states(self, msg: JointState):
        now = self.seconds()
        positions = dict(zip(msg.name, msg.position))
        dt = 0.0 if self.prev_time is None else max(0.0, now - self.prev_time)

        # 角速度: velocity があればそれを使い、なければ position の差分で求める
        if msg.velocity:
            velocities = dict(zip(msg.name, msg.velocity))
        elif self.prev_pos is not None and dt > 0.0:
            velocities = {name: (value - self.prev_pos[name]) / dt
                          for name, value in positions.items() if name in self.prev_pos}
        else:
            velocities = {}
        self.prev_pos = positions
        self.prev_time = now

        # 表現が動かしている分だけを除く。別の関節や指令を超える動きは活動として残る。
        # 表現ノードが止まってフラグが途切れたら、実測値をそのまま使う。
        in_expression = (self.expression_active and self.expression_stamp is not None
                         and 0.0 <= now - self.expression_stamp < EXPRESSION_FLAG_TIMEOUT)
        command_fresh = (self.expression_velocity_stamp is not None
                         and 0.0 <= now - self.expression_velocity_stamp
                         < EXPRESSION_COMMAND_TIMEOUT)
        commands = self.expression_velocity if in_expression and command_fresh else {}
        residuals = [remove_command(value, commands.get(name, 0.0))
                     for name, value in velocities.items() if math.isfinite(value)]
        speed = math.sqrt(sum(value * value for value in residuals))

        moving = speed > self.get_parameter('vel_threshold').value
        self.motion_duration = self.motion_duration + min(dt, 0.1) if moving else 0.0
        # 表現中はfeedback待ちの数十msを活動にしない。
        if in_expression and self.motion_duration < EXPRESSION_MIN_DURATION:
            moving = False

        a = self.get_parameter('smoothing').value
        self.activity += (float(moving) - self.activity) * a

        self.pub.publish(Float32(data=self.activity))


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = ActivityMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
