$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }

$version = & $pythonExe -c "from src.version import __version__; print(__version__)"
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Could not read a three-part version from src\version.py."
}

$isccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if (-not $isccCommand) { throw "Inno Setup 6 compiler (ISCC.exe) was not found on PATH." }

$exe = Join-Path $repoRoot "dist\SmartGestureOS\SmartGestureOS.exe"
if (-not (Test-Path $exe)) { throw "PyInstaller output is missing. Run scripts\build_windows.ps1 first." }

Push-Location $repoRoot
try {
    & $isccCommand.Source "/DAppVersion=$version" "packaging\windows\SmartGestureOS.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "Installer created under dist\release for version $version." -ForegroundColor Green
