from __future__ import annotations

import datetime
import json
import logging
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .clipboard import copy_text, paste_image, paste_text
from .config import Settings

LOGGER = logging.getLogger("phone_keyboard.server")
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_TEXT_BYTES = 512 * 1024


def safe_image_stem(name: str) -> str:
    stem = re.sub(r"[^0-9A-Za-z_-]+", "_", Path(name).stem)[:40].strip("_")
    return stem or "image"


def make_handler(settings: Settings, template: str):
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
            if self.path == "/send":
                self._handle_text()
                return
            if self.path == "/send-image":
                self._handle_image()
                return
            self._send_json(404, {"error": "Not found"})

        def _handle_text(self) -> None:
            if not self._authorized():
                self._send_json(403, {"error": "Invalid link"})
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
                    copy_text(text)
                    self._send_json(200, {"ok": True, "copied": True})
                    return
                if mode != "paste":
                    self._send_json(400, {"error": "Invalid mode"})
                    return
                paste_text(text, press_enter=press_enter)
                self._send_json(200, {"ok": True, "pasted": True})
            except RuntimeError as error:
                self._send_json(501, {"error": str(error)})
            except Exception as error:
                LOGGER.exception("Text send failed")
                self._send_json(500, {"error": f"Text send failed: {error}"})

        def _handle_image(self) -> None:
            if not self._authorized():
                self._send_json(403, {"error": "Invalid link"})
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
                    self._send_json(200, {"ok": True, "saved": True, "pasted": False, "path": str(path)})
                    return
                try:
                    paste_image(path)
                    self._send_json(200, {"ok": True, "saved": True, "pasted": True, "path": str(path)})
                except RuntimeError as error:
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
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
            except Exception as error:
                LOGGER.exception("Image send failed")
                self._send_json(500, {"error": f"Image send failed: {error}"})

    return Handler


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_server(settings: Settings, template: str) -> None:
    handler = make_handler(settings, template)
    server = _Server((settings.host, settings.port), handler)
    LOGGER.info("Listening on %s:%s", settings.host, settings.port)
    server.serve_forever()
