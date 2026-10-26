#!/usr/bin/env python3
"""MoveIt付きGazeboで、下向き睡眠姿勢・小さい揺れ・復帰を実測。"""

import json
import math
from pathlib import Path
import signal
import subprocess
import sys

from moveit_msgs.srv import GetPositionFK
import rclpy
from std_msgs.msg import Bool, Float32

from verify_activity import JOINTS, Verification

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sleep_expression import SleepExpression, sleep_pose


def main():
    rclpy.init()
    node = Verification()
    root = Path(__file__).resolve().parents[1]
    processes = []
    node.test_sleepiness = .59
    node.expression_value = False
    publisher = node.create_publisher(Float32, '/test_drowsiness', 10)
    node.create_timer(.05, lambda: publisher.publish(Float32(data=node.test_sleepiness)))
    node.create_subscription(Bool, '/expression_active',
                             lambda msg: setattr(node, 'expression_value', msg.data), 10)
    fk = node.create_client(GetPositionFK, '/compute_fk')
    try:
        node.wait_until(lambda: node.joints is not None)
        initial = dict(zip(node.joints.name, node.joints.position))
        origin = [initial[name] for name in JOINTS]
        for script, extra in [('activity_monitor.py', []), ('sleep_expression.py', [
                '-p', 'amplitude_deg:=3.0', '-p', 'period:=6.0',
                '-r', '/drowsiness:=/test_drowsiness'])]:
            processes.append(subprocess.Popen([
                sys.executable, str(root / script), '--ros-args', '-p', 'use_sim_time:=true',
                *extra]))
        node.wait_until(lambda: publisher.get_subscription_count() > 0)
        node.sample(1)
        assert not node.expression_value
        node.test_sleepiness = .6
        target = sleep_pose(origin)

        def pose_near(values):
            q = dict(zip(node.joints.name, node.joints.position))
            return max(abs(q[name] - value) for name, value in zip(JOINTS, values)) < .005

        node.wait_until(lambda: pose_near(target), timeout=60)
        node.sample(1)
        node.phase = 'sleeping'
        node.sample(9)
        rows = [r for r in node.rows if r['phase'] == 'sleeping']
        poses = [[dict(zip(r['names'], r['position']))[name] for name in JOINTS] for r in rows]
        tilt = [q[1] for q in poses]
        assert max(tilt) - min(tilt) > math.radians(4.5), (min(tilt), max(tilt))
        assert max(abs(sum(q[i] for i in (1, 3, 5)) + math.pi) for q in poses) < .01
        assert max(abs(q[3] - target[3]) for q in poses) < .005
        activity = [v for phase, v in node.activity_samples if phase == 'sleeping']
        assert activity and max(activity) < .01, activity[-5:]

        assert fk.wait_for_service(timeout_sec=5)
        orientations = []
        heights = []
        for q in (min(poses, key=lambda p: p[1]), max(poses, key=lambda p: p[1]), poses[-1]):
            request = GetPositionFK.Request()
            request.header.frame_id = 'crane_x7_mounting_plate_link'
            request.fk_link_names = ['crane_x7_gripper_base_link']
            request.robot_state = SleepExpression.robot_state(q)
            result = node.future_result(fk.call_async(request))
            assert result.error_code.val == 1
            pose = result.pose_stamped[0].pose
            orientation = pose.orientation
            # Quaternionの回転行列のzz成分 = 先端+Zと鉛直上向きとの内積。
            tip_z = 1 - 2 * (orientation.x ** 2 + orientation.y ** 2)
            assert tip_z < -.999, tip_z
            orientations.append(tip_z)
            heights.append(pose.position.z)
        assert max(heights) - min(heights) > .005, heights

        node.test_sleepiness = .2
        node.wait_until(lambda: pose_near(origin), timeout=60)
        node.sample(2)
        assert not node.expression_value
        summary = dict(all_checks_passed=True, tip_direction_z=orientations,
                       tip_height_range=[min(heights), max(heights)],
                       shoulder_range_deg=[math.degrees(min(tilt)), math.degrees(max(tilt))],
                       activity_max=max(activity), returned_to_awake_pose=True)
        (root / 'simulation/results/sleep_summary.json').write_text(
            json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2))
    finally:
        for process in reversed(processes):
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
