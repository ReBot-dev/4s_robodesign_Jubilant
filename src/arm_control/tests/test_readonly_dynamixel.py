"""Transport checks using real SDK packet construction, without a serial device."""

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import dynamixel_sdk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from readonly_dynamixel import ReadOnlyArm, decode_state


class FakePort:
    def __init__(self, name):
        self.is_open = False
        self.ser = SimpleNamespace(exclusive=False)
        self.closed = False

    def setBaudRate(self, baudrate):
        self.is_open = True
        return True

    def closePort(self):
        self.is_open = False
        self.closed = True


class ReadOnlyTransportTest(unittest.TestCase):
    def setUp(self):
        self.port = FakePort('fake')
        self.packet = dynamixel_sdk.PacketHandler(2.0)
        self.instructions = []
        self.failure = None
        self.bad_model = False

        def exchange(port, request):
            self.instructions.append(list(request))
            servo_id = request[4]
            address = request[8] + 256 * request[9]
            length = request[10] + 256 * request[11]
            if self.failure == 'communication':
                return [], dynamixel_sdk.COMM_RX_TIMEOUT, 0
            if address == 0:
                value = 999 if self.bad_model else 1120 if servo_id == 3 else 1020
                data = list(value.to_bytes(2, 'little'))
            elif address == 64:
                data = [1]
            elif address == 128:
                data = list((-10).to_bytes(4, 'little', signed=True) +
                            (2048).to_bytes(4, 'little', signed=True))
            else:
                self.fail(f'Unexpected register read: {address}')
            if self.failure == 'short':
                data = data[:-1]
            self.assertEqual(length, {0: 2, 64: 1, 128: 8}[address])
            return [0] * 8 + [128 if self.failure == 'hardware' else 0] + data, 0, 0

        self.packet.txRxPacket = exchange
        self.sdk = SimpleNamespace(PortHandler=lambda name: self.port,
                                   PacketHandler=lambda protocol: self.packet,
                                   COMM_SUCCESS=dynamixel_sdk.COMM_SUCCESS)

    def test_only_read_instructions_from_start_through_close(self):
        arm = ReadOnlyArm('fake', sdk=self.sdk)
        positions, velocities = arm.read()
        arm.close()
        self.assertEqual(len(positions), 7)
        self.assertEqual(positions, [0.0] * 7)
        self.assertAlmostEqual(velocities[0], -10 * 0.229 * math.tau / 60)
        self.assertEqual(arm.torque_enabled, [True] * 7)
        self.assertTrue(self.port.closed)
        self.assertTrue(self.port.ser.exclusive)
        self.assertEqual(len(self.instructions), 21)
        self.assertTrue(all(p[7] == 2 for p in self.instructions))  # Protocol 2 READ
        self.assertEqual([p[4] for p in self.instructions[-7:]], list(range(2, 9)))

    def test_failure_does_not_produce_a_partial_scan(self):
        for failure in ('communication', 'hardware', 'short'):
            with self.subTest(failure=failure):
                self.failure = None
                arm = ReadOnlyArm('fake', sdk=self.sdk)
                self.failure = failure
                try:
                    with self.assertRaises(RuntimeError):
                        arm.read()
                finally:
                    arm.close()
                self.assertTrue(all(p[7] == 2 for p in self.instructions))

    def test_unknown_model_closes_without_writing(self):
        self.bad_model = True
        with self.assertRaisesRegex(RuntimeError, 'model 999'):
            ReadOnlyArm('fake', sdk=self.sdk)
        self.assertTrue(self.port.closed)
        self.assertTrue(all(p[7] == 2 for p in self.instructions))

    def test_opening_failure_closes_port(self):
        def fail(baudrate):
            self.port.is_open = True
            raise OSError('busy')
        self.port.setBaudRate = fail
        with self.assertRaises(OSError):
            ReadOnlyArm('fake', sdk=self.sdk)
        self.assertTrue(self.port.closed)
        self.assertEqual(self.instructions, [])

    def test_signed_conversion_and_stock_zero(self):
        data = (-1).to_bytes(4, 'little', signed=True) + (-2048).to_bytes(4, 'little', signed=True)
        position, velocity = decode_state(data)
        self.assertAlmostEqual(position, -math.tau)
        self.assertLess(velocity, 0)
        data = (0).to_bytes(4, 'little') + (3072).to_bytes(4, 'little')
        self.assertAlmostEqual(decode_state(data)[0], math.pi / 2)
        with self.assertRaises(ValueError):
            decode_state(b'\x00' * 7)


if __name__ == '__main__':
    unittest.main()
