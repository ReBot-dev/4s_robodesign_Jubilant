"""Hardware gating and trajectory checks without ROS startup or robot access."""

import copy
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from builtin_interfaces.msg import Duration
from std_msgs.msg import String
from std_srvs.srv import SetBool
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from drowsiness_expression import DrowsinessExpression, JOINTS
from hardware_sleep_expression import (HardwareSleepExpression, floor_scene,
                                       hardware_sleep_cycle, start_state_issues,
                                       validate_hardware_trajectory)
from sleep_expression import sleep_cycle, sleep_pose


class HardwareGuardTest(unittest.TestCase):
    def node(self):
        return SimpleNamespace(
            enabled=False, model_verified=True, floor_ready=True, now=lambda: 10., sleep_stamp=10.,
            joint_stamp=10., pending=False, goal_handle=None, cancel_requested=False,
            arm=Mock(), planner=Mock(), validity=Mock(), blocked=False,
            get_parameter=lambda name: SimpleNamespace(value=True),
            positions=[0.] * 7, bounds=[(-2., 2., 1.)] * 7,
        )

    def test_mount_unknown_never_enables(self):
        node = self.node()
        node.get_parameter = lambda name: SimpleNamespace(value=False)
        response = HardwareSleepExpression.on_enable(node, SetBool.Request(data=True), SetBool.Response())
        self.assertFalse(response.success)
        self.assertFalse(node.enabled)

    def test_enable_requires_hardware_fresh_inputs_and_servers(self):
        for unavailable in ('model_verified', 'floor_ready', 'fresh', 'server', 'pending'):
            node = self.node()
            if unavailable == 'fresh':
                node.joint_stamp = 8.
            elif unavailable == 'server':
                node.planner.service_is_ready.return_value = False
            elif unavailable == 'pending':
                node.pending = True
            else:
                setattr(node, unavailable, False)
            response = HardwareSleepExpression.on_enable(node, SetBool.Request(data=True), SetBool.Response())
            self.assertFalse(response.success)
            self.assertFalse(node.enabled)
        node = self.node()
        self.assertTrue(HardwareSleepExpression.on_enable(
            node, SetBool.Request(data=True), SetBool.Response()).success)
        self.assertTrue(node.enabled)

    def test_stop_requests_cancellation(self):
        node = self.node()
        node.enabled = True
        node.goal_handle = Mock()
        response = HardwareSleepExpression.on_enable(node, SetBool.Request(data=False), SetBool.Response())
        self.assertTrue(response.success)
        self.assertFalse(node.enabled)
        node.goal_handle.cancel_goal_async.assert_called_once()

    def test_measured_out_of_bounds_is_rejected_before_enable(self):
        node = self.node()
        node.positions[1] = 1.60915
        node.bounds[1] = (-1.6057, 1.6057, 1.)
        response = HardwareSleepExpression.on_enable(node, SetBool.Request(data=True), SetBool.Response())
        self.assertFalse(response.success)
        self.assertFalse(node.enabled)
        self.assertIn('92.198', response.message)
        self.assertEqual(node.positions[1], 1.60915)

    def test_failure_stays_disabled_when_drowsiness_callback_clears_block(self):
        node = HardwareSleepExpression.__new__(HardwareSleepExpression)
        node.__dict__.update(vars(self.node()))
        node.enabled = True
        node.threshold = 0.6
        node.get_logger = Mock()
        HardwareSleepExpression.fail(node, RuntimeError('plan failed'))
        self.assertFalse(node.enabled)
        self.assertTrue(node.blocked)
        from std_msgs.msg import Float32
        DrowsinessExpression.on_drowsiness(node, Float32(data=0.1))
        self.assertFalse(node.blocked)
        self.assertFalse(node.enabled)

    def test_start_state_diagnostics_preserve_measurements(self):
        node = self.node()
        self.assertEqual(start_state_issues(node.positions, node.bounds), [])
        self.assertTrue(start_state_issues(None, node.bounds))
        node.positions[1] = float('nan')
        self.assertIn(JOINTS[1], start_state_issues(node.positions, node.bounds)[0])

    def test_simulator_entry_point_still_rejects_real_model(self):
        for entry_point in (DrowsinessExpression, HardwareSleepExpression):
            for plugin in ('gz_ros2_control/GazeboSimSystem',
                           'crane_x7_hardware/CraneX7Hardware', 'mock_components/GenericSystem'):
                node = SimpleNamespace(HARDWARE_PLUGIN=entry_point.HARDWARE_PLUGIN, get_logger=Mock())
                xml = f'<robot><ros2_control><hardware><plugin>{plugin}</plugin></hardware></ros2_control>'
                xml += f'<joint name="{JOINTS[1]}"><limit lower="-2" upper="2" velocity="1"/></joint></robot>'
                DrowsinessExpression.on_description(node, String(data=xml))
                self.assertEqual(node.model_verified, plugin == entry_point.HARDWARE_PLUGIN)


class HardwareTrajectoryTest(unittest.TestCase):
    def measured_sleep_pose(self):
        return [-0.007669903939428206, 0.16873788666742054, 0.0015339807878856412,
                -2.1751847572218392, -0.0015339807878856412, -1.2241166687327416,
                0.006135923151542565]

    def test_measured_elbow_offset_starts_continuously_without_moving_center(self):
        current = self.measured_sleep_pose()
        center = sleep_pose(current)
        original_center = list(center)
        bounds = [(-math.pi, math.pi, 1.)] * 7
        old = JointTrajectory(joint_names=JOINTS,
                              points=sleep_cycle(center, math.radians(3), 6., bounds))
        with self.assertRaisesRegex(ValueError, JOINTS[3]):
            validate_hardware_trajectory(old, current, bounds)
        points = hardware_sleep_cycle(current, center, math.radians(3), 6., bounds)
        trajectory = JointTrajectory(joint_names=JOINTS, points=points)
        validate_hardware_trajectory(trajectory, current, bounds)
        for measured, first in zip(current, points[0].positions):
            self.assertAlmostEqual(first, measured)
        self.assertEqual(list(points[0].velocities), [0.] * 7)
        self.assertEqual(list(points[-1].velocities), [0.] * 7)
        self.assertEqual(list(points[-1].positions), center)
        self.assertEqual(center, original_center)
        nominal = sleep_cycle(center, math.radians(3), 6., bounds)
        for corrected, reference in zip(points[60:], nominal[60:]):
            self.assertEqual(list(corrected.positions), list(reference.positions))
            self.assertEqual(list(corrected.velocities), list(reference.velocities))

    def test_large_tracking_error_does_not_get_blended(self):
        current = [0.] * 7
        current[3] = math.radians(-6)
        with self.assertRaisesRegex(ValueError, '5°'):
            hardware_sleep_cycle(current, [0.] * 7, math.radians(3), 6.,
                                 [(-math.pi, math.pi, 1.)] * 7)

    def test_corrected_path_limits_and_speed_are_checked(self):
        current = [0.] * 7
        current[1] = 0.08
        bounds = [(-1., 1., 1.)] * 7
        bounds[1] = (-1., 0.08, 1.)
        with self.assertRaisesRegex(ValueError, '可動域'):
            hardware_sleep_cycle(current, [0.] * 7, math.radians(3), 6., bounds)
        with self.assertRaisesRegex(ValueError, '速度'):
            hardware_sleep_cycle([0.] * 7, [0.] * 7, math.radians(10), 2.,
                                 [(-1., 1., 1.)] * 7)

    def test_floor_geometry_and_invalid_height(self):
        scene = floor_scene(-0.01)
        floor = scene.world.collision_objects[0]
        self.assertEqual(floor.header.frame_id, 'base_link')
        self.assertAlmostEqual(floor.primitive_poses[0].position.z +
                               floor.primitives[0].dimensions[2] / 2, -0.01)
        for invalid in (float('nan'), 0.1, -1.):
            with self.assertRaises(ValueError):
                floor_scene(invalid)

    def trajectory(self):
        return JointTrajectory(joint_names=JOINTS, points=[
            JointTrajectoryPoint(positions=[0.] * 7, velocities=[0.] * 7),
            JointTrajectoryPoint(positions=[0.1] * 7, velocities=[0.1] * 7,
                                 time_from_start=Duration(sec=2)),
        ])

    def test_valid_slow_plan(self):
        validate_hardware_trajectory(self.trajectory(), [0.] * 7, [(-1., 1., 1.)] * 7)

    def test_invalid_plan_is_rejected(self):
        plan = self.trajectory()
        variants = []
        for mutate in (
            lambda p: p.joint_names.reverse(),
            lambda p: setattr(p.points[1], 'positions', [float('nan')] * 7),
            lambda p: setattr(p.points[1], 'velocities', [float('nan')] * 7),
            lambda p: setattr(p.points[1], 'velocities', [0.3] * 7),
            lambda p: setattr(p.points[1], 'positions', [2.] * 7),
            lambda p: setattr(p.points[1], 'time_from_start', Duration()),
            lambda p: setattr(p.points[1], 'time_from_start', Duration(nanosec=1)),
            lambda p: setattr(p.points[0], 'positions', [0.1] * 7),
        ):
            changed = copy.deepcopy(plan)
            mutate(changed)
            variants.append(changed)
        for changed in variants:
            with self.subTest(plan=changed):
                with self.assertRaises(ValueError):
                    validate_hardware_trajectory(changed, [0.] * 7, [(-1., 1., 1.)] * 7)


if __name__ == '__main__':
    unittest.main()
