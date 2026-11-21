from __future__ import annotations

import logging
import ssl
import threading
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

from phone_keyboard.certs import ensure_certificates
from phone_keyboard.cli import find_lan_ip
from phone_keyboard.config import Settings
from phone_keyboard.connections import DeviceRegistry
from phone_keyboard.records import RecordStore
from phone_keyboard.server import create_server

LOGGER = logging.getLogger("phone_keyboard.controller")


class ServerController:
    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._https_server: ThreadingHTTPServer | None = None
        self._https_thread: threading.Thread | None = None
        self._registry: DeviceRegistry | None = None
        self._records: RecordStore | None = None
        self._lock = threading.Lock()
        self.https_port: int = 0
        self.ca_cert: Path | None = None

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def https_running(self) -> bool:
        return self._https_server is not None

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

    def duplicate_device_count(self) -> int:
        return self._registry.duplicate_count() if self._registry is not None else 0

    def merge_duplicate_devices(self) -> int:
        return self._registry.merge_duplicates() if self._registry is not None else 0

    def activate_device(self, device_id: str) -> bool:
        return self._registry.request_activation(device_id) if self._registry is not None else False

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

    def _build_ssl_context(self, settings: Settings) -> ssl.SSLContext | None:
        try:
            cert_dir = settings.data_dir / "certs"
            ca_cert, server_cert, server_key = ensure_certificates(
                cert_dir, [find_lan_ip(), "127.0.0.1"]
            )
        except Exception as error:
            LOGGER.warning("HTTPS 证书生成失败，仅使用 HTTP：%s", error)
            return None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            context.load_cert_chain(certfile=str(server_cert), keyfile=str(server_key))
        except Exception as error:
            LOGGER.warning("HTTPS 证书加载失败，仅使用 HTTP：%s", error)
            return None
        self.ca_cert = ca_cert
        return context

    def start(self, settings: Settings, template: str) -> tuple[bool, str | None]:
        with self._lock:
            if self._server is not None:
                return True, None
            https_port = int(settings.port) + 1
            ssl_context = self._build_ssl_context(settings)
            http_settings = replace(
                settings,
                https_port=https_port if ssl_context is not None else 0,
                ca_cert=self.ca_cert,
            )
            try:
                registry = DeviceRegistry(settings.data_dir / "approved_devices.json")
                records = RecordStore(settings.data_dir / "records.json")
                server = create_server(http_settings, template, registry, records)
            except OSError as error:
                return False, str(error)

            https_server: ThreadingHTTPServer | None = None
            if ssl_context is not None:
                https_settings = replace(http_settings, port=https_port)
                try:
                    https_server = create_server(
                        https_settings, template, registry, records, ssl_context=ssl_context
                    )
                except OSError as error:
                    LOGGER.warning("HTTPS 端口 %s 启动失败：%s", https_port, error)
                    https_server = None

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            if https_server is not None:
                https_thread = threading.Thread(target=https_server.serve_forever, daemon=True)
                https_thread.start()
                self._https_server = https_server
                self._https_thread = https_thread
                self.https_port = https_port
            else:
                self._https_server = None
                self._https_thread = None
                self.https_port = 0
            self._registry = registry
            self._records = records
            return True, None

    def stop(self) -> None:
        with self._lock:
            server = self._server
            https_server = self._https_server
            self._server = None
            self._thread = None
            self._https_server = None
            self._https_thread = None
            self._registry = None
            self._records = None
            self.https_port = 0
        if https_server is not None:
            https_server.shutdown()
            https_server.server_close()
        if server is not None:
            server.shutdown()
            server.server_close()
