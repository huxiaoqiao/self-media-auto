Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
"@

$MAXIMIZE = 3
Start-Sleep -Seconds 5

$chromeProcesses = Get-Process -Name "chrome" -ErrorAction SilentlyContinue

if ($chromeProcesses) {
    foreach ($proc in $chromeProcesses) {
        $hwnd = $proc.MainWindowHandle
        if ($hwnd -ne [IntPtr]::Zero) {
            if ([Win32]::IsIconic($hwnd)) {
                [void][Win32]::ShowWindow($hwnd, $MAXIMIZE)
            }
            [void][Win32]::SetForegroundWindow($hwnd)
            Write-Host "[maximize_chrome] Activated PID $($proc.Id)"
        }
    }
} else {
    Write-Host "[maximize_chrome] No Chrome process"
}
