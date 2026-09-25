$ErrorActionPreference = "Stop"

Write-Host "=== SmartGestureOS MSIX Build Script ===" -ForegroundColor Cyan
Write-Host "Validating MakeAppx tool availability..."

# Ensure Windows 10 SDK is installed
$makeappx = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe"
if (-not (Test-Path $makeappx)) {
    # Try finding it dynamically or warn
    $makeappx = (Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\makeappx.exe" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
    if (-not $makeappx) {
        Write-Host "MakeAppx.exe not found! Please install Windows 10/11 SDK." -ForegroundColor Red
        exit 1
    }
}

$version = "1.0.0.0"
if (Test-Path "version.txt") {
    $ver = (Get-Content "version.txt").Trim()
    # Ensure it's in 4-part format for MSIX (e.g. 1.0.0.0)
    $version_parts = $ver.Split('.')
    while ($version_parts.Length -lt 4) { $version_parts += '0' }
    $version = $version_parts[0..3] -join "."
}

Write-Host "Using version: $version"

Write-Host "Staging MSIX layout..."
$msix_dir = "dist\msix_layout"
if (Test-Path $msix_dir) { Remove-Item -Recurse -Force $msix_dir }
New-Item -ItemType Directory -Force -Path "$msix_dir" | Out-Null
New-Item -ItemType Directory -Force -Path "$msix_dir\Assets" | Out-Null

# Copy PyInstaller output
Copy-Item -Recurse -Force "dist\SmartGestureOS\*" "$msix_dir\"

# Copy AppxManifest and Assets
Copy-Item -Force "packaging\windows\AppxManifest.xml" "$msix_dir\AppxManifest.xml"

# Update version in manifest
$manifest = Get-Content "$msix_dir\AppxManifest.xml"
$manifest = $manifest -replace 'Version="[^"]+"', "Version=""$version"""
Set-Content -Path "$msix_dir\AppxManifest.xml" -Value $manifest

# Create placeholder assets if they don't exist yet (for testing purposes)
# In production, these should be replaced with real assets
foreach ($img in @("StoreLogo.png", "Square150x150Logo.png", "Square44x44Logo.png", "Wide310x150Logo.png", "SplashScreen.png")) {
    # create a dummy file if not exists
    $out_path = "$msix_dir\Assets\$img"
    # just create empty file for now so makeappx doesn't fail
    New-Item -ItemType File -Force -Path $out_path | Out-Null
}

$output_msix = "release\SmartGestureOS_${version}_x64.msix"
if (-not (Test-Path "release")) { New-Item -ItemType Directory -Path "release" | Out-Null }
if (Test-Path $output_msix) { Remove-Item -Force $output_msix }

Write-Host "Packing MSIX..."
& $makeappx pack /d "$msix_dir" /p "$output_msix"

if ($LASTEXITCODE -eq 0) {
    Write-Host "MSIX Build COMPLETE: $output_msix" -ForegroundColor Green
    Write-Host "Remember to sign the package using SignTool before sideloading or publishing." -ForegroundColor Yellow
} else {
    Write-Host "MSIX Build FAILED with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
