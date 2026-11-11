# Builds the standalone exe and the Windows installer.
# Usage:  powershell -ExecutionPolicy Bypass -File .\build_installer.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> [1/2] Building ImageMeasureTool.exe with PyInstaller" -ForegroundColor Cyan
python -m PyInstaller ImageMeasureTool.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$iscCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $iscCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isdl.php"
}

Write-Host "==> [2/2] Compiling installer with Inno Setup" -ForegroundColor Cyan
& $iscc "ImageMeasureTool_Setup.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed." }

Write-Host "`nDone. Installer:" -ForegroundColor Green
Get-ChildItem "installer\ImageMeasureTool_Setup_*.exe" |
    Select-Object FullName, @{ n = "SizeMB"; e = { [math]::Round($_.Length / 1MB, 1) } } |
    Format-Table -AutoSize
