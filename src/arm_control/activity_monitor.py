#!/usr/bin/env python3
"""CRANE-X7 の /joint_states から「動いているかどうか」を 0〜1 の活動度として出すノード."""
import math

import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float32


class ActivityMonitor(Node):
    def __init__(self):
        super().__init__('activity_monitor')
        self.declare_parameter('vel_threshold', 0.05)  # [rad/s] これ以上なら「動いている」
        self.declare_parameter('smoothing', 0.1)       # ローパス係数 (0〜1, 大きいほど反応が速い)

        self.activity = 0.0
        self.frozen = False          # 表現動作中は True
        self.prev_pos = None
        self.prev_time = None

        self.create_subscription(JointState, '/joint_states', self.on_joint_states, 10)
        self.create_subscription(Bool, '/expression_active', self.on_expression, 10)
        self.pub = self.create_publisher(Float32, '/activity', 10)

    def on_expression(self, msg: Bool):
        self.frozen = msg.data

    def on_joint_states(self, msg: JointState):
        now = self.get_clock().now().nanoseconds * 1e-9

        # 角速度: velocity があればそれを使い、なければ position の差分で求める
        if msg.velocity:
            vel = list(msg.velocity)
        elif self.prev_pos is not None and now > self.prev_time:
            dt = now - self.prev_time
            vel = [(p - q) / dt for p, q in zip(msg.position, self.prev_pos)]
        else:
            vel = [0.0]
        self.prev_pos = list(msg.position)
        self.prev_time = now

        if not self.frozen:
            speed = math.sqrt(sum(v * v for v in vel))
            moving = 1.0 if speed > self.get_parameter('vel_threshold').value else 0.0
            a = self.get_parameter('smoothing').value
            self.activity += (moving - self.activity) * a

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
