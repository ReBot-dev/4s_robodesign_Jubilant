#!/usr/bin/env python3
"""Publish measured arm states, or explicitly selected synthetic test states."""

import math
import time

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32

from readonly_dynamixel import JOINT_NAMES, ReadOnlyArm


class ReadOnlyJointStates(Node):
    def __init__(self):
        super().__init__('readonly_joint_states', namespace='/hardware_observation')
        self.arm = None
        self.latest = {}
        for name, value in [('source', 'serial'), ('port', '/dev/ttyUSB0'),
                            ('baudrate', 3000000), ('rate', 10.0)]:
            self.declare_parameter(name, value, ParameterDescriptor(read_only=True))
        source = self.get_parameter('source').value
        rate = self.get_parameter('rate').value
        if source not in ('serial', 'mock') or not math.isfinite(rate) or not 0 < rate <= 50:
            raise ValueError('source must be serial/mock; rate must be in (0, 50] Hz')
        self.mock = source == 'mock'
        self.publisher = self.create_publisher(JointState, 'joint_states', qos_profile_sensor_data)
        for topic in ('activity', 'drowsiness'):
            self.create_subscription(Float32, topic,
                                     lambda msg, t=topic: self.receive(t, msg), 10)
        self.start = time.monotonic()
        self.next_report = self.start
        self.timer = self.create_timer(1.0 / rate, self.update)

    def connect(self):
        if self.mock:
            self.get_logger().warning('MOCK: synthetic input; no serial device is opened')
        else:
            self.get_logger().info(
                f'Opening read-only serial connection: {self.get_parameter("port").value}, '
                f'{self.get_parameter("baudrate").value} bps')
            self.arm = ReadOnlyArm(self.get_parameter('port').value,
                                   self.get_parameter('baudrate').value)
            self.get_logger().info(f'READ ONLY: IDs 2..8; existing torque enabled: '
                                   f'{self.arm.torque_enabled}. Torque is unchanged.')

    def receive(self, topic, msg):
        self.latest[topic] = (msg.data, time.monotonic())

    def update(self):
        now = time.monotonic()
        if self.mock:
            # Ten-second phases: stationary -> moving -> stationary.
            elapsed = now - self.start
            moving = 10 <= elapsed % 30 < 20
            phase = elapsed % 30 - 10
            positions = [0.2 * math.sin(math.tau * phase / 10) if moving else 0.0] + [0.0] * 6
            velocities = [0.2 * math.tau / 10 * math.cos(math.tau * phase / 10)
                          if moving else 0.0] + [0.0] * 6
        else:
            # Exceptions terminate this process and trigger launch-wide shutdown.
            positions, velocities = self.arm.read()
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = list(JOINT_NAMES)
        msg.position = positions
        msg.velocity = velocities
        self.publisher.publish(msg)
        if now >= self.next_report:
            values = []
            for topic in ('activity', 'drowsiness'):
                sample = self.latest.get(topic)
                values.append(f'{topic}=' + ('waiting' if sample is None else
                              f'{sample[0]:.3f}' if now - sample[1] < 1.0 else 'STALE'))
            angles = ', '.join(f'{math.degrees(p):.1f}' for p in positions)
            self.get_logger().info(f'{"MOCK" if self.mock else "SERIAL"} '
                                   f'angles[deg]=[{angles}] ' + ' '.join(values))
            self.next_report = now + 1.0


def main():
    rclpy.init()
    node = None
    try:
        node = ReadOnlyJointStates()
        node.connect()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        if node is not None:
            node.get_logger().error(f'Read-only observation failed: {type(error).__name__}: {error}')
        raise
    finally:
        if node is not None:
            if node.arm is not None:
                node.arm.close()
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
