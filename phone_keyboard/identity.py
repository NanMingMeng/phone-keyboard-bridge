"""设备身份识别：把同一台物理设备的多个客户端归到一个身份。

同一个物理设备在服务端会冒出多个 `device_id`，原因都是客户端侧的标识不稳定：

- App 的后台心跳用 `HttpURLConnection`，`device_id` 存在 SharedPreferences 里；
- App 内嵌 WebView 页面、手机浏览器页面各有一份 localStorage，`device_id` 各不相同；
- 清掉浏览器数据、换浏览器、换网络后重开，`device_id` 会重新随机生成。

所以身份不能只看 `device_id`，要按“这台机器本身”来认。判定依据按可信度分三档：

- **high** —— 机型。Android 的 User-Agent（`...; PLC110 Build/...`）和浏览器指纹的第一段都带机型，
  原生心跳（`Dalvik/2.1.0 ... PLC110 Build/...`）、App 内 WebView（`... wv ... PLC110 Build/...`）、
  Chrome 浏览器三者 device_id 完全不同但机型一致，直接归成一台。
- **medium** —— 指纹里的 platform + 分辨率 + 时区。iOS 的 UA 不含机型，桌面浏览器也没有，
  只能用这组信号。
- **low** —— 完全没有指纹的本地客户端（PowerShell / curl / python 脚本）。退化成家族 + 客户端类型，
  只保证同一台机器上的重复请求归一。

身份只升不降：一条记录一旦拿到 high 身份，之后被无指纹客户端复用 `device_id` 也不会退化。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

CONFIDENCE_RANK = {"": 0, LOW: 1, MEDIUM: 2, HIGH: 3}

# Android UA：`...; PLC110 Build/BP2A.250605.015)` / `Linux; U; Android 16; PLC110 Build/...`
_MODEL_RE = re.compile(r";\s*([A-Za-z0-9 ._+\-]{1,40}?)\s+Build/")

# 无浏览器的原生客户端，用于把它们和浏览器区分开
_NATIVE_CLIENTS = (
    ("dalvik", "dalvik"),
    ("okhttp", "okhttp"),
    ("powershell", "powershell"),
    ("curl", "curl"),
    ("wget", "wget"),
    ("python-requests", "python"),
    ("python", "python"),
    ("httpclient", "httpclient"),
    ("java/", "java"),
)


@dataclass(frozen=True)
class DeviceIdentity:
    """一台设备的身份。`key` 相同即视为同一台设备。"""

    key: str
    confidence: str
    detail: str

    @property
    def rank(self) -> int:
        return CONFIDENCE_RANK.get(self.confidence, 0)


def split_fingerprint(fingerprint: str) -> tuple[str, str, str, str, str, str]:
    """拆手机端 `X-Device-Print`：机型|浏览器|platform|语言|时区|分辨率x色深。"""
    parts = (fingerprint or "").split("|")
    parts += [""] * (6 - len(parts))
    return tuple(part.strip() for part in parts[:6])  # type: ignore[return-value]


def ua_family(user_agent: str) -> str:
    ua = user_agent or ""
    if "Android" in ua:
        return "android"
    if "iPhone" in ua or "iPad" in ua or "iPod" in ua:
        return "ios"
    if "Windows" in ua:
        return "windows"
    if "Macintosh" in ua or "Mac OS X" in ua:
        return "macos"
    if "Linux" in ua:
        return "linux"
    return "unknown"


def ua_model(user_agent: str) -> str:
    match = _MODEL_RE.search(user_agent or "")
    return match.group(1).strip() if match else ""


def ua_client(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    for needle, name in _NATIVE_CLIENTS:
        if needle in ua:
            return name
    return "browser"


def compute_identity(user_agent: str, fingerprint: str, ip: str = "") -> DeviceIdentity:
    """按 UA / 指纹 / IP 推出设备身份。"""
    model_u, brand, platform, lang, tz, size = split_fingerprint(fingerprint)
    family = ua_family(user_agent)
    client = ua_client(user_agent)
    model = ua_model(user_agent) or model_u
    # 指纹里的平台段能补回 UA 丢了的信息：本机脚本复用手机 device_id 时，
    # UA 是 PowerShell 但指纹仍然是 `PLC110|Chrome|Linux aarch64|...`。
    mobile_platform = platform.lower().startswith(
        ("linux aarch64", "linux arm", "android", "iphone", "ipad")
    )
    mobile = family in ("android", "ios") or mobile_platform

    if model and mobile:
        family = "ios" if family == "ios" or platform in ("iPhone", "iPad") else "android"
        return DeviceIdentity(
            key=f"{family}:{model.lower()}",
            confidence=HIGH,
            detail=f"机型 {model}",
        )

    if platform or size or tz:
        # iOS 和桌面浏览器没有机型，用 platform + 分辨率 + 时区，再带上客户端类型避免
        # 同一台机器的浏览器和原生客户端互相顶替。
        return DeviceIdentity(
            key=f"{family}|{platform}|{size}|{tz}|{client}",
            confidence=MEDIUM,
            detail=f"{platform or family} {size or '未知分辨率'} {tz or '未知时区'}",
        )

    if family == "unknown":
        return DeviceIdentity(
            key=f"unknown|{(user_agent or '')[:48].lower()}|{client}",
            confidence=LOW,
            detail=f"未知平台 {client}",
        )

    return DeviceIdentity(
        key=f"desktop|{family}:{client}",
        confidence=LOW,
        detail=f"{family} {client}（无指纹）",
    )


def better_identity(current: DeviceIdentity, candidate: DeviceIdentity) -> bool:
    """candidate 是否比 current 更可信（身份只升不降）。"""
    return candidate.rank > current.rank
