#!/usr/bin/env python3
"""Explicitly enabled hardware sleep expression; Gazebo remains a separate entry point."""

import math

from rcl_interfaces.msg import ParameterDescriptor
from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject, PlanningScene
from moveit_msgs.srv import ApplyPlanningScene
import rclpy
from rclpy.signals import SignalHandlerOptions
from shape_msgs.msg import SolidPrimitive
from std_msgs.msg import Bool
from std_srvs.srv import SetBool

from drowsiness_expression import DrowsinessExpression, JOINTS
from sleep_expression import SleepExpression, sleep_cycle


def floor_scene(top):
    if not math.isfinite(top) or not -0.1 <= top <= 0.0:
        raise ValueError('floor_top must be in [-0.1, 0] m relative to base_link')
    floor = CollisionObject(id='hardware_support_surface', operation=CollisionObject.ADD)
    floor.header.frame_id = 'base_link'
    pose = Pose()
    pose.orientation.w = 1.0
    pose.position.z = top - 0.05
    floor.primitives = [SolidPrimitive(type=SolidPrimitive.BOX, dimensions=[3.0, 3.0, 0.1])]
    floor.primitive_poses = [pose]
    scene = PlanningScene(is_diff=True)
    scene.robot_state.is_diff = True
    scene.world.collision_objects = [floor]
    return scene


def validate_hardware_trajectory(trajectory, current, bounds):
    if list(trajectory.joint_names) != JOINTS or not trajectory.points:
        raise ValueError('実機7軸の軌道ではありません')
    previous_time = None
    previous_positions = current
    for point in trajectory.points:
        positions = list(point.positions)
        velocities = list(point.velocities)
        stamp = point.time_from_start.sec + point.time_from_start.nanosec * 1e-9
        if (len(positions) != 7 or not all(math.isfinite(p) for p in positions)
                or len(velocities) not in (0, 7)
                or any(not math.isfinite(v) or abs(v) > 0.25 for v in velocities)):
            raise ValueError('実機軌道の値または速度が不正です（上限0.25 rad/s）')
        if any(not lower <= p <= upper for p, (lower, upper, _) in zip(positions, bounds)):
            raise ValueError('実機軌道が関節可動域を超えています')
        if previous_time is None:
            if stamp < 0:
                raise ValueError('軌道の開始時刻が負です')
            for name, measured, planned in zip(JOINTS, current, positions):
                if abs(measured - planned) > 0.03:
                    raise ValueError(f'軌道の開始姿勢が現在姿勢から離れています: {name}, '
                                     f'実測{math.degrees(measured):.3f}°, '
                                     f'軌道先頭{math.degrees(planned):.3f}°, '
                                     f'差{math.degrees(planned - measured):.3f}°')
        else:
            dt = stamp - previous_time
            if dt <= 0 or any(abs(a - b) / dt > 0.25 + 1e-6
                              for a, b in zip(positions, previous_positions)):
                raise ValueError('軌道の時刻またはサンプル間の速度が不正です')
        previous_time, previous_positions = stamp, positions


def start_state_issues(positions, bounds):
    """Describe measured violations without clamping or changing joint limits."""
    if positions is None or bounds is None or len(positions) != 7 or len(bounds) != 7:
        return ['7軸の角度または可動域が未取得です']
    issues = []
    for name, position, (lower, upper, _) in zip(JOINTS, positions, bounds):
        if not math.isfinite(position) or not lower <= position <= upper:
            issues.append(f'{name}: 現在{math.degrees(position):.3f}°、'
                          f'範囲[{math.degrees(lower):.3f}, {math.degrees(upper):.3f}]°')
    return issues


def hardware_sleep_cycle(current, center, amplitude, period, bounds):
    """Start at measured angles; decay <=5 degree errors over half a cycle.

    Keep the nominal center fixed. Re-anchoring the center to feedback every
    cycle would accumulate tracking errors. All corrected samples are checked
    for limits here and for collisions through the normal MoveIt validity path.
    """
    issues = start_state_issues(current, bounds)
    if issues:
        raise ValueError('揺れ開始時の角度が不正です: ' + '; '.join(issues))
    offsets = [actual - target for actual, target in zip(current, center)]
    for name, offset in zip(JOINTS, offsets):
        if not math.isfinite(offset) or abs(offset) > math.radians(5):
            raise ValueError(f'睡眠姿勢とのずれが5°を超えています: {name}, '
                             f'差{math.degrees(offset):.3f}°。保持・負荷を確認してください')
    points = sleep_cycle(center, amplitude, period, bounds)
    for point in points:
        elapsed = point.time_from_start.sec + point.time_from_start.nanosec * 1e-9 - 0.1
        u = min(1.0, max(0.0, elapsed / (period / 2)))
        # Quintic correction has zero velocity/acceleration at both ends.
        weight = 1 - 10 * u**3 + 15 * u**4 - 6 * u**5
        rate = -30 * u**2 * (1 - u)**2 / (period / 2)
        for index, (offset, (lower, upper, velocity)) in enumerate(zip(offsets, bounds)):
            point.positions[index] += offset * weight
            point.velocities[index] += offset * rate
            if not lower <= point.positions[index] <= upper:
                raise ValueError(f'{JOINTS[index]}: 接続区間が可動域を超えます')
            if abs(point.velocities[index]) > min(velocity, 0.25):
                raise ValueError(f'{JOINTS[index]}: 接続区間が速度上限を超えます')
    return points


class HardwareSleepExpression(SleepExpression):
    HARDWARE_PLUGIN = 'crane_x7_hardware/CraneX7Hardware'

    def __init__(self):
        self.enabled = False
        super().__init__()
        self.declare_parameter('camera_model_confirmed', False,
                               ParameterDescriptor(read_only=True))
        self.declare_parameter('floor_top', -0.01, ParameterDescriptor(read_only=True))
        self.floor = floor_scene(self.get_parameter('floor_top').value)
        self.floor_ready = False
        self.floor_pending = False
        self.scene_client = self.create_client(ApplyPlanningScene, '/apply_planning_scene')
        self.create_timer(0.5, self.ensure_floor)
        self.create_service(SetBool, '~/enable', self.on_enable)
        # Avoid a duplicate consumer of the same action; retain the normal
        # cancellation path and mark any late accepted goal for cancellation.
        self.get_logger().info('実機表現は停止中です。モデル確認後に ~/enable で開始します')

    def ensure_floor(self):
        if self.floor_ready or self.floor_pending or not self.scene_client.service_is_ready():
            return
        self.floor_pending = True

        def applied(future):
            self.floor_pending = False
            try:
                self.floor_ready = future.result().success
                if not self.floor_ready:
                    self.get_logger().error('設置面の衝突モデルを登録できませんでした')
            except Exception as error:
                self.get_logger().error(str(error))
        self.scene_client.call_async(ApplyPlanningScene.Request(scene=self.floor)).add_done_callback(applied)

    def inputs_fresh(self, now):
        # Also guards asynchronous MoveIt callbacks after a stop request.
        return self.enabled and super().inputs_fresh(now)

    def on_enable(self, request, response):
        if not request.data:
            self.enabled = False
            if self.goal_handle is not None and not self.cancel_requested:
                self.cancel_requested = True
                self.goal_handle.cancel_goal_async()
            response.success = True
            response.message = '停止要求を受信しました。トルクは変更しません'
            return response
        if not self.get_parameter('camera_model_confirmed').value:
            response.message = 'カメラ・固定具のモデル一致が未確認です。動作を開始しません'
        elif not self.model_verified:
            response.message = '実機用のrobot_descriptionを確認できていません'
        elif not self.floor_ready:
            response.message = '設置面の衝突モデルをMoveItへ登録できていません'
        elif not DrowsinessExpression.inputs_fresh(self, self.now()):
            response.message = '関節情報または眠気の入力が未受信・古い状態です'
        elif issues := start_state_issues(self.positions, self.bounds):
            response.message = '開始姿勢が可動域外です。動作は送りません: ' + '; '.join(issues)
        elif self.pending or self.goal_handle is not None:
            response.message = '進行中の処理が終了してから再度開始してください'
        elif not all((self.arm.server_is_ready(), self.planner.service_is_ready(),
                      self.validity.service_is_ready())):
            response.message = 'コントローラまたはMoveItの準備ができていません'
        else:
            self.enabled = True
            self.blocked = False
            response.success = True
            response.message = '実機の睡眠表現を開始します'
        return response

    def fail(self, error):
        # The shared simulation callback clears blocked when drowsiness is low.
        # Hardware failures must still require another explicit enable request.
        self.enabled = False
        super().fail(error)
        self.get_logger().warning('実機表現を無効にしました。原因解消後に再度開始してください')

    def plan_pose(self, target, kind):
        issues = start_state_issues(self.positions, self.bounds)
        if issues:
            self.fail(ValueError('開始姿勢が可動域外です: ' + '; '.join(issues)))
            return
        super().plan_pose(target, kind)

    def make_sleep_cycle(self):
        points = hardware_sleep_cycle(self.positions, self.sleep_center, self.amplitude,
                                      self.period, self.bounds)
        differences = ', '.join(
            f'{name}={math.degrees(actual - target):+.2f}°'
            for name, actual, target in zip(JOINTS, self.positions, self.sleep_center)
            if abs(actual - target) > 0.03)
        if differences:
            self.get_logger().info('実測姿勢から揺れへ接続します（中心は固定）: ' + differences)
        return points

    def on_goal(self, future):
        super().on_goal(future)
        if ((not self.inputs_fresh(self.now()) or not self.model_verified)
                and self.goal_handle is not None):
            self.cancel_requested = True
            self.goal_handle.cancel_goal_async()

    def send_trajectory(self, trajectory, kind):
        if not self.inputs_fresh(self.now()) or not self.model_verified:
            self.fail(RuntimeError('停止要求または入力途絶のため軌道を送信しません'))
            return
        # MoveIt plans already obey scaling; the generated sway uses a much
        # smaller absolute velocity cap. Check every outgoing sample as well.
        try:
            validate_hardware_trajectory(trajectory, self.positions, self.bounds)
        except ValueError as error:
            self.fail(error)
            return
        super().send_trajectory(trajectory, kind)


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = HardwareSleepExpression()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.enabled = False
        if rclpy.ok():
            if node.goal_handle is not None:
                future = node.goal_handle.cancel_goal_async()
                rclpy.spin_until_future_complete(node, future, timeout_sec=1.0)
            node.expression.publish(Bool(data=False))
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
