"""活動度の計算と、表現の指令分を差し引く処理の回帰テスト。"""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from activity_monitor import ActivityMonitor, remove_command  # noqa: E402
from drowsiness_node import integrate_drowsiness  # noqa: E402
from sensor_msgs.msg import JointState  # noqa: E402
from std_msgs.msg import Bool  # noqa: E402


class ActivityMonitorTest(unittest.TestCase):
    def setUp(self):
        self.clock = SimpleNamespace(nanoseconds=1_000_000_000)
        parameters = {'vel_threshold': 0.05, 'smoothing': 1.0}
        self.node = SimpleNamespace(
            activity=0.0, motion_duration=0.0, expression_active=False, expression_stamp=None,
            expression_velocity={}, expression_velocity_stamp=None,
            prev_pos=None, prev_time=None, pub=Mock(),
            seconds=lambda: self.clock.nanoseconds * 1e-9,
            get_parameter=lambda name: SimpleNamespace(value=parameters[name]))

    def at(self, seconds):
        self.clock.nanoseconds = round(seconds * 1e9)

    def joints(self, seconds, velocities, positions=None):
        self.at(seconds)
        names = list(velocities or positions)
        ActivityMonitor.on_joint_states(self.node, JointState(
            name=names,
            position=[(positions or {}).get(name, 0.0) for name in names],
            velocity=[velocities[name] for name in velocities or {}]))

    def expression(self, seconds, commands):
        self.at(seconds)
        ActivityMonitor.on_expression(self.node, Bool(data=True))
        ActivityMonitor.on_expression_velocity(self.node, JointState(
            name=list(commands), velocity=list(commands.values())))

    def test_motion_counts_outside_expression(self):
        self.joints(1.0, {'a': 0.1})
        self.assertEqual(self.node.activity, 1.0)
        self.joints(1.1, {'a': 0.0})
        self.assertEqual(self.node.activity, 0.0)

    def test_position_difference_is_used_without_velocity(self):
        self.joints(1.0, None, {'a': 0.0})
        self.joints(1.1, None, {'a': 0.02})
        self.assertEqual(self.node.activity, 1.0)

    def test_commanded_motion_is_removed(self):
        for i in range(5):
            t = 1.0 + i * 0.05
            self.expression(t, {'a': 0.2})
            self.joints(t, {'a': 0.2})
        self.assertEqual(self.node.activity, 0.0)

    def test_other_joint_counts_during_expression(self):
        for i in range(5):
            t = 1.0 + i * 0.05
            self.expression(t, {'a': 0.2})
            self.joints(t, {'a': 0.2, 'b': 0.1})
        self.assertEqual(self.node.activity, 1.0)

    def test_motion_beyond_command_counts(self):
        for i in range(5):
            t = 1.0 + i * 0.05
            self.expression(t, {'a': 0.1})
            self.joints(t, {'a': 0.2})
        self.assertEqual(self.node.activity, 1.0)

    def test_short_gap_before_first_feedback_is_not_activity(self):
        self.at(1.0)
        ActivityMonitor.on_expression(self.node, Bool(data=True))
        self.joints(1.0, {'a': 0.0})
        self.joints(1.02, {'a': 0.2})
        self.assertEqual(self.node.activity, 0.0)

    def test_stale_command_does_not_hide_motion(self):
        self.expression(1.0, {'a': 0.2})
        for i in range(5):
            t = 1.4 + i * 0.05
            self.at(t)
            ActivityMonitor.on_expression(self.node, Bool(data=True))
            self.joints(t, {'a': 0.2})
        self.assertEqual(self.node.activity, 1.0)

    def test_stale_flag_returns_to_measured_motion(self):
        self.expression(1.0, {'a': 0.2})
        self.joints(2.0, {'a': 0.2})
        self.assertEqual(self.node.activity, 1.0)

    def test_remove_command_does_not_invent_motion(self):
        self.assertEqual(remove_command(0.0, 0.2), 0.0)
        self.assertEqual(remove_command(0.1, 0.2), 0.0)
        self.assertAlmostEqual(remove_command(0.3, 0.2), 0.1)
        self.assertEqual(remove_command(-0.1, 0.2), -0.1)

    def test_activity_slows_drowsiness_without_lowering_it(self):
        moving = integrate_drowsiness(0.7, 1.0, 0.1)
        still = integrate_drowsiness(0.7, 0.0, 0.1)
        self.assertGreater(moving, 0.7)
        self.assertLess(moving, still)


if __name__ == '__main__':
    unittest.main()
