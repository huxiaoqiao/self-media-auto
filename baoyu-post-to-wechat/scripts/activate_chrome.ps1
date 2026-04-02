Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ChromeActivator {
    [DllImport("user32.dll", SetLastError=true)] 
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] 
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] 
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] 
    public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] 
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] 
    public static extern bool AllowSetForegroundWindow(int dwProcessId);
    [DllImport("kernel32.dll")] 
    public static extern IntPtr GetConsoleWindow();
}
"@

$SW_RESTORE = 9
$SW_SHOW = 5
$SW_MAXIMIZE = 3

Start-Sleep -Seconds 4

$console = [ChromeActivator]::GetConsoleWindow()
if ($console -ne [IntPtr]::Zero) {
    Write-Host "[activate] Console hwnd: $console"
    # 先把控制台窗口放到后台
    $null = [ChromeActivator]::ShowWindow($console, $SW_SHOW)
}

# 找到所有 Chrome 主窗口
$shell = Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }
Write-Host "[activate] Found Chrome processes: $($shell.Count)"

if ($shell) {
    # 通知系统允许设置前台窗口（解决权限问题）
    $null = [ChromeActivator]::AllowSetForegroundWindow(-1)
    
    foreach ($p in $shell) {
        $hwnd = $p.MainWindowHandle
        Write-Host "[activate] PID=$($p.Id) hwnd=$hwnd iconic=$([ChromeActivator]::IsIconic($hwnd))"
        
        if ([ChromeActivator]::IsIconic($hwnd)) {
            $null = [ChromeActivator]::ShowWindow($hwnd, $SW_RESTORE)
            Start-Sleep -Milliseconds 800
        }
        
        $null = [ChromeActivator]::SetForegroundWindow($hwnd)
        Start-Sleep -Milliseconds 300
        $null = [ChromeActivator]::ShowWindow($hwnd, $SW_SHOW)
        Write-Host "[activate] Activated PID=$($p.Id)"
    }
} else {
    Write-Host "[activate] No visible Chrome window found"
}
