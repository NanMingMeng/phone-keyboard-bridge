import tempfile
import unittest
from pathlib import Path

from desktop.updater import build_update_script, is_newer, version_tuple


class TestUpdater(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(is_newer("v0.3.0", "0.2.0"))
        self.assertTrue(is_newer("0.10.0", "0.9.9"))
        self.assertFalse(is_newer("v0.2.0", "0.2.0"))
        self.assertEqual(version_tuple("v1.2.3"), (1, 2, 3))

    def test_update_script_contains_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "PKB.exe"
            new = root / "new" / "PKB.exe"
            script = build_update_script(current, new, 1234)
            text = script.read_text(encoding="utf-8-sig")
            self.assertIn(str(current), text)
            self.assertIn(str(new), text)
            self.assertIn("Wait-Process -Id 1234", text)


if __name__ == "__main__":
    unittest.main()
