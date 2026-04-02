$ErrorActionPreference = "Continue"

$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$url = "https://mp.weixin.qq.com"
$port = 9223
$profile = "C:\Users\Administrator\AppData\Roaming\baoyu-skills\chrome-profile\Default"

$argString = "--remote-debugging-port=$port --user-data-dir=`"$profile`" --start-maximized --new-window `"$url`""

Write-Host "=== 启动 Chrome ==="
Write-Host "Chrome: $chrome"
Write-Host "Args: $argString"

# 方案1: Start-Process -WindowStyle Normal
Start-Process -FilePath $chrome -ArgumentList $argString -WindowStyle Normal -PassThru | ForEach-Object {
    Write-Host "Chrome PID: $($_.Id)"
}

Start-Sleep 6

# 方案2: 检查窗口
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder sb, int count);
    [DllImport("user32.dll")] public static extern IntPtr GetShellWindow();
}
"@

$hwnd = [Win32]::GetForegroundWindow()
$title = [System.Text.StringBuilder]::new(256)
[void][Win32]::GetWindowText($hwnd, $title, 256)
Write-Host "当前前景窗口: [$($title.ToString())] hwnd=$hwnd"

Write-Host "=== 完成 ==="
