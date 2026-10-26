#!/usr/bin/env python3
"""先端を真下に向け、肩と手首を連動させて小さく揺らす睡眠表現。"""

import math
import xml.etree.ElementTree as ET

from action_msgs.msg import GoalStatus
from control_msgs.action import FollowJointTrajectory
from moveit_msgs.msg import Constraints, JointConstraint, RobotState
from moveit_msgs.srv import GetMotionPlan, GetStateValidity
import rclpy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool

from drowsiness_expression import DrowsinessExpression, JOINTS, make_cycle


def sleep_pose(origin):
    """肩10°・肘−120°・手首−70°。ピッチ合計−180°で先端の+Zが下向き。"""
    return [origin[0], math.radians(10), 0.0, math.radians(-120),
            0.0, math.radians(-70), origin[6]]


def sleep_cycle(center, amplitude, period, bounds):
    points = make_cycle(center, amplitude, period, *bounds[1][:2])
    for point in points:
        # 肩の傾きの変化を手首で打ち消し、先端は真下を向いたまま。
        point.positions[5] = center[5] - (point.positions[1] - center[1])
        point.velocities[5] = -point.velocities[1]
        for i, (lower, upper, velocity) in enumerate(bounds):
            if not lower <= point.positions[i] <= upper:
                raise ValueError(f'{JOINTS[i]}: 睡眠動作が可動域を超えます')
            if abs(point.velocities[i]) > velocity:
                raise ValueError(f'{JOINTS[i]}: 睡眠動作が速度上限を超えます')
    return points


class SleepExpression(DrowsinessExpression):
    def __init__(self):
        super().__init__(node_name='sleep_expression', amplitude_deg=3.0, period=6.0)
        self.bounds = None
        self.awake_pose = None
        self.sleep_center = None
        self.sleeping = False
        self.motion_kind = None
        self.planner = self.create_client(GetMotionPlan, '/plan_kinematic_path')
        self.validity = self.create_client(GetStateValidity, '/check_state_validity')
        self.get_logger().info('睡眠表現: 先端を真下に向け、肩と手首で小さく上下に揺らします')

    def on_description(self, msg):
        super().on_description(msg)
        try:
            root = ET.fromstring(msg.data)
            self.bounds = []
            for name in JOINTS:
                limit = root.find(f"./joint[@name='{name}']/limit")
                self.bounds.append(tuple(float(limit.attrib[key])
                                         for key in ('lower', 'upper', 'velocity')))
        except (ET.ParseError, AttributeError, KeyError, ValueError):
            self.simulation = False
            self.bounds = None

    @staticmethod
    def robot_state(positions):
        return RobotState(joint_state=JointState(name=JOINTS, position=list(positions)),
                          is_diff=True)

    def update(self):
        now = self.now()
        if self.last_tick is not None and now < self.last_tick:
            self.sleep_stamp = self.joint_stamp = None
            self.next_start = now
        self.last_tick = now
        if self.active:
            self.expression.publish(Bool(data=True))
        fresh = self.inputs_fresh(now)
        if (not fresh or not self.simulation) and self.goal_handle is not None:
            if not self.cancel_requested:
                self.cancel_requested = True
                self.goal_handle.cancel_goal_async()
        if self.pending or self.goal_handle is not None or now < self.next_start:
            return
        if self.active:
            self.active = False
            self.expression.publish(Bool(data=False))
        if (self.blocked or not fresh or not self.simulation or self.bounds is None
                or not self.arm.server_is_ready()):
            return
        if self.sleepiness < self.threshold:
            if self.sleeping:
                self.plan_pose(self.awake_pose, 'waking')
            return
        if not self.planner.service_is_ready() or not self.validity.service_is_ready():
            self.get_logger().warning('MoveItの計画・衝突確認サービスを待っています',
                                      throttle_duration_sec=5.0)
            return
        if not self.sleeping:
            self.awake_pose = list(self.positions)
            self.sleep_center = sleep_pose(self.awake_pose)
            try:
                # 中心だけでなく、揺れの両端も可動域に入ることを確認。
                sleep_cycle(self.sleep_center, self.amplitude, self.period, self.bounds)
            except ValueError as error:
                self.fail(error)
                return
            self.plan_pose(self.sleep_center, 'lowering')
        else:
            points = sleep_cycle(self.sleep_center, self.amplitude, self.period, self.bounds)
            self.pending = True
            self.active = True
            self.expression.publish(Bool(data=True))
            self.check_cycle(points, 0)

    def fail(self, error):
        self.get_logger().error(str(error))
        self.pending = False
        self.blocked = True
        self.next_start = self.now() + 0.3

    def plan_pose(self, target, kind):
        if not self.planner.service_is_ready():
            return
        self.pending = True
        self.active = True
        self.expression.publish(Bool(data=True))
        request = GetMotionPlan.Request()
        plan = request.motion_plan_request
        plan.group_name = 'arm'
        plan.pipeline_id = 'ompl'
        plan.num_planning_attempts = 3
        plan.allowed_planning_time = 5.0
        plan.max_velocity_scaling_factor = 0.2
        plan.max_acceleration_scaling_factor = 0.1
        plan.start_state = self.robot_state(self.positions)
        plan.goal_constraints = [Constraints(joint_constraints=[
            JointConstraint(joint_name=name, position=value, tolerance_above=.001,
                            tolerance_below=.001, weight=1.0)
            for name, value in zip(JOINTS, target)])]

        def planned(future):
            try:
                response = future.result().motion_plan_response
                if response.error_code.val != 1:
                    raise RuntimeError(f'睡眠姿勢の計画に失敗: MoveIt {response.error_code.val}')
                if not self.inputs_fresh(self.now()) or not self.simulation:
                    raise RuntimeError('計画中に入力が途切れたため実行しません')
                self.send_trajectory(response.trajectory.joint_trajectory, kind)
            except Exception as error:
                self.fail(error)
        self.planner.call_async(request).add_done_callback(planned)

    def check_cycle(self, points, index):
        if (not self.inputs_fresh(self.now()) or not self.simulation
                or self.sleepiness < self.threshold):
            self.pending = False
            self.next_start = self.now() + .3
            return
        if index == len(points):
            from trajectory_msgs.msg import JointTrajectory
            self.send_trajectory(JointTrajectory(joint_names=JOINTS, points=points), 'cycle')
            return
        request = GetStateValidity.Request()
        request.group_name = 'arm'
        request.robot_state = self.robot_state(points[index].positions)

        def checked(future):
            try:
                if not future.result().valid:
                    raise RuntimeError('睡眠動作の軌道に衝突があるため停止します')
                self.check_cycle(points, index + 1)
            except Exception as error:
                self.fail(error)
        self.validity.call_async(request).add_done_callback(checked)

    def send_trajectory(self, trajectory, kind):
        self.motion_kind = kind
        self.pending = True
        goal = FollowJointTrajectory.Goal(trajectory=trajectory)
        self.arm.send_goal_async(goal).add_done_callback(self.on_goal)

    def on_result(self, future):
        try:
            result = future.result()
            success = (result.status == GoalStatus.STATUS_SUCCEEDED
                       and result.result.error_code == FollowJointTrajectory.Result.SUCCESSFUL)
        except Exception:
            success = False
        super().on_result(future)
        if success and self.motion_kind == 'lowering':
            self.sleeping = True
            self.get_logger().info('先端を真下に向けた睡眠姿勢に到達しました')
        elif success and self.motion_kind == 'waking':
            self.sleeping = False
            self.awake_pose = self.sleep_center = None
        elif not success:
            # 手動操作が割り込んだ場合、その姿勢を取り返さない。
            self.sleeping = False
            self.awake_pose = self.sleep_center = None


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = SleepExpression()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            if node.goal_handle is not None:
                future = node.goal_handle.cancel_goal_async()
                rclpy.spin_until_future_complete(node, future, timeout_sec=1.0)
            node.expression.publish(Bool(data=False))
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
