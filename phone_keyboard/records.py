from __future__ import annotations

import datetime
import json
import threading
import uuid
from pathlib import Path
from typing import Any


MAX_RECORDS = 50


class RecordStore:
    def __init__(self, storage_path: Path, max_records: int = MAX_RECORDS) -> None:
        self._storage_path = storage_path
        self._max_records = max_records
        self._records: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        records = data.get("records", []) if isinstance(data, dict) else []
        if isinstance(records, list):
            self._records = [item for item in records if isinstance(item, dict)][: self._max_records]

    def _save(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps({"records": self._records}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _add(self, item: dict[str, Any]) -> dict[str, Any]:
        item = {
            "id": uuid.uuid4().hex,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            **item,
        }
        with self._lock:
            self._records.insert(0, item)
            self._records = self._records[: self._max_records]
            self._save()
        return item

    def add_text(self, text: str, action: str, success: bool, error: str = "") -> dict[str, Any]:
        return self._add(
            {
                "type": "text",
                "text": text,
                "action": action,
                "success": success,
                "error": error,
            }
        )

    def add_image(
        self,
        image_path: Path,
        action: str,
        success: bool,
        error: str = "",
    ) -> dict[str, Any]:
        return self._add(
            {
                "type": "image",
                "image_path": str(image_path),
                "action": action,
                "success": success,
                "error": error,
            }
        )

    def add_file(
        self,
        file_path: Path,
        action: str,
        success: bool,
        error: str = "",
    ) -> dict[str, Any]:
        return self._add(
            {
                "type": "file",
                "file_path": str(file_path),
                "action": action,
                "success": success,
                "error": error,
            }
        )

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._records]

    def delete(self, record_id: str, delete_image: bool = True) -> bool:
        with self._lock:
            found = None
            remaining = []
            for item in self._records:
                if item.get("id") == record_id and found is None:
                    found = item
                else:
                    remaining.append(item)
            if found is None:
                return False
            self._records = remaining
            self._save()
        if delete_image and found.get("type") == "image":
            self._delete_file(found.get("image_path"))
        if delete_image and found.get("type") == "file":
            self._delete_file(found.get("file_path"))
        return True

    def clear(self, delete_images: bool = True) -> None:
        with self._lock:
            old_records = self._records
            self._records = []
            self._save()
        if delete_images:
            for item in old_records:
                if item.get("type") == "image":
                    self._delete_file(item.get("image_path"))
                if item.get("type") == "file":
                    self._delete_file(item.get("file_path"))

    @staticmethod
    def _delete_file(value: Any) -> None:
        if not value:
            return
        try:
            Path(str(value)).unlink(missing_ok=True)
        except OSError:
            pass
