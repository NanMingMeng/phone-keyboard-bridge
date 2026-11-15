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

    def test_fingerprint_inherits_existing_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            ua = "Mozilla/5.0 (Linux; Android 16) HeyTapBrowser/40.10.10.9"
            registry.touch("old-id", "10.0.0.2", ua, "申请连接", fingerprint="PLC110|Chrome")
            self.assertTrue(registry.approve("old-id", "我的手机"))
            state = registry.touch(
                "new-id", "10.0.1.3", ua, "申请连接", fingerprint="PLC110|Chrome"
            )
            self.assertEqual(state, STATUS_APPROVED)
            approved = registry.approved()
            self.assertEqual(len(approved), 1)
            self.assertEqual(approved[0]["device_id"], "new-id")
            self.assertEqual(approved[0]["alias"], "我的手机")

    def test_different_fingerprint_still_waits(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            ua = "Mozilla/5.0 (Linux; Android 16) Chrome/115.0 Mobile"
            registry.touch("device-1", "10.0.0.2", ua, "申请连接", fingerprint="phone-a")
            registry.approve("device-1", "手机 A")
            state = registry.touch("device-2", "10.0.0.9", ua, "申请连接", fingerprint="phone-b")
            self.assertEqual(state, STATUS_PENDING)

    def test_last_seen_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            registry = DeviceRegistry(path)
            ua = "test-agent"
            registry.touch("device-1", "10.0.0.2", ua, "申请连接")
            registry.approve("device-1", "手机")
            registry.touch("device-1", "10.0.0.2", ua, "粘贴文字")
            reloaded = DeviceRegistry(path)
            approved = reloaded.approved()
            self.assertEqual(len(approved), 1)
            self.assertGreater(approved[0]["last_seen"], 0)
            self.assertEqual(approved[0]["request_count"], 1)

    def test_merge_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            ua = "Mozilla/5.0 (Linux; Android 16) HeyTapBrowser/40.10.10.9"
            # 模拟升级前留下的历史记录：没有指纹，UA 相同
            registry.touch("id-1", "10.0.0.2", ua, "申请连接")
            registry.approve("id-1", "我的手机")
            registry.touch("id-2", "10.0.0.3", ua, "申请连接")
            registry.approve("id-2", "我的手机2")
            self.assertEqual(registry.duplicate_count(), 1)
            self.assertEqual(registry.merge_duplicates(), 1)
            approved = registry.approved()
            self.assertEqual(len(approved), 1)
            self.assertEqual(registry.duplicate_count(), 0)

    def test_merge_skips_distinct_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            ua = "Mozilla/5.0 (Linux; Android 16) HeyTapBrowser/40.10.10.9"
            # 两台不同手机：UA 相同但指纹明确不同，不应合并
            registry.touch("id-1", "10.0.0.2", ua, "申请连接", fingerprint="fp-1")
            registry.approve("id-1", "手机 A")
            registry.touch("id-2", "10.0.0.3", ua, "申请连接", fingerprint="fp-2")
            registry.approve("id-2", "手机 B")
            self.assertEqual(registry.duplicate_count(), 0)
            self.assertEqual(registry.merge_duplicates(), 0)
            self.assertEqual(len(registry.approved()), 2)

    def test_request_activation_only_for_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            registry = DeviceRegistry(path)
            ua = "test-agent"
            registry.touch("device-1", "10.0.0.2", ua, "申请连接")
            self.assertFalse(registry.request_activation("device-1"))
            registry.approve("device-1", "手机")
            self.assertTrue(registry.request_activation("device-1"))
            item = registry.approved()[0]
            self.assertEqual(item["activate"], 1)
            self.assertEqual(item["last_action"], "电脑唤醒打字界面")
            reloaded = DeviceRegistry(path)
            self.assertEqual(reloaded.approved()[0]["activate"], 1)


if __name__ == "__main__":
    unittest.main()
