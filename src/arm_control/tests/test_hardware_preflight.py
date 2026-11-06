"""Preflight inspects the device without opening it or launching hardware."""

import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from launch import LaunchContext


spec = importlib.util.spec_from_file_location(
    'hardware_launch', Path(__file__).resolve().parents[1] / 'hardware_activity.launch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HardwarePreflightTest(unittest.TestCase):
    def setUp(self):
        self.context = LaunchContext()
        self.context.launch_configurations['port'] = '/dev/fake_crane'

    def test_missing_device_fails_before_driver(self):
        with patch.object(module.os, 'stat', side_effect=FileNotFoundError('missing')):
            with self.assertRaisesRegex(RuntimeError, 'USBポート'):
                module.check_serial_access(self.context)

    def test_non_device_is_rejected(self):
        with patch.object(module.os, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFREG)):
            with self.assertRaisesRegex(RuntimeError, 'シリアルデバイス'):
                module.check_serial_access(self.context)

    def test_missing_permission_explains_group_refresh(self):
        with patch.object(module.os, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFCHR, st_gid=20)), \
             patch.object(module.os, 'access', return_value=False), \
             patch.object(module.grp, 'getgrgid', return_value=SimpleNamespace(gr_name='dialout')):
            with self.assertRaisesRegex(RuntimeError, 'newgrp dialout'):
                module.check_serial_access(self.context)

    def test_accessible_device_passes_without_opening(self):
        with patch.object(module.os, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
             patch.object(module.os, 'access', return_value=True), \
             patch('builtins.open') as opened:
            self.assertEqual(module.check_serial_access(self.context), [])
            opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
