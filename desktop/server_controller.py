from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from phone_keyboard.config import Settings
from phone_keyboard.connections import DeviceRegistry
from phone_keyboard.records import RecordStore
from phone_keyboard.server import create_server


class ServerController:
    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._registry: DeviceRegistry | None = None
        self._records: RecordStore | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def online_count(self) -> int:
        return self._registry.online_count() if self._registry is not None else 0

    def connections(self) -> list[dict[str, object]]:
        return self._registry.snapshot() if self._registry is not None else []

    def pending_requests(self) -> list[dict[str, object]]:
        return self._registry.pending() if self._registry is not None else []

    def approved_devices(self) -> list[dict[str, object]]:
        return self._registry.approved() if self._registry is not None else []

    def approve_device(self, device_id: str, alias: str) -> bool:
        return self._registry.approve(device_id, alias) if self._registry is not None else False

    def deny_device(self, device_id: str) -> bool:
        return self._registry.deny(device_id) if self._registry is not None else False

    def rename_device(self, device_id: str, alias: str) -> bool:
        return self._registry.rename(device_id, alias) if self._registry is not None else False

    def revoke_device(self, device_id: str) -> bool:
        return self._registry.revoke(device_id) if self._registry is not None else False

    def clear_devices(self) -> None:
        if self._registry is not None:
            self._registry.clear_all()

    def records(self) -> list[dict[str, object]]:
        return self._records.records() if self._records is not None else []

    def delete_record(self, record_id: str) -> bool:
        return self._records.delete(record_id, delete_image=True) if self._records is not None else False

    def clear_records(self) -> None:
        if self._records is not None:
            self._records.clear(delete_images=True)

    def start(self, settings: Settings, template: str) -> tuple[bool, str | None]:
        with self._lock:
            if self._server is not None:
                return True, None
            try:
                registry = DeviceRegistry(settings.data_dir / "approved_devices.json")
                records = RecordStore(settings.data_dir / "records.json")
                server = create_server(settings, template, registry, records)
            except OSError as error:
                return False, str(error)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            self._registry = registry
            self._records = records
            return True, None

    def stop(self) -> None:
        with self._lock:
            server = self._server
            self._server = None
            self._thread = None
            self._registry = None
            self._records = None
        if server is not None:
            server.shutdown()
            server.server_close()
