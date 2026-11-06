from __future__ import annotations

import socket
import subprocess
import urllib.request
from dataclasses import dataclass

from phone_keyboard.cli import build_url, find_lan_ip


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    hint: str = ""


def _run_powershell(command: str) -> str:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=6,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return (completed.stdout or completed.stderr).strip()


def _http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def run_checks(port: int, token: str, running: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(
        CheckResult(
            "本机服务",
            running,
            "服务正在运行" if running else "服务没有启动",
            "点击“启动服务”。" if not running else "",
        )
    )

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            port_ok = True
    except OSError:
        port_ok = False
    results.append(
        CheckResult(
            "监听端口",
            port_ok,
            f"端口 {port} 正在监听" if port_ok else f"端口 {port} 没有监听",
            "检查设置页端口是否被其他软件占用。" if not port_ok else "",
        )
    )

    ip = find_lan_ip()
    ip_ok = bool(ip and not ip.startswith("127."))
    results.append(
        CheckResult(
            "局域网地址",
            ip_ok,
            f"当前地址 {ip}" if ip_ok else "没有找到可用的局域网地址",
            "确认电脑已连接 Wi-Fi 或热点。" if not ip_ok else "",
        )
    )

    local_ok = _http_ok(f"http://127.0.0.1:{port}/ping")
    results.append(
        CheckResult(
            "本机接口",
            local_ok,
            "本机接口可访问" if local_ok else "本机接口无法访问",
            "重新启动服务；仍失败时查看日志页。" if not local_ok else "",
        )
    )

    if ip_ok:
        phone_url = build_url(ip, port, token)
        lan_ok = _http_ok(phone_url)
        results.append(
            CheckResult(
                "手机页面",
                lan_ok,
                "局域网手机页面可访问" if lan_ok else "局域网手机页面不可访问",
                "如果手机也打不开，检查 Windows 防火墙或网络隔离。" if not lan_ok else "",
            )
        )

    try:
        completed = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=PKB"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        has_rule = "Rule Name:" in output or "规则名称" in output
        enabled = "Enabled:                              Yes" in output or "已启用" in output
        if has_rule and enabled:
            results.append(CheckResult("防火墙规则", True, "已找到 PKB 的启用规则"))
        elif has_rule:
            results.append(
                CheckResult(
                    "防火墙规则",
                    False,
                    "找到 PKB 规则，但当前不是启用状态",
                    "打开防火墙设置并启用 PKB 规则。",
                )
            )
        else:
            results.append(
                CheckResult(
                    "防火墙规则",
                    False,
                    "没有找到名为 PKB 的防火墙规则",
                    "若手机无法访问，请打开防火墙设置，允许 PKB 或 Python 通过专用网络。",
                )
            )
    except Exception as error:
        results.append(CheckResult("防火墙规则", False, f"无法检查：{error}", "手动打开 Windows 防火墙检查。"))

    try:
        profile = _run_powershell(
            "Get-NetConnectionProfile | Select-Object -First 1 -ExpandProperty NetworkCategory"
        )
        if profile:
            private = "Private" in profile
            results.append(
                CheckResult(
                    "网络类型",
                    private,
                    f"当前网络类型：{profile}",
                    "公用网络可能阻止局域网访问，建议切换到专用网络。" if not private else "",
                )
            )
    except Exception as error:
        results.append(CheckResult("网络类型", False, f"无法检查：{error}", "手动检查 Windows 网络类型。"))

    return results
