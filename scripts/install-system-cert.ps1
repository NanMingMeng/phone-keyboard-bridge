# 把 PKB 的 CA 证书安装成 Android「系统证书」
#
# 适用：手机已经 root（Magisk / KernelSU 等），并已开启 USB 调试。
# 效果：系统级信任，所有浏览器和 App 都认，不需要再到设置里手动安装。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\install-system-cert.ps1
#   如果 adb 不在 PATH：
#   powershell -ExecutionPolicy Bypass -File scripts\install-system-cert.ps1 -Adb "C:\platform-tools\adb.exe"

param(
    [string]$Adb = "adb",
    [string]$CertDir = "$env:APPDATA\PhoneKeyboardBridge\certs\android"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command $Adb -ErrorAction SilentlyContinue) -and -not (Test-Path $Adb)) {
    Write-Host "找不到 adb。请先安装 Android Platform Tools，或用 -Adb 参数指定 adb.exe 的完整路径。" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $CertDir)) {
    Write-Host "找不到证书目录：$CertDir" -ForegroundColor Red
    Write-Host "请先启动一次 PKB 桌面版，它会自动生成证书。" -ForegroundColor Yellow
    exit 1
}

$cert = Get-ChildItem $CertDir -Filter "*.0" | Select-Object -First 1
if (-not $cert) {
    Write-Host "证书目录里没有 .0 文件：$CertDir" -ForegroundColor Red
    exit 1
}

Write-Host "使用证书：$($cert.FullName)" -ForegroundColor Cyan

Write-Host "`n[1/5] 检查设备连接..." -ForegroundColor Cyan
& $Adb devices
Write-Host "`n[2/5] 获取 root 权限..." -ForegroundColor Cyan
& $Adb root
Start-Sleep -Seconds 2
Write-Host "`n[3/5] 以可写方式重新挂载系统分区..." -ForegroundColor Cyan
& $Adb remount
Start-Sleep -Seconds 1
Write-Host "`n[4/5] 推送证书到 /system/etc/security/cacerts/ ..." -ForegroundColor Cyan
$target = "/system/etc/security/cacerts/$($cert.Name)"
& $Adb push $cert.FullName $target
& $Adb shell "chmod 644 $target"
& $Adb shell "chown root:root $target"
Write-Host "`n[5/5] 校验..." -ForegroundColor Cyan
& $Adb shell "ls -l $target"

Write-Host "`n完成。现在重启手机让系统证书生效：" -ForegroundColor Green
Write-Host "  adb reboot" -ForegroundColor Green
Write-Host "`n重启后用 Chrome 打开 https://电脑IP:3005/?t=... 就不会再有证书警告，也不需要手动装证书。" -ForegroundColor Green
Write-Host "注意：系统分区被改过后，系统 OTA 更新可能失败。要撤销的话，删掉这个文件并重启即可。" -ForegroundColor Yellow
