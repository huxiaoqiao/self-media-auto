param(
    [string]$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe",
    [string]$Url = "https://mp.weixin.qq.com",
    [int]$Port = 18999,
    [string]$Profile = "C:\Users\Administrator\AppData\Roaming\baoyu-skills\chrome-profile\Default"
)

$ErrorActionPreference = "Continue"

$chromeArgs = "--remote-debugging-port=$Port --user-data-dir=`"$Profile`" --start-maximized --new-window `"$Url`""

Write-Host "[ChromeLauncher] Starting Chrome..."
Write-Host "[ChromeLauncher] Port: $Port"
Write-Host "[ChromeLauncher] Profile: $Profile"

# UseShellExecute=true 让 Chrome 在用户桌面上下文运行
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $ChromePath
$psi.Arguments = $chromeArgs
$psi.UseShellExecute = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Maximized

try {
    $proc = [System.Diagnostics.Process]::Start($psi)
    Write-Host "[ChromeLauncher] Started PID: $($proc.Id)"
} catch {
    Write-Host "[ChromeLauncher] ERROR: $_"
}

Start-Sleep 6
Write-Host "[ChromeLauncher] Done."
