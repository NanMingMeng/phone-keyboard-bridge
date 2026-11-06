from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DeviceApprovalDialog(QDialog):
    TIMEOUT_SECONDS = 60

    def __init__(self, request: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.request = request
        self.auto_denied = False
        self.remaining = self.TIMEOUT_SECONDS
        self.setWindowTitle("新的设备请求连接")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)

        title = QLabel("有一台新设备想连接 PKB")
        title.setObjectName("h2")
        layout.addWidget(title)

        device = QLabel(str(request.get("device", "未知设备")))
        device.setObjectName("statusTitle")
        layout.addWidget(device)

        detail = QLabel(f"IP 地址：{request.get('ip', '未知')}")
        detail.setObjectName("muted")
        layout.addWidget(detail)

        alias_label = QLabel("给这台设备起个名字")
        alias_label.setObjectName("body")
        layout.addWidget(alias_label)

        self.alias_edit = QLineEdit()
        self.alias_edit.setText(str(request.get("alias") or "我的手机"))
        self.alias_edit.selectAll()
        layout.addWidget(self.alias_edit)

        self.countdown = QLabel()
        self.countdown.setObjectName("muted")
        layout.addWidget(self.countdown)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        deny = QPushButton("拒绝")
        deny.setObjectName("secondary")
        deny.setCursor(Qt.CursorShape.PointingHandCursor)
        deny.clicked.connect(self.reject)
        allow = QPushButton("允许连接")
        allow.setObjectName("primary")
        allow.setCursor(Qt.CursorShape.PointingHandCursor)
        allow.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(deny)
        buttons.addWidget(allow)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._update_countdown()

    @property
    def alias(self) -> str:
        return self.alias_edit.text().strip() or "我的手机"

    def _update_countdown(self) -> None:
        self.countdown.setText(f"{self.remaining} 秒内未处理会自动拒绝")

    def _tick(self) -> None:
        self.remaining -= 1
        if self.remaining <= 0:
            self.auto_denied = True
            self.timer.stop()
            self.reject()
            return
        self._update_countdown()
