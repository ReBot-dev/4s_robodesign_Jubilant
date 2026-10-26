"""Numerical checks for the drowsiness model; no ROS graph is required."""

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drowsiness_node import DrowsinessNode, integrate_drowsiness
from rclpy.parameter import Parameter


class DrowsinessModelTest(unittest.TestCase):
    def test_stationary_matches_analytic_solution(self):
        state = 0.0
        for _ in range(600):
            state = integrate_drowsiness(state, 0.0, 0.05)
        self.assertAlmostEqual(state, 1.0 - math.exp(-0.03 * 30), delta=0.001)

    def test_activity_alone_does_not_reduce_drowsiness(self):
        state = 0.6
        for _ in range(140):
            state = integrate_drowsiness(state, 1.0, 0.05)
        self.assertGreater(state, 0.6)
        self.assertGreater(integrate_drowsiness(0.0, 1.0, 0.05), 0.0)

    def test_activity_slows_growth_without_external_stimulus(self):
        state = 0.0
        for _ in range(600):
            state = integrate_drowsiness(state, 1.0, 0.05)
        self.assertAlmostEqual(state, 1.0 - math.exp(-0.006 * 30), delta=0.001)
        self.assertEqual(integrate_drowsiness(0.6, 1.0, 0.05, k_down=100.0),
                         integrate_drowsiness(0.6, 1.0, 0.05, k_down=0.0))

    def test_saturation_and_activity_clamping(self):
        self.assertEqual(integrate_drowsiness(0.99, 0.0, 1000), 1.0)
        self.assertEqual(integrate_drowsiness(0.01, 1.0, 1000, external_stimulus=1.0), 0.0)
        self.assertEqual(integrate_drowsiness(0.5, -1.0, 0.05),
                         integrate_drowsiness(0.5, 0.0, 0.05))
        self.assertEqual(integrate_drowsiness(0.5, 2.0, 0.05),
                         integrate_drowsiness(0.5, 1.0, 0.05))

    def test_invalid_parameters_are_rejected(self):
        for name, value in [('alpha', 1.1), ('alpha', -0.1), ('k_up', -1.0),
                            ('k_down', -1.0), ('update_rate', 0.0), ('k_up', float('nan'))]:
            with self.subTest(name=name, value=value):
                result = DrowsinessNode.validate_parameters([Parameter(name, value=value)])
                self.assertFalse(result.successful)

    def test_clock_startup_and_rewind_do_not_integrate_old_time(self):
        clock = SimpleNamespace(nanoseconds=1_000_000_000_000)
        published = []
        node = SimpleNamespace(
            drowsiness=0.0, activity=0.0, previous_update_ns=None,
            get_clock=lambda: SimpleNamespace(now=lambda: clock),
            get_parameter=lambda name: Parameter(name, value={
                'k_up': 0.03, 'alpha': 0.8, 'k_down': 0.1}[name]),
            publisher=SimpleNamespace(publish=published.append),
        )
        DrowsinessNode.update(node)
        self.assertEqual(node.drowsiness, 0.0)
        clock.nanoseconds += 50_000_000
        DrowsinessNode.update(node)
        self.assertAlmostEqual(node.drowsiness, 0.0015)
        clock.nanoseconds = 1_000_000_000
        DrowsinessNode.update(node)
        self.assertAlmostEqual(node.drowsiness, 0.0015)
        clock.nanoseconds += 50_000_000
        DrowsinessNode.update(node)
        self.assertGreater(node.drowsiness, 0.0015)
        self.assertEqual(len(published), 4)


if __name__ == '__main__':
    unittest.main()
