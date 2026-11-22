from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .identity import (
    CONFIDENCE_RANK,
    HIGH,
    DeviceIdentity,
    compute_identity,
    ua_client,
    ua_family,
)

ONLINE_TIMEOUT_SECONDS = 15.0
SAVE_THROTTLE_SECONDS = 30.0
# 一台设备可能同时被手机浏览器、App WebView、App 后台心跳访问，留够余量
MAX_DEVICE_IDS = 8

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
    identity: str = ""
    identity_confidence: str = ""
    identity_detail: str = ""
    device_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.device_ids:
            self.device_ids = [self.device_id]
        elif self.device_id not in self.device_ids:
            self.device_ids.insert(0, self.device_id)


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
        return f"{_describe_system(user_agent)} · {_describe_browser(user_agent)}"

    # ------------------------------------------------------------------ 持久化

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
            stored_ids = [
                str(value).strip()
                for value in item.get("device_ids", [])
                if isinstance(value, str) and value.strip()
            ]
            fingerprint = str(item.get("fingerprint", "")).strip()[:128]
            record = DeviceRecord(
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
                fingerprint=fingerprint,
                activate_seq=int(item.get("activate_seq", 0) or 0),
                identity=str(item.get("identity", "")).strip(),
                identity_confidence=str(item.get("identity_confidence", "")).strip(),
                identity_detail=str(item.get("identity_detail", "")).strip(),
                device_ids=stored_ids,
            )
            if not record.identity or not record.identity_confidence:
                identity = compute_identity(record.user_agent, record.fingerprint, record.ip)
                record.identity = identity.key
                record.identity_confidence = identity.confidence
                record.identity_detail = identity.detail
            self._records[device_id] = record
        # 升级后老数据里同一台设备的重复记录，加载时就地归并，不需要再点“合并重复设备”
        if self._merge_locked():
            self._save()

    def _save(self) -> None:
        approved = []
        for record in self._records.values():
            if record.status != STATUS_APPROVED:
                continue
            approved.append(
                {
                    "device_id": record.device_id,
                    "device_ids": list(record.device_ids),
                    "alias": record.alias,
                    "user_agent": record.user_agent,
                    "fingerprint": record.fingerprint,
                    "identity": record.identity,
                    "identity_confidence": record.identity_confidence,
                    "identity_detail": record.identity_detail,
                    "ip": record.ip,
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

    # ------------------------------------------------------------------ 身份查找

    def _record_for(self, device_id: str) -> DeviceRecord | None:
        """按 device_id 找记录，别名（同一台设备的其它 device_id）也算。"""
        record = self._records.get(device_id)
        if record is not None:
            return record
        for candidate in self._records.values():
            if device_id in candidate.device_ids:
                return candidate
        return None

    def _record_for_identity(self, identity: DeviceIdentity) -> DeviceRecord | None:
        """按身份找已授权记录：同一台设备换了 device_id 也要认出来。"""
        matches = [
            record
            for record in self._records.values()
            if record.status == STATUS_APPROVED and record.identity == identity.key
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.request_count, item.last_seen), reverse=True)
        return matches[0]

    @staticmethod
    def _bind_device_id(record: DeviceRecord, device_id: str) -> None:
        if device_id == record.device_id or device_id in record.device_ids:
            return
        record.device_ids.append(device_id)
        if len(record.device_ids) > MAX_DEVICE_IDS:
            # canonical id 永远保留在第一位
            record.device_ids = [record.device_ids[0]] + record.device_ids[-(MAX_DEVICE_IDS - 1):]

    @staticmethod
    def _apply_identity(record: DeviceRecord, identity: DeviceIdentity) -> None:
        if CONFIDENCE_RANK.get(identity.confidence, 0) >= CONFIDENCE_RANK.get(
            record.identity_confidence, 0
        ):
            record.identity = identity.key
            record.identity_confidence = identity.confidence
            record.identity_detail = identity.detail

    # ------------------------------------------------------------------ 访问

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
        identity = compute_identity(ua, fp, ip)
        with self._lock:
            record = self._record_for(device_id)
            adopted = False
            if record is None:
                record = self._record_for_identity(identity)
                if record is not None:
                    self._bind_device_id(record, device_id)
                    record.last_action = "自动识别为同一台设备"
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
            self._apply_identity(record, identity)
            if record.status == STATUS_DENIED and reset_denied:
                record.status = STATUS_PENDING
                record.first_seen = now
                record.last_action = "重新申请"
            elif adopted:
                record.status = STATUS_APPROVED
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
            record = self._record_for(device_id)
            if record is None:
                return False
            record.status = STATUS_APPROVED
            record.alias = alias.strip() or record.device
            record.approved_at = time.time()
            self._save()
            return True

    def deny(self, device_id: str) -> bool:
        with self._lock:
            record = self._record_for(device_id)
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
                data["online"] = self._is_online(item, now)
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
                data["online"] = self._is_online(item, now)
                result.append(data)
            return result

    def online_count(self) -> int:
        return sum(1 for item in self.snapshot() if item["online"])

    def rename(self, device_id: str, alias: str) -> bool:
        with self._lock:
            record = self._record_for(device_id)
            if record is None or record.status != STATUS_APPROVED:
                return False
            record.alias = alias.strip() or record.device
            self._save()
            return True

    def request_activation(self, device_id: str) -> bool:
        with self._lock:
            record = self._record_for(device_id)
            if record is None or record.status != STATUS_APPROVED:
                return False
            record.activate_seq += 1
            record.last_action = "电脑唤醒打字界面"
            self._save()
            return True

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            record = self._record_for(device_id)
            if record is None:
                return False
            if record.status == STATUS_APPROVED:
                del self._records[record.device_id]
                self._save()
                return True
            return False

    # ------------------------------------------------------------------ 重复合并

    def _duplicate_groups(self) -> list[list[DeviceRecord]]:
        """按设备身份分组，同一台设备的多个 device_id 记录归到一组。"""
        groups: dict[str, list[DeviceRecord]] = {}
        for record in self._records.values():
            if record.status != STATUS_APPROVED:
                continue
            key = record.identity or compute_identity(
                record.user_agent, record.fingerprint, record.ip
            ).key
            groups.setdefault(key, []).append(record)
        result = []
        for records in groups.values():
            if len(records) < 2:
                continue
            prints = {item.fingerprint for item in records if item.fingerprint}
            if len(prints) == len(records) and not any(
                _same_model(item) for item in records
            ):
                # 每条都有指纹且互不相同，机型也不同：是不同设备，不能合并
                continue
            result.append(records)
        return result

    def duplicate_count(self) -> int:
        with self._lock:
            return sum(len(records) - 1 for records in self._duplicate_groups())

    def merge_duplicates(self) -> int:
        with self._lock:
            merged = self._merge_locked()
            if merged:
                self._save()
            return merged

    def _merge_locked(self) -> int:
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
                for device_id in extra.device_ids:
                    self._bind_device_id(keep, device_id)
                self._records.pop(extra.device_id, None)
                merged += 1
        return merged

    def clear_all(self) -> None:
        with self._lock:
            self._records.clear()
            self._save()

    # ------------------------------------------------------------------ 工具

    def _is_online(self, record: DeviceRecord, now: float) -> bool:
        return (
            record.status == STATUS_APPROVED
            and record.last_seen > 0
            and now - record.last_seen <= self._online_timeout
        )

    @staticmethod
    def _as_dict(item: DeviceRecord, now: float) -> dict[str, Any]:
        return {
            "device_id": item.device_id,
            "device_ids": list(item.device_ids),
            "identity": item.identity,
            "identity_confidence": item.identity_confidence,
            "identity_detail": item.identity_detail,
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


def _same_model(record: DeviceRecord) -> bool:
    """记录是否已经拿到机型级身份（high）。"""
    return record.identity_confidence == HIGH


def _describe_system(user_agent: str) -> str:
    family = ua_family(user_agent)
    return {
        "android": "Android",
        "ios": "iPhone" if "iPhone" in (user_agent or "") else "iPad",
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux",
    }.get(family, "未知设备")


def _describe_browser(user_agent: str) -> str:
    ua = user_agent or ""
    lowered = ua.lower()
    if "edg/" in lowered or "edga" in lowered:
        return "Edge"
    if "chrome/" in lowered or "crios/" in lowered:
        return "Chrome"
    if "firefox/" in lowered or "fxios/" in lowered:
        return "Firefox"
    if "safari/" in lowered:
        return "Safari"
    if ua_client(ua) in ("dalvik", "okhttp", "java", "httpclient"):
        return "App"
    if "powershell" in lowered:
        return "PowerShell"
    return "浏览器"
