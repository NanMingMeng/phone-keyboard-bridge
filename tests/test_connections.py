import unittest

from phone_keyboard.connections import ConnectionTracker


class TestConnections(unittest.TestCase):
    def test_describe_user_agent(self):
        self.assertEqual(
            ConnectionTracker.describe_user_agent(
                "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/142.0 Mobile Safari/537.36"
            ),
            "Android · Chrome",
        )
        self.assertEqual(
            ConnectionTracker.describe_user_agent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/142.0"
            ),
            "Windows · Edge",
        )

    def test_touch_and_snapshot(self):
        tracker = ConnectionTracker(online_timeout=60)
        ua = "Mozilla/5.0 (Linux; Android 15) Chrome/142.0 Mobile Safari/537.36"
        tracker.touch("192.168.43.2", ua, "打开手机页面")
        tracker.touch("192.168.43.2", ua)
        tracker.touch("192.168.43.2", ua, "粘贴文字")
        items = tracker.snapshot()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["ip"], "192.168.43.2")
        self.assertEqual(items[0]["request_count"], 2)
        self.assertEqual(items[0]["last_action"], "粘贴文字")
        self.assertTrue(items[0]["online"])
        self.assertEqual(tracker.online_count(), 1)

    def test_offline_record(self):
        tracker = ConnectionTracker(online_timeout=-1)
        tracker.touch("127.0.0.1", "test-agent", "打开手机页面")
        self.assertFalse(tracker.snapshot()[0]["online"])
        self.assertEqual(tracker.online_count(), 0)


if __name__ == "__main__":
    unittest.main()
