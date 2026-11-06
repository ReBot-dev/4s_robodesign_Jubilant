"""睡眠姿勢の向きと、肩・手首の連動を検証する。"""

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sleep_expression import SleepExpression, sleep_cycle, sleep_pose, waiting_pose


class SleepPoseTest(unittest.TestCase):
    def test_waiting_pose_is_close_and_points_down(self):
        origin = [.8, .4, .2, -2., .1, .4, -.3]
        waiting = waiting_pose(origin)
        sleeping = sleep_pose(origin)
        self.assertAlmostEqual(sum(waiting[i] for i in (1, 3, 5)), -math.pi)
        for i in range(7):
            self.assertAlmostEqual(waiting[i] - sleeping[i],
                                   math.radians({1: 10, 5: -10}.get(i, 0)))

    def test_sleep_pose_points_down_for_different_start_poses(self):
        for origin in ([0.0] * 7, [.8, .4, .2, -2., .1, .4, -.3]):
            pose = sleep_pose(origin)
            self.assertEqual(pose[0], origin[0])
            self.assertEqual(pose[6], origin[6])
            self.assertEqual((pose[2], pose[4]), (0., 0.))
            self.assertAlmostEqual(pose[1] + pose[3] + pose[5], -math.pi)

    def test_sway_keeps_tip_down(self):
        center = sleep_pose([0.] * 7)
        bounds = [(-math.pi, math.pi, 1.)] * 7
        points = sleep_cycle(center, math.radians(3), 6., bounds)
        for point in points:
            self.assertAlmostEqual(sum(point.positions[i] for i in (1, 3, 5)), -math.pi)
            self.assertAlmostEqual(point.velocities[1], -point.velocities[5])
        self.assertAlmostEqual(max(p.positions[1] for p in points), math.radians(13))
        self.assertAlmostEqual(min(p.positions[1] for p in points), math.radians(7))
        self.assertEqual(list(points[-1].positions), center)

    def test_wrist_limits_are_checked(self):
        bounds = [(-math.pi, math.pi, 1.)] * 7
        bounds[5] = (math.radians(-71), math.radians(90), 1.)
        with self.assertRaises(ValueError):
            sleep_cycle(sleep_pose([0.] * 7), math.radians(3), 6., bounds)


class StartupTest(unittest.TestCase):
    def make_node(self):
        node = SimpleNamespace(
            now=lambda: 10., last_tick=None, active=False, inputs_fresh=lambda now: True,
            model_verified=True, goal_handle=None, pending=False, next_start=0., blocked=False,
            bounds=[(-math.pi, math.pi, 1.)] * 7, arm=Mock(), planner=Mock(),
            validity=Mock(), expression=Mock(), get_logger=Mock(), plan_pose=Mock(),
            startup_attempted=False, sleepiness=0., threshold=.6, sleeping=False,
            positions=[0.] * 7, amplitude=math.radians(3), period=6.,
        )
        return node

    def test_startup_moves_even_below_threshold_then_waits(self):
        node = self.make_node()
        SleepExpression.update(node)
        node.plan_pose.assert_called_once_with(waiting_pose(node.positions), 'waiting')
        SleepExpression.update(node)
        self.assertEqual(node.plan_pose.call_count, 1)

    def test_startup_waits_for_safe_inputs_and_services(self):
        for unavailable in ('model_verified', 'fresh', 'planner', 'arm'):
            node = self.make_node()
            if unavailable == 'model_verified':
                node.model_verified = False
            elif unavailable == 'fresh':
                node.inputs_fresh = lambda now: False
            elif unavailable == 'planner':
                node.planner.service_is_ready.return_value = False
            else:
                node.arm.server_is_ready.return_value = False
            SleepExpression.update(node)
            node.plan_pose.assert_not_called()
            self.assertFalse(node.startup_attempted)

    def test_threshold_still_starts_sleep_from_waiting_pose(self):
        node = self.make_node()
        node.startup_attempted = True
        node.positions = waiting_pose(node.positions)
        node.sleepiness = .6
        SleepExpression.update(node)
        node.plan_pose.assert_called_once_with(sleep_pose(node.positions), 'lowering')
        self.assertEqual(node.awake_pose, node.positions)


if __name__ == '__main__':
    unittest.main()
