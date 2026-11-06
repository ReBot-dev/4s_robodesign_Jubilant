"""Read-only transport for stock CRANE-X7 arm servos (Protocol 2.0).

Only READ instructions are used. No register writes, torque changes, reboot,
mode changes or indirect-address setup are performed, including on close.
"""

import math


JOINT_NAMES = (
    'crane_x7_shoulder_fixed_part_pan_joint',
    'crane_x7_shoulder_revolute_part_tilt_joint',
    'crane_x7_upper_arm_revolute_part_twist_joint',
    'crane_x7_upper_arm_revolute_part_rotate_joint',
    'crane_x7_lower_arm_fixed_part_joint',
    'crane_x7_lower_arm_revolute_part_joint',
    'crane_x7_wrist_joint',
)
SERVO_IDS = tuple(range(2, 9))
EXPECTED_MODELS = (1020, 1120, 1020, 1020, 1020, 1020, 1020)


def decode_state(data):
    """Addresses 128..135: signed velocity and signed position, little endian.

    Position uses the stock 2048-pulse zero. This is an observation convention,
    not a calibrated pose for planning or control. Homing offsets are not changed.
    """
    if len(data) != 8:
        raise ValueError('Expected 8 bytes for velocity and position')
    velocity = int.from_bytes(bytes(data[:4]), 'little', signed=True)
    position = int.from_bytes(bytes(data[4:]), 'little', signed=True)
    return ((position - 2048) * math.tau / 4096,
            velocity * 0.229 * math.tau / 60)


class ReadOnlyArm:
    def __init__(self, port_name, baudrate=3000000, *, sdk=None):
        if sdk is None:
            import dynamixel_sdk as sdk
        self.sdk = sdk
        self.port = sdk.PortHandler(port_name)
        self.packet = sdk.PacketHandler(2.0)
        try:
            # SDK setBaudRate opens the host serial port. It does not change the
            # servo's Baud Rate register. Exclusive mode prevents cooperating
            # serial programs from opening it concurrently; stop all drivers first.
            if not self.port.setBaudRate(baudrate):
                raise RuntimeError(f'Cannot open {port_name} at {baudrate} bps')
            self.port.ser.exclusive = True
            self.torque_enabled = []
            for servo_id, expected in zip(SERVO_IDS, EXPECTED_MODELS):
                model = int.from_bytes(self._read(servo_id, 0, 2), 'little')
                if model != expected:
                    raise RuntimeError(f'ID {servo_id}: model {model}, expected {expected}; '
                                       'only stock CRANE-X7 is supported')
                self.torque_enabled.append(bool(self._read(servo_id, 64, 1)[0]))
        except BaseException:
            self.close()
            raise

    def _read(self, servo_id, address, length):
        data, result, error = self.packet.readTxRx(self.port, servo_id, address, length)
        if result != self.sdk.COMM_SUCCESS:
            raise RuntimeError(f'ID {servo_id}: {self.packet.getTxRxResult(result)}')
        if error:
            raise RuntimeError(f'ID {servo_id}: {self.packet.getRxPacketError(error)}')
        if len(data) != length:
            raise RuntimeError(f'ID {servo_id}: incomplete response ({len(data)}/{length})')
        return bytes(data)

    def read(self):
        # A partial scan is never published as a complete JointState.
        states = [decode_state(self._read(i, 128, 8)) for i in SERVO_IDS]
        return [s[0] for s in states], [s[1] for s in states]

    def close(self):
        if self.port.is_open:
            self.port.closePort()
