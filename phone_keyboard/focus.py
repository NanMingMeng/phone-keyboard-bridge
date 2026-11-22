"""获取 Windows 当前前台窗口标题。

用途：手机端在「连接成功」旁边显示这次粘贴会落到哪个程序，
避免把文字/图片发到错误窗口。

非 Windows 平台（开发机）返回空字符串，不影响其它功能。
"""
from __future__ import annotations

import os

# 标题可能很长（浏览器会带整页标题），截断避免撑破手机端布局
MAX_TITLE_LEN = 80


def foreground_title() -> str:
    """返回当前前台窗口标题；拿不到时返回空串。"""
    if os.name != "nt":
        return ""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").strip()
        return title[:MAX_TITLE_LEN]
    except Exception:
        return ""
