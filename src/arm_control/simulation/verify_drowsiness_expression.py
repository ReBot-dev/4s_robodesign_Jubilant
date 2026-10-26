#!/usr/bin/env python3
"""Gazeboで実角度・しきい値・活動度固定を確認。眠気は専用テスト入力。"""

import json
from pathlib import Path
import signal
import subprocess
import sys

import rclpy
from std_msgs.msg import Bool, Float32

from verify_activity import JOINTS, Verification


def main():
    rclpy.init()
    node = Verification()
    node.expression_samples = []
    node.create_subscription(Bool, '/expression_active', lambda msg:
                             node.expression_samples.append((node.phase, msg.data)), 10)
    publisher = node.create_publisher(Float32, '/test_drowsiness', 10)
    node.test_sleepiness = .59
    node.create_timer(.05, lambda: publisher.publish(Float32(data=node.test_sleepiness)))
    process = None
    try:
        node.wait_until(lambda: node.joints is not None and node.description is not None)
        node.phase = 'baseline'
        node.sample(1)
        origin = dict(zip(node.joints.name, node.joints.position))
        process = subprocess.Popen([
            sys.executable, str(Path(__file__).resolve().parents[1] / 'drowsiness_expression.py'),
            '--ros-args', '-p', 'use_sim_time:=true',
            '-r', '/drowsiness:=/test_drowsiness'])
        node.phase = 'below'
        node.wait_until(lambda: publisher.get_subscription_count() > 0)
        node.sample(1)
        assert not any(value for phase, value in node.expression_samples if phase == 'below')
        node.phase = 'nodding'
        node.test_sleepiness = .6  # しきい値と等しい場合も開始。
        node.wait_until(lambda: any(value for phase, value in node.expression_samples
                                    if phase == 'nodding'))
        node.sample(9)  # 2往復以上を確認。
        rows = [row for row in node.rows if row['phase'] == 'nodding']
        tilt = [r['position'][r['names'].index(JOINTS[1])] for r in rows]
        assert max(tilt) - min(tilt) > .15, (min(tilt), max(tilt))
        assert max(abs(v - origin[JOINTS[1]]) for v in tilt) < .11
        frozen = [v for phase, v in node.activity_samples if phase == 'nodding']
        assert max(frozen) - min(frozen) < .01, (min(frozen), max(frozen))
        other_joint_drift = max(abs(r['position'][r['names'].index(name)] - origin[name])
                                for r in rows for name in JOINTS if name != JOINTS[1])
        assert other_joint_drift < .02, other_joint_drift
        node.phase = 'stopping'
        node.test_sleepiness = .2
        node.wait_until(lambda: any(not value for phase, value in node.expression_samples
                                    if phase == 'stopping'), timeout=15)
        node.phase = 'stopped'
        node.sample(2)
        assert not any(value for phase, value in node.expression_samples if phase == 'stopped')
        stopped = [r['position'][r['names'].index(JOINTS[1])]
                   for r in node.rows if r['phase'] == 'stopped']
        assert max(stopped) - min(stopped) < .01
        assert abs(stopped[-1] - origin[JOINTS[1]]) < .01
        summary = dict(tilt_min=min(tilt), tilt_max=max(tilt),
                       stopped_tilt=stopped[-1], other_joint_drift=other_joint_drift,
                       activity_range=[min(frozen), max(frozen)], all_checks_passed=True)
        output = Path(__file__).resolve().parent / 'results' / 'nod_summary.json'
        output.write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2))
    finally:
        if process is not None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
