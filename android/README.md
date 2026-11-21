# PKB 手机端（Android App）

这是 PKB 的安卓客户端外壳。它把现有的手机打字页面装进 App 里，并用自己的后台服务发**系统通知**，所以不需要给手机装证书、不需要 HTTPS，也不受浏览器后台冻结影响。

## 它解决什么问题

浏览器页面在手机后台会被系统冻结，电脑点了「打开打字界面」手机没反应；而且浏览器里发系统通知必须有 HTTPS 证书，普通用户装证书很麻烦。

这个 App 换了一种做法：界面还是那个网页（内嵌网页视图），但"有没有被呼叫"这件事交给 App 自己的前台服务去问电脑，收到后发**手机原生通知**。

## 功能

- 首次粘贴电脑上显示的手机地址（含令牌），或点「扫描局域网」自动找电脑
- 内嵌网页视图加载打字页面，文字、图片、文件发送全部与浏览器版一致
- 前台服务每 3 秒询问一次电脑，被呼叫时发原生通知（响铃 + 震动）
- 通知点击直接回到打字界面
- 设备身份固定，只需在电脑上授权一次

## 环境要求

- Android 8.0（API 26）及以上
- JDK 17
- Android SDK（compileSdk 35、build-tools 34.0.0）
- Gradle 8.9

## 构建

```bash
# 1. 复制并填写 SDK 路径
copy local.properties.example local.properties

# 2. 构建 debug 包
gradle assembleDebug

# 产物
app/build/outputs/apk/debug/app-debug.apk
```

Windows 下如果没有把 Gradle 加进 PATH，可以直接用完整路径：

```powershell
$env:JAVA_HOME='C:\path\to\jdk-17'
& 'C:\path\to\gradle-8.9\bin\gradle.bat' assembleDebug
```

## 安装

把 `app-debug.apk` 传到手机，点开安装，允许「未知来源」。首次打开需要粘贴电脑上显示的完整地址，例如：

```
http://192.168.1.5:3004/?t=abcdef123456
```

## 使用要点

1. 首次打开会弹「新设备请求连接」，在电脑上点允许，只此一次
2. 允许通知权限
3. 建议在系统设置里把这个 App 的电池优化设为「不限制」，否则后台可能被系统杀掉
4. 手机和电脑必须在同一个局域网

## 技术说明

| 文件 | 作用 |
|---|---|
| `MainActivity.kt` | 配置界面、内嵌网页视图、局域网扫描、通知权限申请 |
| `PollService.kt` | 前台服务，轮询 `/heartbeat`，发现呼叫序号变化就发通知 |
| `Prefs.kt` | 保存电脑地址、令牌、设备号、上次呼叫序号 |

App 的设备和网页页面共用同一个设备号：App 生成一个固定 ID，页面加载后通过脚本写入 `localStorage`，所以电脑上只需要授权一次。

## 许可证

与主项目相同，MIT。转载、修改、二次分发请保留作者署名和原项目地址：
https://github.com/NanMingMeng/phone-keyboard-bridge
