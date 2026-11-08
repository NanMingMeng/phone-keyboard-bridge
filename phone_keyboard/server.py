from __future__ import annotations

import datetime
import json
import logging
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .clipboard import copy_text, paste_files, paste_image, paste_text
from .config import Settings
from .connections import STATUS_APPROVED, DeviceRegistry
from .records import RecordStore

LOGGER = logging.getLogger("phone_keyboard.server")
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_TEXT_BYTES = 512 * 1024
MAX_FILE_BYTES = 100 * 1024 * 1024


def safe_image_stem(name: str) -> str:
    stem = re.sub(r"[^0-9A-Za-z_-]+", "_", Path(name).stem)[:40].strip("_")
    return stem or "image"


def safe_file_name(name: str) -> str:
    filename = Path(name).name
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", filename).strip(" .")
    if not filename:
        return "file"
    stem = Path(filename).stem[:80].strip(" .") or "file"
    suffix = Path(filename).suffix[:16]
    return f"{stem}{suffix}"


def make_handler(settings: Settings, template: str, registry: DeviceRegistry, records: RecordStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"PhoneKeyboardBridge/{settings.version}"

        def log_message(self, fmt: str, *args: Any) -> None:
            LOGGER.info("%s - %s", self.address_string(), fmt % args)

        def _send_json(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            return self.headers.get("X-Token") == settings.token

        def _client_ip(self) -> str:
            return str(self.client_address[0])

        def _device_id(self) -> str | None:
            value = self.headers.get("X-Device-Id", "").strip()
            if not value or len(value) > 128:
                return None
            return value

        def _device_state(self, action: str | None = None, reset_denied: bool = False) -> str | None:
            device_id = self._device_id()
            if device_id is None:
                return None
            return registry.touch(
                device_id,
                self._client_ip(),
                self.headers.get("User-Agent", ""),
                action=action,
                reset_denied=reset_denied,
            )

        def _session_payload(self, state: str) -> dict[str, Any]:
            device_id = self._device_id() or ""
            for item in registry.snapshot():
                if item["device_id"] == device_id:
                    return {
                        "ok": True,
                        "state": state,
                        "device_id": device_id,
                        "device": item["device"],
                        "alias": item["alias"],
                        "ip": item["ip"],
                    }
            return {"ok": True, "state": state, "device_id": device_id}

        def _require_approved(self) -> bool:
            state = self._device_state()
            if state is None:
                self._send_json(400, {"error": "Missing device ID", "state": "missing_device"})
                return False
            if state != STATUS_APPROVED:
                self._send_json(403, {"error": "Device not approved", "state": state})
                return False
            return True

        def _read_body(self, limit: int) -> bytes:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("Empty request body")
            if length > limit:
                raise ValueError("Request body is too large")
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError("Incomplete request body")
            return data

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                query = urllib.parse.parse_qs(parsed.query)
                if query.get("t", [""])[0] != settings.token:
                    self.send_response(403)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write("Invalid link. Scan the QR code again.".encode("utf-8"))
                    return
                body = (
                    template
                    .replace("__TOKEN__", json.dumps(settings.token))
                    .replace("__VERSION__", settings.version)
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/ping":
                self._send_json(200, {"ok": True, "version": settings.version})
                return
            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:
            if self.path == "/session":
                self._handle_session("申请连接", reset_denied=False)
                return
            if self.path == "/request-access":
                self._handle_session("重新申请", reset_denied=True)
                return
            if self.path == "/heartbeat":
                self._handle_session(None, reset_denied=False)
                return
            if self.path == "/send":
                self._handle_text()
                return
            if self.path == "/send-image":
                self._handle_image()
                return
            if self.path == "/send-file":
                self._handle_file()
                return
            self._send_json(404, {"error": "Not found"})

        def _handle_session(self, action: str | None, reset_denied: bool) -> None:
            if not self._authorized():
                self._send_json(403, {"error": "Invalid link", "state": "invalid_link"})
                return
            if self._device_id() is None:
                self._send_json(400, {"error": "Missing device ID", "state": "missing_device"})
                return
            state = self._device_state(action=action, reset_denied=reset_denied)
            self._send_json(200, self._session_payload(str(state)))

        def _handle_text(self) -> None:
            if not self._authorized():
                self._send_json(403, {"error": "Invalid link", "state": "invalid_link"})
                return
            if not self._require_approved():
                return
            try:
                payload = json.loads(self._read_body(MAX_TEXT_BYTES).decode("utf-8"))
                text = payload.get("text", "")
                mode = payload.get("mode", "paste")
                press_enter = bool(payload.get("enter", False))
                if not isinstance(text, str) or not text.strip():
                    self._send_json(400, {"error": "Text is empty"})
                    return
                if mode == "copy":
                    try:
                        copy_text(text)
                    except Exception as error:
                        records.add_text(text, "复制文字", False, str(error))
                        raise
                    self._device_state("复制文字")
                    records.add_text(text, "复制文字", True)
                    self._send_json(200, {"ok": True, "copied": True})
                    return
                if mode != "paste":
                    self._send_json(400, {"error": "Invalid mode"})
                    return
                try:
                    paste_text(text, press_enter=press_enter)
                except Exception as error:
                    records.add_text(text, "粘贴文字", False, str(error))
                    raise
                self._device_state("粘贴文字")
                records.add_text(text, "粘贴文字", True)
                self._send_json(200, {"ok": True, "pasted": True})
            except RuntimeError as error:
                self._send_json(501, {"error": str(error)})
            except Exception as error:
                LOGGER.exception("Text send failed")
                self._send_json(500, {"error": f"Text send failed: {error}"})

        def _handle_file(self) -> None:
            if not self._authorized():
                self._send_json(403, {"error": "Invalid link", "state": "invalid_link"})
                return
            if not self._require_approved():
                return
            try:
                raw_name = urllib.parse.unquote(self.headers.get("X-Filename", "file"))
                safe_name = Path(raw_name).name or "file"
                mode = self.headers.get("X-Mode", "paste")
                if mode not in ("paste", "save"):
                    self._send_json(400, {"error": "Invalid mode"})
                    return
                data = self._read_body(MAX_FILE_BYTES)
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                filename = safe_file_name(safe_name)
                path = settings.data_dir / "files" / f"{stamp}-{filename}"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                if mode == "save":
                    self._device_state("保存文件")
                    records.add_file(path, "保存文件", True)
                    self._send_json(200, {"ok": True, "saved": True, "pasted": False, "path": str(path)})
                    return
                try:
                    paste_files([path])
                except RuntimeError as error:
                    self._device_state("粘贴文件")
                    records.add_file(path, "粘贴文件", False, str(error))
                    self._send_json(200, {"ok": True, "saved": True, "pasted": False, "path": str(path), "warning": str(error)})
                    return
                self._device_state("粘贴文件")
                records.add_file(path, "粘贴文件", True)
                self._send_json(200, {"ok": True, "saved": True, "pasted": True, "path": str(path)})
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
            except Exception as error:
                LOGGER.exception("File send failed")
                self._send_json(500, {"error": f"File send failed: {error}"})

        def _handle_image(self) -> None:
            if not self._authorized():
                self._send_json(403, {"error": "Invalid link", "state": "invalid_link"})
                return
            if not self._require_approved():
                return
            try:
                raw_name = urllib.parse.unquote(self.headers.get("X-Filename", "image"))
                suffix = Path(raw_name).suffix.lower()
                if suffix not in ALLOWED_IMAGE_SUFFIXES:
                    self._send_json(400, {"error": "Unsupported image format"})
                    return
                mode = self.headers.get("X-Mode", "paste")
                if mode not in ("paste", "save"):
                    self._send_json(400, {"error": "Invalid mode"})
                    return
                data = self._read_body(MAX_IMAGE_BYTES)
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                filename = f"{stamp}-{safe_image_stem(raw_name)}{suffix}"
                path = settings.image_dir / filename
                path.write_bytes(data)

                if mode == "save":
                    self._device_state("保存图片")
                    records.add_image(path, "保存图片", True)
                    self._send_json(200, {"ok": True, "saved": True, "pasted": False, "path": str(path)})
                    return
                try:
                    paste_image(path)
                except RuntimeError as error:
                    self._device_state("粘贴图片")
                    records.add_image(path, "粘贴图片", False, str(error))
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "saved": True,
                            "pasted": False,
                            "path": str(path),
                            "warning": str(error),
                        },
                    )
                    return
                self._device_state("粘贴图片")
                records.add_image(path, "粘贴图片", True)
                self._send_json(200, {"ok": True, "saved": True, "pasted": True, "path": str(path)})
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
            except Exception as error:
                LOGGER.exception("Image send failed")
                self._send_json(500, {"error": f"Image send failed: {error}"})

    return Handler


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_server(
    settings: Settings,
    template: str,
    registry: DeviceRegistry,
    records: RecordStore,
) -> ThreadingHTTPServer:
    handler = make_handler(settings, template, registry, records)
    server = _Server((settings.host, settings.port), handler)
    server.registry = registry
    server.records = records
    return server


def run_server(settings: Settings, template: str) -> None:
    registry = DeviceRegistry(settings.data_dir / "approved_devices.json")
    records = RecordStore(settings.data_dir / "records.json")
    server = create_server(settings, template, registry, records)
    LOGGER.info("Listening on %s:%s", settings.host, settings.port)
    server.serve_forever()
