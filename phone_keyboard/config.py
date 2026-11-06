from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "PhoneKeyboardBridge"
VERSION = "0.2.1"
TOKEN_BYTES = 12


def default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
    return Path.home() / ".phone-keyboard-bridge"


def ensure_data_dir(path: Path) -> Path:
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    (path / "images").mkdir(exist_ok=True)
    (path / "logs").mkdir(exist_ok=True)
    return path


def load_or_create_token(data_dir: Path) -> str:
    token_file = data_dir / "token.txt"
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(TOKEN_BYTES)
    token_file.write_text(token + "\n", encoding="utf-8")
    return token


def package_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "phone_keyboard"
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    token: str
    image_dir: Path
    log_file: Path
    template_file: Path
    version: str = VERSION
