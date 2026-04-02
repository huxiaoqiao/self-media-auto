$ErrorActionPreference = "Stop"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$port = 18999
$profile = "C:\Users\Administrator\AppData\Roaming\baoyu-skills\chrome-profile\Default"
$url = "https://mp.weixin.qq.com"

$args = @(
    "--remote-debugging-port=$port",
    "--user-data-dir=`"$profile`"",
    "--start-maximized",
    "--new-window",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    $url
)

$joinedArgs = $args -join " "
Write-Host "[测试] 启动 Chrome..."
Write-Host "[测试] 参数: $joinedArgs"

# 关键：使用 -PassThru 让 PowerShell 返回进程对象，然后等待
$proc = Start-Process -FilePath $chrome -ArgumentList $joinedArgs -WindowStyle Normal -PassThru -Wait -NoNewWindow
Write-Host "[测试] Chrome 已退出，退出码: $($proc.ExitCode)"
