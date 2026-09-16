$ErrorActionPreference = "Stop"

Write-Host "Building SmartGestureOS..."
Write-Host "Cleaning previous builds..."

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

Write-Host "Running PyInstaller..."
pyinstaller --noconfirm --clean SmartGesture.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete! Output in dist/SmartGestureOS" -ForegroundColor Green
} else {
    Write-Host "Build failed with exit code $LASTEXITCODE" -ForegroundColor Red
}
