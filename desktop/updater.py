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

MIRROR_PREFIXES = (
    "",
    "https://gh-proxy.com/",
    "https://ghfast.top/",
)
DOWNLOAD_ATTEMPTS = 3
CHUNK_SIZE = 256 * 1024
MIN_SPEED_BYTES = 60 * 1024
SLOW_CHECK_SECONDS = 20.0


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


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_checksum(checksum_url: str, timeout: float = 15.0) -> str:
    last_error: Exception | None = None
    for prefix in MIRROR_PREFIXES:
        url = f"{prefix}{checksum_url}" if prefix else checksum_url
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace").strip()
            expected = text.split()[0].lower() if text else ""
            if len(expected) == 64:
                return expected
            last_error = RuntimeError("发布页校验文件格式不正确")
        except Exception as error:
            last_error = error
    raise RuntimeError(f"无法获取更新校验文件：{last_error}")


def _download_to_part(
    url: str,
    part: Path,
    total_size: int,
    progress: Callable[[int, int], None] | None,
    timeout: float = 20.0,
) -> None:
    existing = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    started = time.time()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if existing and status != 206:
            existing = 0
        total = total_size
        content_length = response.headers.get("Content-Length")
        if content_length and str(content_length).isdigit():
            total = int(content_length) + existing
        downloaded = existing
        last_probe = downloaded
        with part.open("ab" if existing else "wb") as handle:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress is not None:
                    progress(downloaded, total)
                if downloaded - last_probe >= 1024 * 1024:
                    elapsed = time.time() - started
                    if elapsed > SLOW_CHECK_SECONDS and downloaded / elapsed < MIN_SPEED_BYTES:
                        raise RuntimeError("当前下载通道速度过低")
                    last_probe = downloaded


def download_and_verify(
    info: UpdateInfo,
    output_dir: Path,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "PKB.exe"
    part = output_dir / "PKB.exe.part"
    expected = _read_checksum(info.checksum_url)
    last_error: Exception | None = None
    for prefix in MIRROR_PREFIXES:
        url = f"{prefix}{info.download_url}" if prefix else info.download_url
        part.unlink(missing_ok=True)
        for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
            try:
                if progress is not None:
                    progress(0, info.size)
                _download_to_part(url, part, info.size, progress)
                if info.size and part.stat().st_size != info.size:
                    raise RuntimeError("下载文件大小与发布页不一致")
                if _sha256_of(part).lower() != expected:
                    part.unlink(missing_ok=True)
                    raise RuntimeError("下载文件校验失败，可能下载不完整")
                if target.exists():
                    target.unlink()
                part.replace(target)
                return target
            except Exception as error:
                last_error = error
                if attempt < DOWNLOAD_ATTEMPTS:
                    time.sleep(1.5)
    raise RuntimeError(f"下载更新失败：{last_error}")


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
