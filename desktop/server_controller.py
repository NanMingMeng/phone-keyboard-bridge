from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from phone_keyboard.config import Settings
from phone_keyboard.connections import ConnectionTracker
from phone_keyboard.server import create_server


class ServerController:
    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._tracker: ConnectionTracker | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def online_count(self) -> int:
        tracker = self._tracker
        return tracker.online_count() if tracker is not None else 0

    def connections(self) -> list[dict[str, object]]:
        tracker = self._tracker
        return tracker.snapshot() if tracker is not None else []

    def start(self, settings: Settings, template: str) -> tuple[bool, str | None]:
        with self._lock:
            if self._server is not None:
                return True, None
            try:
                tracker = ConnectionTracker()
                server = create_server(settings, template, tracker)
            except OSError as error:
                return False, str(error)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            self._tracker = tracker
            return True, None

    def stop(self) -> None:
        with self._lock:
            server = self._server
            self._server = None
            self._thread = None
            self._tracker = None
        if server is not None:
            server.shutdown()
            server.server_close()
