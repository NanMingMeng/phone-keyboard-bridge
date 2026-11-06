import tempfile
import unittest
from pathlib import Path

from phone_keyboard.connections import STATUS_APPROVED, STATUS_DENIED, STATUS_PENDING, DeviceRegistry


class TestDeviceRegistry(unittest.TestCase):
    def test_new_device_waits_for_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            ua = "Mozilla/5.0 (Linux; Android 15) Chrome/142.0 Mobile Safari/537.36"
            state = registry.touch("device-1", "192.168.1.2", ua, "申请连接")
            self.assertEqual(state, STATUS_PENDING)
            self.assertEqual(registry.describe_user_agent(ua), "Android · Chrome")
            self.assertEqual(len(registry.pending()), 1)

    def test_approval_persists_and_reloads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            registry = DeviceRegistry(path)
            ua = "Mozilla/5.0 (Windows NT 10.0) Chrome/142.0"
            registry.touch("device-1", "192.168.1.2", ua, "申请连接")
            self.assertTrue(registry.approve("device-1", "我的手机"))
            self.assertEqual(registry.touch("device-1", "192.168.1.2", ua), STATUS_APPROVED)
            reloaded = DeviceRegistry(path)
            approved = reloaded.approved()
            self.assertEqual(len(approved), 1)
            self.assertEqual(approved[0]["alias"], "我的手机")
            self.assertEqual(approved[0]["status"], STATUS_APPROVED)

    def test_deny_and_request_again(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            ua = "test-agent"
            registry.touch("device-1", "127.0.0.1", ua, "申请连接")
            self.assertTrue(registry.deny("device-1"))
            self.assertEqual(registry.touch("device-1", "127.0.0.1", ua), STATUS_DENIED)
            self.assertEqual(
                registry.touch("device-1", "127.0.0.1", ua, "重新申请", reset_denied=True),
                STATUS_PENDING,
            )

    def test_revoke(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            registry.touch("device-1", "127.0.0.1", "test", "申请连接")
            registry.approve("device-1", "手机")
            self.assertTrue(registry.revoke("device-1"))
            self.assertEqual(registry.approved(), [])


if __name__ == "__main__":
    unittest.main()
