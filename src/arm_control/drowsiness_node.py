#!/usr/bin/env python3
"""活動度 m で眠気の増加を抑えるROS 2ノード。外部刺激は未接続。"""

import math

from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32


def integrate_drowsiness(state, activity, dt, *, external_stimulus=0.0,
                        k_up=0.03, alpha=0.8, k_down=0.1):
    """dS/dt = k_up*(1-alpha*m)*(1-S) - k_down*外部刺激 を積分。"""
    m = min(max(activity, 0.0), 1.0)
    derivative = k_up * (1.0 - alpha * m) * (1.0 - state) - k_down * external_stimulus
    return min(max(state + derivative * dt, 0.0), 1.0)


class DrowsinessNode(Node):
    def __init__(self):
        super().__init__('drowsiness_node')
        self.declare_parameter('k_up', 0.03)
        self.declare_parameter('alpha', 0.8)
        self.declare_parameter('k_down', 0.1)
        self.declare_parameter('update_rate', 20.0, ParameterDescriptor(
            description='更新頻度 [Hz]。起動時に設定する。', read_only=True))
        params = [self.get_parameter(name) for name in ('k_up', 'alpha', 'k_down', 'update_rate')]
        result = self.validate_parameters(params)
        if not result.successful:
            raise ValueError(result.reason)
        self.add_on_set_parameters_callback(self.validate_parameters)

        self.drowsiness = 0.0
        self.activity = 0.0
        self.previous_update_ns = None
        self.create_subscription(Float32, '/activity', self.on_activity, 10)
        self.publisher = self.create_publisher(Float32, '/drowsiness', 10)
        self.timer = self.create_timer(1.0 / self.get_parameter('update_rate').value, self.update)
        self.get_logger().info('Activity m suppresses growth; external stimulus is unconnected (0)')

    @staticmethod
    def validate_parameters(parameters):
        for parameter in parameters:
            if parameter.name not in ('k_up', 'alpha', 'k_down', 'update_rate'):
                continue
            value = parameter.value
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                return SetParametersResult(successful=False, reason=f'{parameter.name} must be finite')
            if parameter.name == 'alpha' and not 0.0 <= value <= 1.0:
                return SetParametersResult(successful=False, reason='alpha must be in [0, 1]')
            if parameter.name in ('k_up', 'k_down') and value < 0.0:
                return SetParametersResult(successful=False, reason=f'{parameter.name} must be nonnegative')
            if parameter.name == 'update_rate' and value <= 0.0:
                return SetParametersResult(successful=False, reason='update_rate must be positive')
        return SetParametersResult(successful=True)

    def on_activity(self, msg):
        if math.isfinite(msg.data):
            self.activity = min(max(msg.data, 0.0), 1.0)
        else:
            self.get_logger().warning('Ignoring non-finite activity', throttle_duration_sec=1.0)

    def update(self):
        now_ns = self.get_clock().now().nanoseconds
        # /clock が最初に届いたとき、起動前の経過時間を積分しない。
        if self.previous_update_ns is not None and now_ns > self.previous_update_ns:
            dt = (now_ns - self.previous_update_ns) * 1e-9
            self.drowsiness = integrate_drowsiness(
                self.drowsiness, self.activity, dt,
                external_stimulus=0.0,  # 外部刺激の入力元はまだ指定しない。
                k_up=self.get_parameter('k_up').value,
                alpha=self.get_parameter('alpha').value,
                k_down=self.get_parameter('k_down').value,
            )
        # 時刻が巻き戻った場合は基準を更新し、負のdtを積分しない。
        self.previous_update_ns = now_ns
        self.publisher.publish(Float32(data=self.drowsiness))


def main():
    rclpy.init()
    node = DrowsinessNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
