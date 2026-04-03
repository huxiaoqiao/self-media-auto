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

Start-Sleep -Seconds 2

$maxWait = 20
$waited = 0
$portOpen = $false

while ($waited -lt $maxWait -and -not $portOpen) {
    Start-Sleep -Milliseconds 500
    $waited++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$Port/json" -UseBasicParsing -TimeoutSec 1 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $portOpen = $true
            Write-Host "[ChromeLauncher] Debug port ready after $waited checks"
        }
    } catch {
    }
}

if (-not $portOpen) {
    Write-Host "[ChromeLauncher] Warning: Debug port not ready after $maxWait checks, proceeding anyway"
}

Write-Host "[ChromeLauncher] Done."
