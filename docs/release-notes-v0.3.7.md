# v0.3.7

## 新增

- 手机页面顶部在「连接成功」后面显示电脑**当前前台窗口名**，例如「连接成功 · 微信」，一眼判断这次粘贴会落到哪个程序，避免发错窗口。
- 前台窗口名通过 `/session`、`/heartbeat` 等接口的 `focus` 字段下发，手机端沿用原有 4 秒心跳刷新，无需额外请求。
- 标题过长时截断到 80 个字符，避免撑破手机端布局；非 Windows 平台或取不到句柄时返回空字符串，页面回退显示「连接成功」。

## 实现

- 新增 `phone_keyboard/focus.py`：`foreground_title()` 调用 `user32!GetForegroundWindow` + `GetWindowTextW` 取标题，全部异常都吞掉返回空串。
- `phone_keyboard/server.py`：`_session_payload()` 增加 `focus` 字段。
- `phone_keyboard/templates/index.html`：`focusText()` 拼接状态文案。
- 仅电脑端改动，手机端 App 与浏览器页面无需更新（页面由电脑端下发）。

## 备注

- 这是本地构建的版本，基于上游 v0.3.6 源码修改。
