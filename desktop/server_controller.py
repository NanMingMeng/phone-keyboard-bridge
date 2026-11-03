from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from phone_keyboard.config import Settings
from phone_keyboard.server import create_server


class ServerController:
    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def start(self, settings: Settings, template: str) -> tuple[bool, str | None]:
        with self._lock:
            if self._server is not None:
                return True, None
            try:
                server = create_server(settings, template)
            except OSError as error:
                return False, str(error)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            return True, None

    def stop(self) -> None:
        with self._lock:
            server = self._server
            self._server = None
            self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
