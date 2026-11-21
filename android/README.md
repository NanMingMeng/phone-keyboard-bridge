# PKB 手机端（Android App）

这是 PKB 的安卓客户端外壳。它把现有的手机打字页面装进 App 里，并用自己的后台服务发**系统通知**，所以不需要给手机装证书、不需要 HTTPS，也不受浏览器后台冻结影响。

## 它解决什么问题

浏览器页面在手机后台会被系统冻结，电脑点了「打开打字界面」手机没反应；而且浏览器里发系统通知必须有 HTTPS 证书，普通用户装证书很麻烦。

这个 App 换了一种做法：界面还是那个网页（内嵌网页视图），但"有没有被呼叫"这件事交给 App 自己的前台服务去问电脑，收到后发**手机原生通知**。

## 功能

- **扫码连接**：直接扫电脑 PKB 窗口里的二维码，扫到就自动连（CameraX + ZXing，无需 Google 服务）
- **继续上次的连接**：连过一次之后，重新打开 App 直接回到打字页，不用重扫
- **连接条件与常见问题**：首次进入默认展开，写明三种连法（同一 Wi‑Fi / 电脑连手机热点 / 手机连电脑热点）、防火墙要点、换网络后要重扫
- 也可以手动粘贴电脑上显示的手机地址（含令牌），或扫描局域网自动找电脑
- 内嵌网页视图加载打字页面，文字、图片、文件发送全部与浏览器版一致
- 前台服务每 3 秒询问一次电脑，被呼叫时发原生通知（响铃 + 震动）
- 通知点击直接回到打字界面
- 设备身份固定，只需在电脑上授权一次
- App 图标与名称与电脑端 PKB 保持一致（自适应图标，深色/浅色启动器通用）
- **连不上不会白屏**：连之前先探 1.5 秒端口，失败或网页加载出错都会退回连接页并给出排查提示

## 发布约定（重要）

安卓版的 Release 标签**必须**用 `android-vX.Y.Z` 格式（例如 `android-v1.0.7`），不要用 `v0.x.y`。

原因：桌面版的自动更新会扫描仓库所有 Release，挑出带 `PKB.exe` 的最新版本。如果安卓版用了 `v0.x.y` 这种标签，会被当成桌面版的新版本，桌面版去里面找不到 `PKB.exe`，就会报「最新版本缺少 PKB.exe」。

另外建议把安卓版的 Release 标记为「预发布（Pre-release）」，双重保险。

| 发什么 | 标签格式 | 预发布 |
|---|---|---|
| 桌面版 | `v0.3.7` | 否 |
| 安卓版 | `android-v1.0.8` | 是 |

## 环境要求

- Android 8.0（API 26）及以上
- JDK 17 或更高
- Android SDK（compileSdk 34、build-tools 34.0.0 及以上）
- Gradle 8.9

> 说明：之所以是 compileSdk 34 而不是 35，是因为部分自编译的 aarch64 aapt2 读不了 platform-35 的 `android.jar`（`RES_TABLE_TYPE_TYPE entry offsets overlap`）。如果本机 aapt2 正常，可以自行改回 35。

## 构建

```bash
# 1. 写 SDK 路径
echo "sdk.dir=/path/to/Android/sdk" > local.properties

# 2. 构建（未配置签名时输出 app-release-unsigned.apk）
./gradlew assembleRelease

# 产物
app/build/outputs/apk/release/app-release.apk
```

### 签名（可选）

签名材料**不入库**。在 `local.properties` 里写：

```properties
pkb.storeFile=app/pkb.jks
pkb.storePassword=******
pkb.keyAlias=pkb
pkb.keyPassword=******
```

也支持环境变量：`PKB_KEYSTORE` / `PKB_STORE_PASSWORD` / `PKB_KEY_ALIAS` / `PKB_KEY_PASSWORD`。
都没配置时 `assembleRelease` 只出未签名包，自己用 `apksigner` 签即可：

```bash
zipalign -f -p 4 app-release-unsigned.apk app-aligned.apk
apksigner sign --ks my.jks --out app-release.apk app-aligned.apk
```

## 安装

把 APK 传到手机点开安装，允许「未知来源」。首次打开：点「扫码连接」扫电脑窗口里的二维码，或在「手动输入地址」里粘贴完整地址：

```
http://192.168.1.5:3004/?t=abcdef123456
```

## 使用要点

1. 首次打开会弹「新设备请求连接」，在电脑上点允许，只此一次
2. 允许通知权限（Android 13+）与相机权限（扫码用）
3. 建议在系统设置里把这个 App 的电池优化设为「不限制」，否则后台可能被系统杀掉
4. 手机和电脑必须能互相访问：同一个 Wi‑Fi，或电脑连手机开的热点（最稳）
5. 打字页按返回 = 退回桌面（连接不丢），下次打开自动回到打字页

## 目录

```
android/
├── app/
│   ├── build.gradle.kts          # 版本号、依赖、签名读取逻辑
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/nanming/pkb/
│       │   ├── MainActivity.kt   # 连接页 + 网页容器 + 错误兜底
│       │   ├── QrScanActivity.kt # 扫码（CameraX + ZXing）
│       │   ├── Prefs.kt          # 地址/令牌/设备 ID/最近连接状态
│       │   └── PollService.kt    # 前台轮询 + 系统通知
│       └── res/                  # 布局、图标、字符串
└── README.md
```
