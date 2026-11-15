from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ONLINE_TIMEOUT_SECONDS = 15.0
SAVE_THROTTLE_SECONDS = 30.0

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
    fingerprint: str = ""
    activate_seq: int = 0


class DeviceRegistry:
    def __init__(self, storage_path: Path, online_timeout: float = ONLINE_TIMEOUT_SECONDS) -> None:
        self._storage_path = storage_path
        self._online_timeout = online_timeout
        self._records: dict[str, DeviceRecord] = {}
        self._lock = threading.Lock()
        self._last_save = 0.0
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
            approved_at = float(item.get("approved_at", 0.0) or 0.0)
            first_seen = float(item.get("first_seen", 0.0) or 0.0) or approved_at or now
            last_seen = float(item.get("last_seen", 0.0) or 0.0)
            self._records[device_id] = DeviceRecord(
                device_id=device_id,
                ip=str(item.get("ip", "")),
                user_agent=ua,
                device=self.describe_user_agent(ua),
                first_seen=first_seen,
                last_seen=last_seen,
                request_count=int(item.get("request_count", 0) or 0),
                last_action=str(item.get("last_action", "")),
                status=STATUS_APPROVED,
                alias=str(item.get("alias", "")).strip(),
                approved_at=approved_at,
                fingerprint=str(item.get("fingerprint", "")).strip()[:128],
                activate_seq=int(item.get("activate_seq", 0) or 0),
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
                    "fingerprint": record.fingerprint,
                    "first_seen": record.first_seen,
                    "last_seen": record.last_seen,
                    "request_count": record.request_count,
                    "last_action": record.last_action,
                    "approved_at": record.approved_at,
                    "activate_seq": record.activate_seq,
                }
            )
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps({"devices": approved}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._last_save = time.time()

    def _find_by_fingerprint(self, fingerprint: str) -> DeviceRecord | None:
        if not fingerprint:
            return None
        matches = [
            record
            for record in self._records.values()
            if record.status == STATUS_APPROVED and record.fingerprint == fingerprint
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.request_count, item.last_seen), reverse=True)
        return matches[0]

    def touch(
        self,
        device_id: str,
        ip: str,
        user_agent: str,
        action: str | None = None,
        reset_denied: bool = False,
        fingerprint: str = "",
    ) -> str:
        now = time.time()
        ua = (user_agent or "")[:300]
        fp = (fingerprint or "").strip()[:128]
        with self._lock:
            record = self._records.get(device_id)
            adopted = False
            if record is None and fp:
                record = self._find_by_fingerprint(fp)
                if record is not None:
                    self._records.pop(record.device_id, None)
                    record.device_id = device_id
                    self._records[device_id] = record
                    record.last_action = "自动识别为已授权设备"
                    adopted = True
            if record is None:
                record = DeviceRecord(
                    device_id=device_id,
                    ip=ip,
                    user_agent=ua,
                    device=self.describe_user_agent(ua),
                    first_seen=now,
                    last_seen=now,
                    fingerprint=fp,
                )
                self._records[device_id] = record
            record.ip = ip
            record.user_agent = ua
            record.device = self.describe_user_agent(ua)
            record.last_seen = now
            if fp:
                record.fingerprint = fp
            if record.status == STATUS_DENIED and reset_denied:
                record.status = STATUS_PENDING
                record.first_seen = now
                record.last_action = "重新申请"
            if action:
                record.request_count += 1
                record.last_action = action
            if adopted or (
                record.status == STATUS_APPROVED and now - self._last_save >= SAVE_THROTTLE_SECONDS
            ):
                self._save()
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

    def request_activation(self, device_id: str) -> bool:
        with self._lock:
            record = self._records.get(device_id)
            if record is None or record.status != STATUS_APPROVED:
                return False
            record.activate_seq += 1
            record.last_action = "电脑唤醒打字界面"
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

    def _duplicate_groups(self) -> list[list[DeviceRecord]]:
        groups: dict[str, list[DeviceRecord]] = {}
        for record in self._records.values():
            if record.status != STATUS_APPROVED:
                continue
            key = record.user_agent.strip() or record.fingerprint or record.device
            groups.setdefault(key, []).append(record)
        result = []
        for records in groups.values():
            if len(records) < 2:
                continue
            prints = {item.fingerprint for item in records if item.fingerprint}
            if len(prints) == len(records):
                # 每条都有指纹且互不相同，说明是不同设备，不能合并
                continue
            result.append(records)
        return result

    def duplicate_count(self) -> int:
        with self._lock:
            return sum(len(records) - 1 for records in self._duplicate_groups())

    def merge_duplicates(self) -> int:
        with self._lock:
            merged = 0
            for records in self._duplicate_groups():
                records.sort(
                    key=lambda item: (item.request_count, item.last_seen, item.approved_at),
                    reverse=True,
                )
                keep = records[0]
                for extra in records[1:]:
                    keep.request_count += extra.request_count
                    if extra.last_seen > keep.last_seen:
                        keep.last_seen = extra.last_seen
                        keep.ip = extra.ip or keep.ip
                    if extra.last_action:
                        keep.last_action = extra.last_action
                    if extra.approved_at and (
                        not keep.approved_at or extra.approved_at < keep.approved_at
                    ):
                        keep.approved_at = extra.approved_at
                    if not keep.alias or keep.alias == keep.device:
                        keep.alias = extra.alias or keep.alias
                    if not keep.fingerprint and extra.fingerprint:
                        keep.fingerprint = extra.fingerprint
                    self._records.pop(extra.device_id, None)
                    merged += 1
            if merged:
                self._save()
            return merged

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
            "fingerprint": item.fingerprint,
            "activate": item.activate_seq,
            "last_seen_ago": max(0.0, now - item.last_seen) if item.last_seen > 0 else 0.0,
        }
