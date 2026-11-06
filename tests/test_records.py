import tempfile
import unittest
from pathlib import Path

from phone_keyboard.records import RecordStore


class TestRecordStore(unittest.TestCase):
    def test_text_record_and_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecordStore(Path(directory) / "records.json", max_records=2)
            store.add_text("first", "粘贴文字", True)
            store.add_text("second", "粘贴文字", True)
            store.add_text("third", "粘贴文字", True)
            records = store.records()
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["text"], "third")
            self.assertEqual(records[1]["text"], "second")

    def test_delete_image_removes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            image.write_bytes(b"png")
            store = RecordStore(root / "records.json")
            record = store.add_image(image, "粘贴图片", True)
            self.assertTrue(store.delete(record["id"], delete_image=True))
            self.assertFalse(image.exists())
            self.assertEqual(store.records(), [])

    def test_clear_removes_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.jpg"
            image.write_bytes(b"jpg")
            store = RecordStore(root / "records.json")
            store.add_image(image, "保存图片", True)
            store.clear(delete_images=True)
            self.assertFalse(image.exists())
            self.assertEqual(store.records(), [])


if __name__ == "__main__":
    unittest.main()
