import tempfile
import unittest
from pathlib import Path

from phone_keyboard.config import ensure_data_dir, load_or_create_token
from phone_keyboard.server import safe_file_name, safe_image_stem


class TestConfig(unittest.TestCase):
    def test_token_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = ensure_data_dir(Path(directory))
            first = load_or_create_token(data_dir)
            second = load_or_create_token(data_dir)
            self.assertEqual(first, second)
            self.assertGreater(len(first), 10)
            self.assertTrue((data_dir / "images").is_dir())

    def test_safe_image_stem(self):
        self.assertEqual(safe_image_stem("../../my photo!.png"), "my_photo")
        self.assertEqual(safe_image_stem("图片.png"), "image")

    def test_safe_file_name(self):
        self.assertEqual(safe_file_name("../../测试文件.docx"), "测试文件.docx")
        self.assertEqual(safe_file_name('bad<>:"name.pdf'), "bad_name.pdf")


if __name__ == "__main__":
    unittest.main()
