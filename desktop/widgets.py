from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .icons import svg_icon


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(30)
        self._shadow.setOffset(0, 8)
        self.setGraphicsEffect(self._shadow)

    def set_dark(self, dark: bool) -> None:
        self._shadow.setColor(QColor(0, 0, 0, 80 if dark else 18))


class StatusDot(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(10, 10)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background: {color}; border-radius: 5px;")


class NavButton(QPushButton):
    def __init__(self, icon_name: str, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.icon_name = icon_name
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(42)

    def set_icon_color(self, color: str) -> None:
        self.setIcon(svg_icon(self.icon_name, color, 18))


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("h1")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("muted")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)


class Row(QWidget):
    def __init__(self, left: QWidget, right: QWidget | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(left, 1)
        if right is not None:
            layout.addWidget(right, 0, Qt.AlignmentFlag.AlignRight)


class ToggleSwitch(QAbstractButton):
    """HyperOS-style pill switch."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dark = False
        self._offset = 27.0 if self.isChecked() else 3.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(27.0 if checked else 3.0)
        self._anim.start()

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = pyqtProperty(float, fget=get_offset, fset=set_offset)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0, 2, 46, 22)
        if self.isChecked():
            color = QColor("#3482FF" if not self._dark else "#0A84FF")
        else:
            color = QColor("#E5E5E7" if not self._dark else "#3A3A3C")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(track, 11, 11)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(self._offset, 5, 16, 16))
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(46, 26)
