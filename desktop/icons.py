from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


_SVG = {
    "link": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9.5 14.5l5-5"/>
          <path d="M7.2 12.8l-1.7 1.7a3.7 3.7 0 0 0 5.2 5.2l1.7-1.7"/>
          <path d="M16.8 11.2l1.7-1.7a3.7 3.7 0 0 0-5.2-5.2l-1.7 1.7"/>
        </svg>
    """,
    "settings": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round">
          <path d="M4 7h16M4 12h16M4 17h16"/>
          <circle cx="9" cy="7" r="2.1" fill="white" stroke="{color}"/>
          <circle cx="15" cy="12" r="2.1" fill="white" stroke="{color}"/>
          <circle cx="8" cy="17" r="2.1" fill="white" stroke="{color}"/>
        </svg>
    """,
    "history": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4.2 11a8 8 0 1 1 2.1 6.2"/>
          <path d="M4 5v6h6"/>
          <path d="M12 7.5V12l3 2"/>
        </svg>
    """,
    "logs": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <rect x="5" y="4" width="14" height="16" rx="2.5"/>
          <path d="M8.5 9h7M8.5 12h7M8.5 15h4.5"/>
        </svg>
    """,
    "about": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="8.5"/>
          <path d="M12 10.8v5.2"/>
          <circle cx="12" cy="8" r="0.8" fill="{color}" stroke="none"/>
        </svg>
    """,
    "copy": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <rect x="8" y="8" width="10" height="11" rx="2"/>
          <path d="M6 15H5.5A1.5 1.5 0 0 1 4 13.5v-8A1.5 1.5 0 0 1 5.5 4h8A1.5 1.5 0 0 1 15 5.5V6"/>
        </svg>
    """,
    "open": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 4h6v6"/>
          <path d="M20 4l-9 9"/>
          <path d="M19 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4"/>
        </svg>
    """,
    "refresh": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 12a8 8 0 1 1-2.3-5.6"/>
          <path d="M20 4v6h-6"/>
        </svg>
    """,
    "trash": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13"/>
          <path d="M10 11v5M14 11v5"/>
        </svg>
    """,
    "power": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v9"/>
          <path d="M6.2 6.8a7.5 7.5 0 1 0 11.6 0"/>
        </svg>
    """,
    "folder": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3.5 7.5A2.5 2.5 0 0 1 6 5h4l2 2h6A2.5 2.5 0 0 1 20.5 9.5v7A2.5 2.5 0 0 1 18 19H6a2.5 2.5 0 0 1-2.5-2.5z"/>
        </svg>
    """,
    "check": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
             stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 12.5l4.2 4.2L19 7"/>
        </svg>
    """,
}


def svg_bytes(name: str, color: str) -> bytes:
    return _SVG[name].format(color=color).encode("utf-8")


def svg_pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_bytes(name, color)))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def svg_icon(name: str, color: str, size: int = 20) -> QIcon:
    return QIcon(svg_pixmap(name, color, size))
