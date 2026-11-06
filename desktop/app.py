from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow, resource_path


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PKB")
    app.setApplicationDisplayName("PKB")
    app.setOrganizationName("NanMingMeng")
    app.setQuitOnLastWindowClosed(False)

    icon_path = resource_path("assets/icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    return app.exec()
