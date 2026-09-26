$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=== SmartGestureOS Build Script ===" -ForegroundColor Cyan
Write-Host "Preserving existing release artifacts..."

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Write-Host "Running pre-build validation with $pythonExe..."
& $pythonExe -m compileall -q (Join-Path $repoRoot "main.py") (Join-Path $repoRoot "config.py") (Join-Path $repoRoot "src")
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
        Write-Host "  iscc packaging\windows\SmartGestureOS.iss"
    } else {
        Write-Host "WARN: PyInstaller exited 0 but EXE not found at $exe" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "Build FAILED with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
