# 测试脚本：手动启动 Chrome 看哪种方式能显示窗口
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$args = @("--remote-debugging-port=9223", "--user-data-dir=`"C:\Users\Administrator\AppData\Roaming\baoyu-skills\chrome-profile\Default`"", "--start-maximized", "--new-window", "https://mp.weixin.qq.com")

Write-Host "=== 测试1: Start-Process -WindowStyle Normal ==="
Start-Process -FilePath $chrome -ArgumentList ($args -join " ") -WindowStyle Normal

Write-Host "等待 5 秒..."
Start-Sleep 5
Write-Host "完成"
