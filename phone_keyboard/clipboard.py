from __future__ import annotations

import ctypes
import io
import os
import struct
import time
from pathlib import Path

import pyperclip
from PIL import Image


def copy_text(text: str) -> None:
    last_error: Exception | None = None
    for _ in range(6):
        try:
            pyperclip.copy(text)
            return
        except Exception as error:
            last_error = error
            time.sleep(0.12)
    raise RuntimeError(f"Clipboard write failed: {last_error}")


def paste_text(text: str, press_enter: bool = False) -> None:
    _require_windows("Text paste")
    copy_text(text)
    time.sleep(0.12)
    _send_ctrl_v()
    if press_enter:
        time.sleep(0.15)
        _send_enter()


def copy_image_to_clipboard(path: Path) -> None:
    _require_windows("Image clipboard")
    image = Image.open(path)
    image = image.convert("RGB")
    image.thumbnail((2200, 2200))
    output = io.BytesIO()
    image.save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    CF_DIB = 8
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    if not user32.OpenClipboard(None):
        raise RuntimeError("Cannot open the Windows clipboard")
    try:
        user32.EmptyClipboard()
        size = len(data)
        hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
        if not hmem:
            raise RuntimeError("Cannot allocate clipboard memory")
        ptr = kernel32.GlobalLock(hmem)
        if not ptr:
            raise RuntimeError("Cannot lock clipboard memory")
        ctypes.memmove(ptr, data, size)
        kernel32.GlobalUnlock(hmem)
        if not user32.SetClipboardData(CF_DIB, hmem):
            raise RuntimeError("Cannot write image to the Windows clipboard")
    finally:
        user32.CloseClipboard()


def paste_image(path: Path) -> None:
    _require_windows("Image paste")
    copy_image_to_clipboard(path)
    time.sleep(0.12)
    _send_ctrl_v()


def copy_files_to_clipboard(paths: list[Path]) -> None:
    _require_windows("File clipboard")
    files = [str(path.resolve()) for path in paths]
    if not files:
        raise RuntimeError("No files to copy")
    data = "\0".join(files) + "\0\0"
    payload = struct.pack("<IiiII", 20, 0, 0, 0, 1) + data.encode("utf-16le")

    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    if not user32.OpenClipboard(None):
        raise RuntimeError("Cannot open the Windows clipboard")
    try:
        user32.EmptyClipboard()
        size = len(payload)
        hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
        if not hmem:
            raise RuntimeError("Cannot allocate clipboard memory")
        ptr = kernel32.GlobalLock(hmem)
        if not ptr:
            raise RuntimeError("Cannot lock clipboard memory")
        ctypes.memmove(ptr, payload, size)
        kernel32.GlobalUnlock(hmem)
        if not user32.SetClipboardData(CF_HDROP, hmem):
            raise RuntimeError("Cannot write files to the Windows clipboard")
    finally:
        user32.CloseClipboard()


def paste_files(paths: list[Path]) -> None:
    _require_windows("File paste")
    copy_files_to_clipboard(paths)
    time.sleep(0.12)
    _send_ctrl_v()


def _require_windows(action: str) -> None:
    if os.name != "nt":
        raise RuntimeError(f"{action} is only supported on Windows. Use copy/save mode instead.")


def _send_ctrl_v() -> None:
    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL = 0x11
    VK_V = 0x56
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def _send_enter() -> None:
    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_RETURN = 0x0D
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
