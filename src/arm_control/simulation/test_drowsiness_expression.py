"""Trajectory and threshold checks without moving a robot or starting ROS nodes."""

from concurrent.futures import Future
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drowsiness_expression import DrowsinessExpression, JOINTS, make_cycle
from std_msgs.msg import Float32


class ExpressionTest(unittest.TestCase):
    def make_node(self):
        node = SimpleNamespace(
            threshold=0.6, amplitude=math.radians(5), period=4.0,
            sleepiness=0.0, sleep_stamp=10.0, joint_stamp=10.0,
            positions=[0.0] * 7, origin=None, limits=(-1.6, 1.6), velocity_limit=1.0,
            model_verified=True, pending=False, goal_handle=None, cancel_requested=False,
            blocked=False, active=False, next_start=0.0, last_tick=None,
            expression=Mock(), arm=Mock(), now=lambda: 10.0, get_logger=Mock(),
            on_goal=Mock(), on_feedback=Mock(), expression_velocity=Mock(),
        )
        node.arm.server_is_ready.return_value = True
        node.inputs_fresh = lambda now: DrowsinessExpression.inputs_fresh(node, now)
        return node

    def test_sine_extrema_and_other_joints_held(self):
        origin = [0.1, 0.4, -0.2, -1.0, 0.1, 0.5, 0.2]
        amplitude = math.radians(5)
        points = make_cycle(origin, amplitude, 4.0, -1.6, 1.6)
        for index, expected in [(0, .4), (20, .4 + amplitude),
                                (40, .4), (60, .4 - amplitude), (80, .4)]:
            self.assertAlmostEqual(points[index].positions[1], expected)
        for point in points:
            self.assertEqual(list(point.positions[:1] + point.positions[2:]), origin[:1] + origin[2:])
        self.assertEqual(list(points[0].velocities), [0.0] * 7)
        self.assertEqual(list(points[-1].velocities), [0.0] * 7)
        times = [p.time_from_start.sec + p.time_from_start.nanosec * 1e-9 for p in points]
        self.assertTrue(all(a < b for a, b in zip(times, times[1:])))

    def test_limit_violation_rejected(self):
        with self.assertRaises(ValueError):
            make_cycle([0.0, 1.59, 0, 0, 0, 0, 0], .1, 4.0, -1.6, 1.6)

    def test_below_at_above_threshold(self):
        for sleepiness, expected in [(0.59, False), (.6, True), (.8, True)]:
            node = self.make_node()
            node.sleepiness = sleepiness
            DrowsinessExpression.update(node)
            self.assertEqual(node.arm.send_goal_async.called, expected)
            if expected:
                goal = node.arm.send_goal_async.call_args.args[0]
                self.assertEqual(list(goal.trajectory.joint_names), JOINTS)
                self.assertTrue(node.expression.publish.call_args.args[0].data)

    def test_no_duplicate_goals_and_finish_cycle_below_threshold(self):
        node = self.make_node()
        node.sleepiness = .8
        DrowsinessExpression.update(node)
        DrowsinessExpression.update(node)
        self.assertEqual(node.arm.send_goal_async.call_count, 1)
        node.pending = False
        node.goal_handle = Mock()
        node.sleepiness = .2
        DrowsinessExpression.update(node)
        node.goal_handle.cancel_goal_async.assert_not_called()
        node.goal_handle = None
        DrowsinessExpression.update(node)
        self.assertFalse(node.expression.publish.call_args.args[0].data)
        self.assertIsNone(node.origin)

    def test_inputs_missing_stale_non_simulation_do_not_move(self):
        for name, value in [('sleep_stamp', None), ('joint_stamp', 8.0),
                            ('model_verified', False), ('blocked', True)]:
            node = self.make_node()
            node.sleepiness = .8
            setattr(node, name, value)
            DrowsinessExpression.update(node)
            node.arm.send_goal_async.assert_not_called()

    def test_stale_input_cancels_only_once(self):
        node = self.make_node()
        node.goal_handle = Mock()
        node.sleep_stamp = 8.0
        DrowsinessExpression.update(node)
        DrowsinessExpression.update(node)
        node.goal_handle.cancel_goal_async.assert_called_once()

    def test_preemption_blocks_until_below_threshold(self):
        node = self.make_node()
        node.goal_handle = Mock()
        future = Future()
        future.set_result(SimpleNamespace(status=5, result=SimpleNamespace(
            error_code=0, error_string='preempted')))
        DrowsinessExpression.on_result(node, future)
        self.assertTrue(node.blocked)
        self.assertIsNone(node.goal_handle)
        DrowsinessExpression.on_drowsiness(node, Float32(data=.2))
        self.assertFalse(node.blocked)

    def test_repeat_keeps_original_center(self):
        node = self.make_node()
        node.sleepiness = .8
        node.origin = [0.0] * 7
        node.positions[1] = .01  # 実際の追従誤差を周期ごとに蓄積しない。
        DrowsinessExpression.update(node)
        goal = node.arm.send_goal_async.call_args.args[0]
        self.assertEqual(goal.trajectory.points[-1].positions[1], 0.0)


if __name__ == '__main__':
    unittest.main()
