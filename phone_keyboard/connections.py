from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ONLINE_TIMEOUT_SECONDS = 15.0

STATUS_APPROVED = "approved"
STATUS_PENDING = "pending"
STATUS_DENIED = "denied"


@dataclass
class DeviceRecord:
    device_id: str
    ip: str
    user_agent: str
    device: str
    first_seen: float
    last_seen: float
    request_count: int = 0
    last_action: str = ""
    status: str = STATUS_PENDING
    alias: str = ""
    approved_at: float = 0.0


class DeviceRegistry:
    def __init__(self, storage_path: Path, online_timeout: float = ONLINE_TIMEOUT_SECONDS) -> None:
        self._storage_path = storage_path
        self._online_timeout = online_timeout
        self._records: dict[str, DeviceRecord] = {}
        self._lock = threading.Lock()
        self._load()

    @staticmethod
    def describe_user_agent(user_agent: str) -> str:
        ua = user_agent or ""
        if "Android" in ua:
            system = "Android"
        elif "iPhone" in ua:
            system = "iPhone"
        elif "iPad" in ua:
            system = "iPad"
        elif "Windows" in ua:
            system = "Windows"
        elif "Macintosh" in ua or "Mac OS X" in ua:
            system = "macOS"
        elif "Linux" in ua:
            system = "Linux"
        else:
            system = "未知设备"

        if "Edg/" in ua:
            browser = "Edge"
        elif "Chrome/" in ua or "CriOS/" in ua:
            browser = "Chrome"
        elif "Firefox/" in ua or "FxiOS/" in ua:
            browser = "Firefox"
        elif "Safari/" in ua:
            browser = "Safari"
        else:
            browser = "浏览器"
        return f"{system} · {browser}"

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        devices = data.get("devices", []) if isinstance(data, dict) else []
        if not isinstance(devices, list):
            return
        now = time.time()
        for item in devices:
            if not isinstance(item, dict):
                continue
            device_id = str(item.get("device_id", "")).strip()
            if not device_id:
                continue
            ua = str(item.get("user_agent", ""))
            self._records[device_id] = DeviceRecord(
                device_id=device_id,
                ip="",
                user_agent=ua,
                device=self.describe_user_agent(ua),
                first_seen=now,
                last_seen=0.0,
                status=STATUS_APPROVED,
                alias=str(item.get("alias", "")).strip(),
                approved_at=float(item.get("approved_at", 0.0) or 0.0),
            )

    def _save(self) -> None:
        approved = []
        for record in self._records.values():
            if record.status != STATUS_APPROVED:
                continue
            approved.append(
                {
                    "device_id": record.device_id,
                    "alias": record.alias,
                    "user_agent": record.user_agent,
                    "approved_at": record.approved_at,
                }
            )
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps({"devices": approved}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def touch(
        self,
        device_id: str,
        ip: str,
        user_agent: str,
        action: str | None = None,
        reset_denied: bool = False,
    ) -> str:
        now = time.time()
        ua = (user_agent or "")[:300]
        with self._lock:
            record = self._records.get(device_id)
            if record is None:
                record = DeviceRecord(
                    device_id=device_id,
                    ip=ip,
                    user_agent=ua,
                    device=self.describe_user_agent(ua),
                    first_seen=now,
                    last_seen=now,
                )
                self._records[device_id] = record
            record.ip = ip
            record.user_agent = ua
            record.device = self.describe_user_agent(ua)
            record.last_seen = now
            if record.status == STATUS_DENIED and reset_denied:
                record.status = STATUS_PENDING
                record.first_seen = now
                record.last_action = "重新申请"
            if action:
                record.request_count += 1
                record.last_action = action
            return record.status

    def approve(self, device_id: str, alias: str) -> bool:
        with self._lock:
            record = self._records.get(device_id)
            if record is None:
                return False
            record.status = STATUS_APPROVED
            record.alias = alias.strip() or record.device
            record.approved_at = time.time()
            self._save()
            return True

    def deny(self, device_id: str) -> bool:
        with self._lock:
            record = self._records.get(device_id)
            if record is None:
                return False
            record.status = STATUS_DENIED
            record.last_action = "已拒绝"
            return True

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            records = [item for item in self._records.values() if item.status == STATUS_PENDING]
            records.sort(key=lambda item: item.first_seen)
            now = time.time()
            return [self._as_dict(item, now) for item in records]

    def approved(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            records = [item for item in self._records.values() if item.status == STATUS_APPROVED]
            records.sort(key=lambda item: item.last_seen, reverse=True)
            result = []
            for item in records:
                data = self._as_dict(item, now)
                data["online"] = item.last_seen > 0 and now - item.last_seen <= self._online_timeout
                result.append(data)
            return result

    def snapshot(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            records = list(self._records.values())
            records.sort(key=lambda item: item.last_seen, reverse=True)
            result = []
            for item in records:
                data = self._as_dict(item, now)
                data["online"] = (
                    item.status == STATUS_APPROVED
                    and item.last_seen > 0
                    and now - item.last_seen <= self._online_timeout
                )
                result.append(data)
            return result

    def online_count(self) -> int:
        return sum(1 for item in self.snapshot() if item["online"])

    def rename(self, device_id: str, alias: str) -> bool:
        with self._lock:
            record = self._records.get(device_id)
            if record is None or record.status != STATUS_APPROVED:
                return False
            record.alias = alias.strip() or record.device
            self._save()
            return True

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            record = self._records.get(device_id)
            if record is None:
                return False
            if record.status == STATUS_APPROVED:
                del self._records[device_id]
                self._save()
                return True
            return False

    def clear_all(self) -> None:
        with self._lock:
            self._records.clear()
            self._save()

    @staticmethod
    def _as_dict(item: DeviceRecord, now: float) -> dict[str, Any]:
        return {
            "device_id": item.device_id,
            "ip": item.ip,
            "user_agent": item.user_agent,
            "device": item.device,
            "first_seen": item.first_seen,
            "last_seen": item.last_seen,
            "request_count": item.request_count,
            "last_action": item.last_action,
            "status": item.status,
            "alias": item.alias,
            "approved_at": item.approved_at,
            "last_seen_ago": max(0.0, now - item.last_seen) if item.last_seen > 0 else 0.0,
        }
