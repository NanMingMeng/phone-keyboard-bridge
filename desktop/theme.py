from __future__ import annotations

import string
import winreg


LIGHT = {
    "bg": "#F6F6F6",
    "sidebar": "#FFFFFF",
    "card": "#FFFFFF",
    "text": "#171717",
    "muted": "#7A7A7A",
    "border": "#EDEDED",
    "primary": "#3482FF",
    "primary_hover": "#2F75E8",
    "primary_soft": "#EAF2FF",
    "secondary_bg": "#F2F3F5",
    "success": "#22A06B",
    "danger": "#D92D20",
    "log_bg": "#F7F7F8",
}

DARK = {
    "bg": "#0E0E10",
    "sidebar": "#171719",
    "card": "#1C1C1E",
    "text": "#F5F5F7",
    "muted": "#9A9A9E",
    "border": "#2C2C2E",
    "primary": "#0A84FF",
    "primary_hover": "#3B9BFF",
    "primary_soft": "#142B4A",
    "secondary_bg": "#2C2C2E",
    "success": "#30D158",
    "danger": "#FF6961",
    "log_bg": "#151517",
}


def is_dark_mode() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except OSError:
        return False


def colors_for(dark: bool) -> dict[str, str]:
    return DARK if dark else LIGHT


def build_qss(dark: bool) -> str:
    colors = colors_for(dark)
    template = string.Template(
        """
        * {
            font-family: "MiSans", "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 10.5pt;
        }
        QMainWindow, QWidget#root {
            background: $bg;
            color: $text;
        }
        QLabel { color: $text; background: transparent; }
        QFrame#sidebar {
            background: $sidebar;
            border-right: 1px solid $border;
        }
        QFrame#content { background: $bg; }
        QLabel#brand {
            color: $text;
            font-size: 18pt;
            font-weight: 700;
        }
        QLabel#brandSub {
            color: $muted;
            font-size: 9pt;
        }
        QLabel#h1 {
            color: $text;
            font-size: 20pt;
            font-weight: 700;
        }
        QLabel#h2 {
            color: $text;
            font-size: 12pt;
            font-weight: 600;
        }
        QLabel#body { color: $text; }
        QLabel#muted {
            color: $muted;
            font-size: 9.5pt;
        }
        QLabel#statusTitle {
            color: $text;
            font-size: 15pt;
            font-weight: 650;
        }
        QLabel#statusHint {
            color: $muted;
            font-size: 9.5pt;
        }
        QLabel#pill {
            color: $primary;
            background: $primary_soft;
            border-radius: 10px;
            padding: 3px 10px;
            font-size: 9pt;
        }
        QFrame#card {
            background: $card;
            border: 1px solid $border;
            border-radius: 20px;
        }
        QPushButton#nav {
            text-align: left;
            padding: 10px 14px;
            border: 0;
            border-radius: 14px;
            color: $muted;
            background: transparent;
        }
        QPushButton#nav:hover {
            background: $primary_soft;
            color: $text;
        }
        QPushButton#nav:checked {
            background: $primary_soft;
            color: $primary;
            font-weight: 600;
        }
        QPushButton#primary {
            background: $primary;
            color: #FFFFFF;
            border: 0;
            border-radius: 14px;
            padding: 11px 18px;
            min-height: 22px;
            font-weight: 600;
        }
        QPushButton#primary:hover { background: $primary_hover; }
        QPushButton#primary:disabled {
            background: $border;
            color: $muted;
        }
        QPushButton#secondary {
            background: $secondary_bg;
            color: $text;
            border: 0;
            border-radius: 14px;
            padding: 10px 14px;
            min-height: 22px;
        }
        QPushButton#secondary:hover {
            color: $primary;
            background: $primary_soft;
        }
        QPushButton#danger {
            background: transparent;
            color: $danger;
            border: 1px solid $border;
            border-radius: 14px;
            padding: 9px 14px;
            min-height: 22px;
        }
        QPushButton#danger:hover {
            border-color: $danger;
            background: $primary_soft;
        }
        QLineEdit, QSpinBox {
            background: $secondary_bg;
            color: $text;
            border: 1px solid transparent;
            border-radius: 12px;
            padding: 8px 10px;
            min-height: 22px;
            selection-background-color: $primary;
            selection-color: #FFFFFF;
        }
        QLineEdit:focus, QSpinBox:focus { border: 1px solid $primary; }
        QCheckBox {
            color: $text;
            spacing: 8px;
        }
        QPlainTextEdit#logView {
            background: $log_bg;
            color: $text;
            border: 1px solid $border;
            border-radius: 14px;
            padding: 10px;
            font-family: "Cascadia Mono", "Consolas", monospace;
            font-size: 9.5pt;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: $border;
            border-radius: 5px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: $muted; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QToolTip {
            background: $card;
            color: $text;
            border: 1px solid $border;
            padding: 6px;
        }
        """
    )
    return template.safe_substitute(colors)
