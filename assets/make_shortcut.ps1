<#
    Creates the "Video Analyzer" shortcut with the app icon.

    Run:  powershell -ExecutionPolicy Bypass -File assets\make_shortcut.ps1
    Add:  -Desktop     to also drop a copy on the Desktop

    The .lnk itself is not committed to git because it stores absolute paths
    that only work on the machine that made it. Re-run this after cloning.
#>
param([switch]$Desktop)

$ErrorActionPreference = "Stop"

$root   = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$target = Join-Path $root "Video Analyzer.bat"
$icon   = Join-Path $root "assets\icon.ico"

if (-not (Test-Path $target)) { throw "Cannot find $target" }
if (-not (Test-Path $icon))   { throw "Cannot find $icon - run: python assets\make_icon.py" }

$shell = New-Object -ComObject WScript.Shell

function New-AppShortcut([string]$Path) {
    $link = $shell.CreateShortcut($Path)
    $link.TargetPath       = $target
    $link.WorkingDirectory = $root
    $link.IconLocation     = "$icon,0"
    $link.Description      = "Turn a YouTube link into timestamped frames"
    $link.WindowStyle      = 1
    $link.Save()
    Write-Host "created: $Path"
}

New-AppShortcut (Join-Path $root "Video Analyzer.lnk")

if ($Desktop) {
    New-AppShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Video Analyzer.lnk")
}
