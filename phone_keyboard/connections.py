from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


ONLINE_TIMEOUT_SECONDS = 15.0


@dataclass
class ConnectionRecord:
    key: str
    ip: str
    user_agent: str
    device: str
    first_seen: float
    last_seen: float
    request_count: int = 0
    last_action: str = ""


class ConnectionTracker:
    def __init__(self, online_timeout: float = ONLINE_TIMEOUT_SECONDS) -> None:
        self._online_timeout = online_timeout
        self._records: dict[str, ConnectionRecord] = {}
        self._lock = threading.Lock()

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

    def touch(self, ip: str, user_agent: str, action: str | None = None) -> None:
        now = time.time()
        ua = (user_agent or "")[:300]
        key = f"{ip}|{ua}"
        with self._lock:
            record = self._records.get(key)
            if record is None:
                record = ConnectionRecord(
                    key=key,
                    ip=ip,
                    user_agent=ua,
                    device=self.describe_user_agent(ua),
                    first_seen=now,
                    last_seen=now,
                )
                self._records[key] = record
            record.last_seen = now
            if action:
                record.request_count += 1
                record.last_action = action

    def snapshot(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            records = sorted(self._records.values(), key=lambda item: item.last_seen, reverse=True)
            return [
                {
                    "key": item.key,
                    "ip": item.ip,
                    "user_agent": item.user_agent,
                    "device": item.device,
                    "first_seen": item.first_seen,
                    "last_seen": item.last_seen,
                    "request_count": item.request_count,
                    "last_action": item.last_action,
                    "online": now - item.last_seen <= self._online_timeout,
                    "last_seen_ago": max(0.0, now - item.last_seen),
                }
                for item in records
            ]

    def online_count(self) -> int:
        return sum(1 for item in self.snapshot() if item["online"])
