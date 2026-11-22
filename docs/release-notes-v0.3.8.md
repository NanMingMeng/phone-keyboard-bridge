# v0.3.8

## 修复

- **同一台手机在设备列表里堆出多条记录**。以前只按 `device_id` 认设备，换浏览器、清浏览器数据、App WebView 与后台心跳各有一份 localStorage / SharedPreferences，就会各自生成一个新 `device_id`，列表里于是出现三四个「我的手机」。
- **`device_id` 互抢**。旧逻辑在指纹相同时把记录的 `device_id` 改名成新来的那个，两个客户端交替心跳就会来回改名，另一边的 `device_id` 又查不到记录，于是不断新增。

## 新增

- 新增 `phone_keyboard/identity.py`，按「物理设备身份」而不是 `device_id` 归并：
  - **high**：机型。Android 的 UA（`...; PLC110 Build/...`）和浏览器指纹第一段都带机型，App 原生心跳（`Dalvik/...`）、App 内 WebView（`... wv ...`）、手机浏览器三者 `device_id` 不同但机型一致 → 自动归成一台。
  - **medium**：指纹里的 platform + 分辨率 + 时区（iOS 与桌面浏览器没有机型可读）。
  - **low**：完全没有指纹的本地客户端（PowerShell / curl / python），退化成家族 + 客户端类型。
  - 身份只升不降：一条记录拿到机型级身份后，被无指纹脚本复用 `device_id` 也不会退化。
- 一条设备记录现在带 `device_ids` 别名列表（最多 8 个），新 `device_id` 是**追加**而不是改名，旧客户端不会因为改名而重新申请授权。
- 加载旧数据时自动归并历史重复记录（不丢操作次数，取最早的授权时间、最新的 IP 和动作），不需要再手动点「合并重复设备」。
- `server.py` 的会话响应按 `device_ids` 匹配，别名过来的请求同样能拿到设备名、别名和唤醒序号。

## 兼容

- `/session`、`/heartbeat` 等接口字段未变；`approved_devices.json` 新增 `device_ids`、`identity`、`identity_confidence`、`identity_detail`，老文件可直接读取。
- 「合并重复设备」按钮保留，作为兜底（正常情况下已无重复可合并）。

## 已知取舍

- 同一机型的**两台**手机（例如两台 PLC110）会被认成一台设备——这是「零重复」换来的代价，机型级身份无法再细分。需要区分时只保留一台授权即可。
- 无指纹的桌面脚本客户端只按家族 + 客户端类型合并，两台电脑都用 PowerShell 访问时会被并成一条。
