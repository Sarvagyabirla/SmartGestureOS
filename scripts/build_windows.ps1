$ErrorActionPreference = "Stop"

Write-Host "=== SmartGestureOS Build Script ===" -ForegroundColor Cyan
Write-Host "Cleaning previous builds..."

if (Test-Path "build")  { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")   { Remove-Item -Recurse -Force "dist" }

Write-Host "Running pre-build validation..."
python -m compileall -q main.py config.py src
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: compileall found syntax errors. Aborting." -ForegroundColor Red
    exit 1
}

Write-Host "Running PyInstaller (ONEDIR)..."
python -m PyInstaller --noconfirm --clean .\packaging\windows\SmartGesture.spec

if ($LASTEXITCODE -eq 0) {
    $exe = "dist\SmartGestureOS\SmartGestureOS.exe"
    if (Test-Path $exe) {
        Write-Host "Build COMPLETE: $exe" -ForegroundColor Green
        Write-Host ""
        Write-Host "To create the installer, run Inno Setup compiler (iscc):" -ForegroundColor Cyan
        Write-Host "  iscc packaging\windows\SmartGestureOS.iss"
    } else {
        Write-Host "WARN: PyInstaller exited 0 but EXE not found at $exe" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "Build FAILED with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
