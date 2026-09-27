param([string]$PythonExe)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot 'build_common.ps1')

Write-Host "=== SmartGestureOS Build Script ===" -ForegroundColor Cyan
Write-Host "Preserving existing release artifacts..."

$pythonExe = Resolve-BuildPython -PythonExe $PythonExe -RepoRoot $repoRoot

Write-Host "Running pre-build validation with $pythonExe..."
& $pythonExe -m compileall -q (Join-Path $repoRoot "main.py") (Join-Path $repoRoot "config.py") (Join-Path $repoRoot "src") (Join-Path $repoRoot "tests") (Join-Path $repoRoot "scripts")
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: compileall found syntax errors. Aborting." -ForegroundColor Red
    exit 1
}

Write-Host "Running PyInstaller (ONEDIR)..."
& $pythonExe -m PyInstaller --noconfirm --clean `
    --workpath (Join-Path $repoRoot "build\SmartGestureOS") `
    --distpath (Join-Path $repoRoot "dist") `
    (Join-Path $repoRoot "packaging\windows\SmartGesture.spec")

if ($LASTEXITCODE -eq 0) {
    $exe = Join-Path $repoRoot "dist\SmartGestureOS\SmartGestureOS.exe"
    if (Test-Path -LiteralPath $exe) {
        Write-Host "Build COMPLETE: $exe" -ForegroundColor Green
        Write-Host ""
        Write-Host "To create the installer, run Inno Setup compiler (iscc):" -ForegroundColor Cyan
        Write-Host "  .\scripts\build_installer.ps1 -PythonExe '$pythonExe'"
    } else {
        Write-Host "WARN: PyInstaller exited 0 but EXE not found at $exe" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "Build FAILED with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
