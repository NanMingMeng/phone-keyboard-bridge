from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from phone_keyboard.config import default_data_dir


APP_NAME = "PKB"
DEFAULT_PORT = 3004


def ui_config_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".pkb"


def ui_config_path() -> Path:
    return ui_config_dir() / "ui.json"


def default_config() -> dict[str, Any]:
    return {
        "port": DEFAULT_PORT,
        "data_dir": str(default_data_dir()),
        "startup": True,
        "settings_version": 2,
        "tray_hint_shown": False,
        "auto_update_check": True,
        "last_update_check": 0.0,
    }


def load_config() -> dict[str, Any]:
    config = default_config()
    path = ui_config_path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                migrated = dict(stored)
                if "settings_version" not in migrated:
                    migrated["startup"] = True
                    migrated["settings_version"] = 2
                    migrated.setdefault("tray_hint_shown", False)
                    migrated.setdefault("auto_update_check", True)
                    migrated.setdefault("last_update_check", 0.0)
                config.update(migrated)
        except (OSError, json.JSONDecodeError):
            pass
    return config


def save_config(config: dict[str, Any]) -> None:
    directory = ui_config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    ui_config_path().write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def startup_folder() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        return Path.home() / "Startup"
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_cmd_path() -> Path:
    return startup_folder() / "PKB.cmd"


def set_startup(enabled: bool) -> None:
    path = startup_cmd_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            command = f'start "" "{Path(sys.executable)}"'
        else:
            python = Path(sys.executable)
            pythonw = python.with_name("pythonw.exe")
            if not pythonw.exists():
                pythonw = python
            script = Path(__file__).resolve().parent.parent / "run_desktop.py"
            command = f'start "" "{pythonw}" "{script}"'
        content = "@echo off\r\nchcp 936 >nul\r\n" + command + "\r\n"
        path.write_text(content, encoding="gbk", errors="replace")
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
