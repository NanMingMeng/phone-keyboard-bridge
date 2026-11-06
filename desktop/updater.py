from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


RELEASE_API = "https://api.github.com/repos/NanMingMeng/phone-keyboard-bridge/releases/latest"
USER_AGENT = "PKB-Updater"


def version_tuple(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lower().lstrip("v")
    parts = []
    for part in cleaned.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def is_newer(latest: str, current: str) -> bool:
    return version_tuple(latest) > version_tuple(current)


@dataclass
class UpdateInfo:
    version: str
    tag: str
    title: str
    notes: str
    page_url: str
    download_url: str
    checksum_url: str
    size: int


def check_for_update(current_version: str, timeout: float = 12.0) -> UpdateInfo | None:
    request = urllib.request.Request(
        RELEASE_API,
        headers={"User-Agent": f"{USER_AGENT}/{current_version}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    tag = str(data.get("tag_name", ""))
    if not tag or not is_newer(tag, current_version):
        return None
    assets = data.get("assets", [])
    if not isinstance(assets, list):
        assets = []
    by_name = {str(item.get("name", "")): item for item in assets if isinstance(item, dict)}
    exe = by_name.get("PKB.exe")
    checksum = by_name.get("PKB.exe.sha256")
    if not exe or not checksum:
        raise RuntimeError("最新版本缺少 PKB.exe 或校验文件")
    return UpdateInfo(
        version=tag.lstrip("vV"),
        tag=tag,
        title=str(data.get("name") or tag),
        notes=str(data.get("body") or ""),
        page_url=str(data.get("html_url") or ""),
        download_url=str(exe.get("browser_download_url") or ""),
        checksum_url=str(checksum.get("browser_download_url") or ""),
        size=int(exe.get("size") or 0),
    )


def download_and_verify(
    info: UpdateInfo,
    output_dir: Path,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "PKB.exe"
    part = output_dir / "PKB.exe.part"
    checksum_request = urllib.request.Request(info.checksum_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(checksum_request, timeout=15) as response:
        checksum_text = response.read().decode("utf-8", errors="replace").strip()
    expected = checksum_text.split()[0].lower() if checksum_text else ""
    if len(expected) != 64:
        raise RuntimeError("发布页校验文件格式不正确")

    request = urllib.request.Request(info.download_url, headers={"User-Agent": USER_AGENT})
    downloaded = 0
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=30) as response, part.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or info.size or 0)
        while True:
            chunk = response.read(512 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if progress is not None:
                progress(downloaded, total)
    actual = digest.hexdigest().lower()
    if actual != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError("下载文件校验失败，可能下载不完整")
    if target.exists():
        target.unlink()
    part.replace(target)
    return target


def build_update_script(current_exe: Path, new_exe: Path, wait_pid: int) -> Path:
    script_path = Path(tempfile.gettempdir()) / f"pkb-update-{int(time.time())}.ps1"
    exe = str(current_exe).replace("'", "''")
    new = str(new_exe).replace("'", "''")
    script = f"""$ErrorActionPreference = 'Stop'
$exe = '{exe}'
$new = '{new}'
$backup = $exe + '.old'
try {{ Wait-Process -Id {wait_pid} -Timeout 60 -ErrorAction SilentlyContinue }} catch {{}}
for ($i = 0; $i -lt 200; $i++) {{
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object {{
        try {{ $_.Path -eq $exe }} catch {{ return $false }}
    }}
    if (-not $running) {{ break }}
    Start-Sleep -Milliseconds 300
}}
if (Test-Path $backup) {{ Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }}
try {{
    Move-Item -LiteralPath $exe -Destination $backup -Force
    Copy-Item -LiteralPath $new -Destination $exe -Force
    Start-Process -FilePath $exe
    Start-Sleep -Seconds 2
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue
}} catch {{
    if ((Test-Path $backup) -and -not (Test-Path $exe)) {{
        Move-Item -LiteralPath $backup -Destination $exe -Force
    }}
    throw
}}
"""
    script_path.write_text(script, encoding="utf-8-sig")
    return script_path


def launch_update_installer(current_exe: Path, new_exe: Path) -> None:
    script = build_update_script(current_exe, new_exe, os.getpid())
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        creationflags=flags,
        close_fds=True,
    )


class UpdateCheckWorker(QThread):
    result_ready = pyqtSignal(object, object)

    def __init__(self, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self.current_version = current_version

    def run(self) -> None:
        try:
            self.result_ready.emit(check_for_update(self.current_version), None)
        except Exception as error:
            self.result_ready.emit(None, error)


class UpdateDownloadWorker(QThread):
    progress_changed = pyqtSignal(int, int)
    result_ready = pyqtSignal(object, object)

    def __init__(self, info: UpdateInfo, output_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.info = info
        self.output_dir = output_dir

    def run(self) -> None:
        try:
            path = download_and_verify(self.info, self.output_dir, self.progress_changed.emit)
            self.result_ready.emit(path, None)
        except Exception as error:
            self.result_ready.emit(None, error)
