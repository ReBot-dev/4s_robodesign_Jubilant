"""睡眠姿勢の向きと、肩・手首の連動を検証する。"""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sleep_expression import sleep_cycle, sleep_pose


class SleepPoseTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
