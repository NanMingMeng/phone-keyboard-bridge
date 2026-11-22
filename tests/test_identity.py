import json
import tempfile
import unittest
from pathlib import Path

from phone_keyboard.connections import STATUS_APPROVED, DeviceRegistry
from phone_keyboard.identity import HIGH, LOW, MEDIUM, compute_identity

APP_UA = "Dalvik/2.1.0 (Linux; U; Android 16; PLC110 Build/BP2A.250605.015)"
WEBVIEW_UA = (
    "Mozilla/5.0 (Linux; Android 16; PLC110 Build/BP2A.250605.015; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.179 "
    "Mobile Safari/537.36"
)
CHROME_UA = (
    "Mozilla/5.0 (Linux; Android 16; PLC110 Build/BP2A.250605.015) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.179 Mobile Safari/537.36"
)
PHONE_FP = "PLC110|Chrome|Linux aarch64|zh-CN|Asia/Shanghai|364x801x24"
PS_UA = "Mozilla/5.0 (Windows NT; Windows NT 10.0; zh-CN) WindowsPowerShell/5.1.26100.9818"


class TestIdentity(unittest.TestCase):
    def test_three_clients_of_one_phone_share_identity(self):
        app = compute_identity(APP_UA, "", "10.44.69.160")
        webview = compute_identity(WEBVIEW_UA, PHONE_FP, "10.44.69.160")
        chrome = compute_identity(CHROME_UA, PHONE_FP, "10.44.69.23")
        self.assertEqual(app.key, "android:plc110")
        self.assertEqual(app.confidence, HIGH)
        self.assertEqual(webview.key, app.key)
        self.assertEqual(chrome.key, app.key)

    def test_fingerprint_model_used_when_ua_has_none(self):
        # UA 被本地脚本污染（没有机型），指纹里的机型仍然能认出是同一台手机
        identity = compute_identity(PS_UA, PHONE_FP, "10.44.69.160")
        self.assertEqual(identity.key, "android:plc110")
        self.assertEqual(identity.confidence, HIGH)

    def test_ipad_and_desktop_browser_use_fingerprint(self):
        ipad = compute_identity(
            "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            "|Safari|iPad|zh-CN|Asia/Shanghai|820x1180x2",
            "10.0.0.9",
        )
        self.assertEqual(ipad.confidence, MEDIUM)
        self.assertIn("820x1180x2", ipad.key)
        desktop = compute_identity(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/142.0",
            "|Chrome|Win32|zh-CN|Asia/Shanghai|1920x1080x24",
            "127.0.0.1",
        )
        self.assertEqual(desktop.confidence, MEDIUM)

    def test_script_client_is_low_confidence(self):
        identity = compute_identity(PS_UA, "", "127.0.0.1")
        self.assertEqual(identity.confidence, LOW)
        self.assertEqual(identity.key, "desktop|windows:powershell")


class TestAutomaticDeduplication(unittest.TestCase):
    def test_three_clients_merge_into_one_device(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            registry.touch("id-app", "10.44.69.160", APP_UA, "申请连接")
            registry.approve("id-app", "我的手机")
            # App 内 WebView 页面
            self.assertEqual(
                registry.touch("id-wv", "10.44.69.160", WEBVIEW_UA, "申请连接", fingerprint=PHONE_FP),
                STATUS_APPROVED,
            )
            # 手机浏览器
            self.assertEqual(
                registry.touch("id-chrome", "10.44.69.23", CHROME_UA, "申请连接", fingerprint=PHONE_FP),
                STATUS_APPROVED,
            )
            approved = registry.approved()
            self.assertEqual(len(approved), 1)
            self.assertEqual(len(approved[0]["device_ids"]), 3)
            self.assertEqual(registry.duplicate_count(), 0)
            self.assertEqual(registry.duplicate_count.__self__._duplicate_groups(), [])

    def test_alternating_ids_do_not_grow_records(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            registry.touch("id-wv", "10.44.69.160", WEBVIEW_UA, "申请连接", fingerprint=PHONE_FP)
            registry.approve("id-wv", "我的手机")
            for _ in range(10):
                self.assertEqual(
                    registry.touch("id-chrome", "10.44.69.160", CHROME_UA, fingerprint=PHONE_FP),
                    STATUS_APPROVED,
                )
                self.assertEqual(
                    registry.touch("id-wv", "10.44.69.160", WEBVIEW_UA, fingerprint=PHONE_FP),
                    STATUS_APPROVED,
                )
            self.assertEqual(len(registry.approved()), 1)

    def test_duplicate_records_merged_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            # 模拟老版本留下的三条同机记录（不同 id、不同 UA、部分没有指纹），直接写文件
            legacy = {
                "devices": [
                    {
                        "device_id": device_id,
                        "alias": "我的手机",
                        "user_agent": ua,
                        "fingerprint": fp,
                        "first_seen": 1000.0 + index,
                        "last_seen": 2000.0 + index,
                        "request_count": ops,
                        "last_action": "申请连接",
                        "approved_at": 1000.0 + index,
                        "activate_seq": 0,
                    }
                    for index, (device_id, ua, fp, ops) in enumerate(
                        (
                            ("pkb-app-old", WEBVIEW_UA, PHONE_FP, 61),
                            ("pkb-app-new", CHROME_UA, PHONE_FP, 13),
                            ("pkb-app-6abf", APP_UA, PHONE_FP, 2),
                        )
                    )
                ]
            }
            path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            registry = DeviceRegistry(path)
            approved = registry.approved()
            self.assertEqual(len(approved), 1)
            self.assertEqual(len(approved[0]["device_ids"]), 3)
            self.assertEqual(approved[0]["request_count"], 61 + 13 + 2)
            self.assertEqual(approved[0]["identity"], "android:plc110")
            self.assertEqual(registry.duplicate_count(), 0)

    def test_script_client_stays_separate_from_phone(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            registry.touch("id-wv", "10.44.69.160", WEBVIEW_UA, "申请连接", fingerprint=PHONE_FP)
            registry.approve("id-wv", "我的手机")
            registry.touch("diag-pc-001", "127.0.0.1", PS_UA, "申请连接")
            registry.approve("diag-pc-001", "本机测试")
            self.assertEqual(len(registry.approved()), 2)
            self.assertEqual(registry.duplicate_count(), 0)

    def test_different_phone_models_stay_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DeviceRegistry(Path(directory) / "devices.json")
            ua_a = "Mozilla/5.0 (Linux; Android 16; PLC110 Build/BP2A) Chrome/138.0 Mobile"
            ua_b = "Mozilla/5.0 (Linux; Android 16; M2101K9C Build/TKQ1) Chrome/138.0 Mobile"
            registry.touch("id-a", "10.0.0.2", ua_a, "申请连接", fingerprint="PLC110|Chrome|x|zh-CN|CST|1x2x3")
            registry.approve("id-a", "手机 A")
            state = registry.touch(
                "id-b", "10.0.0.3", ua_b, "申请连接", fingerprint="M2101K9C|Chrome|x|zh-CN|CST|1x2x3"
            )
            # 不同机型：新设备照旧走人工授权，不会被自动认成 A
            self.assertEqual(state, "pending")
            self.assertEqual(len(registry.approved()), 1)


if __name__ == "__main__":
    unittest.main()
