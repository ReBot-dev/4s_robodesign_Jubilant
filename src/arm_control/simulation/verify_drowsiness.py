#!/usr/bin/env python3
"""Verify stationary growth and activity-dependent suppression in Gazebo."""

import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import rclpy
from std_msgs.msg import Float32

from verify_activity import JOINTS, Verification


def main():
    rclpy.init()
    node = Verification()
    values = []

    def receive(msg):
        values.append((node.get_clock().now().nanoseconds * 1e-9, msg.data))

    node.create_subscription(Float32, '/drowsiness', receive, 10)
    try:
        node.wait_until(lambda: node.description is not None and node.joints is not None
                        and node.activity is not None and bool(values))
        plugins = [p.text for p in ET.fromstring(node.description).findall(
            './ros2_control/hardware/plugin')]
        assert plugins and all(p == 'gz_ros2_control/GazeboSimSystem' for p in plugins), plugins
        assert node.arm.wait_for_server(timeout_sec=30)
        node.phase = 'settling'
        node.sample(3)
        node.phase = 'drowsiness_stationary'
        start_time, start_state = values[-1]
        node.sample(30)
        end_time, end_state = values[-1]
        predicted = 1.0 - (1.0 - start_state) * math.exp(-0.03 * (end_time - start_time))
        assert abs(end_state - predicted) < 0.015, (end_state, predicted)
        assert end_state > start_state, (start_state, end_state)
        assert max(v for phase, v in node.activity_samples
                   if phase == 'drowsiness_stationary') < 0.1

        node.phase = 'drowsiness_moving'
        initial = dict(zip(node.joints.name, node.joints.position))
        origin = [initial[name] for name in JOINTS]
        target = origin.copy()
        target[0] += 0.3
        motion_start_time, motion_start_state = values[-1]
        node.move([(3, target), (6, origin)])
        motion_end_time, motion_end_state = values[-1]
        peak_activity = max(v for phase, v in node.activity_samples if phase == 'drowsiness_moving')
        stationary_prediction = 1.0 - (1.0 - motion_start_state) * math.exp(
            -0.03 * (motion_end_time - motion_start_time))
        assert peak_activity > 0.9, peak_activity
        assert motion_end_state >= motion_start_state - 1e-6, (motion_start_state, motion_end_state)
        assert motion_end_state < stationary_prediction - 0.002 * (1.0 - motion_start_state), (
            motion_end_state, stationary_prediction)
        assert all(b[1] >= a[1] - 1e-6 for a, b in zip(values, values[1:]))
        assert all(0 <= value <= 1 for _, value in values)
        summary = {
            'stationary_start': start_state, 'stationary_end': end_state,
            'stationary_elapsed_sim_seconds': end_time - start_time,
            'stationary_analytic_expected': predicted,
            'activity_peak_during_motion': peak_activity,
            'external_stimulus': 'unconnected (0)',
            'drowsiness_before_motion': motion_start_state, 'drowsiness_after_motion': motion_end_state,
            'same_duration_stationary_prediction': stationary_prediction,
            'drowsiness_messages': len(values), 'all_checks_passed': True,
        }
        output = Path(__file__).resolve().parent / 'results' / 'drowsiness_summary.json'
        output.write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
