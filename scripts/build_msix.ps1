$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distDir = Join-Path $repoRoot "dist"
$appDir = Join-Path $distDir "SmartGestureOS"
$manifestSource = Join-Path $repoRoot "packaging\windows\msix\AppxManifest.xml"
$assetsDir = Join-Path $repoRoot "packaging\windows\msix\Assets"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }

if (-not (Test-Path (Join-Path $appDir "SmartGestureOS.exe"))) {
    throw "PyInstaller ONEDIR output is missing. Build it first with scripts\build_windows.ps1."
}
if (-not (Test-Path $manifestSource)) { throw "Canonical MSIX manifest is missing: $manifestSource" }

$versionLine = & $pythonExe -c "from src.version import __version__; print(__version__)"
if ($LASTEXITCODE -ne 0 -or $versionLine -notmatch '^\d+\.\d+\.\d+$') {
    throw "Could not read a three-part version from src\version.py."
}
$version = "$versionLine.0"

[xml]$manifest = Get-Content -LiteralPath $manifestSource -Raw
$identity = $manifest.Package.Identity
if ($identity.Name -match '^YOUR_' -or $identity.Publisher -match '^CN=YOUR_' -or
    $manifest.Package.Properties.PublisherDisplayName -match '^Your Publisher') {
    throw "Replace the Identity Name, Publisher, and PublisherDisplayName with exact Partner Center values before building an MSIX."
}

# Verify real PNG headers and dimensions before staging. Never manufacture placeholder images.
$requiredAssets = @{
    "StoreLogo.png" = @(50, 50)
    "Square44x44Logo.png" = @(44, 44)
    "Square150x150Logo.png" = @(150, 150)
    "Wide310x150Logo.png" = @(310, 150)
    "Square310x310Logo.png" = @(310, 310)
    "SplashScreen.png" = @(620, 300)
}
foreach ($name in $requiredAssets.Keys) {
    $path = Join-Path $assetsDir $name
    if (-not (Test-Path -LiteralPath $path)) { throw "Required real MSIX visual asset is missing: $path" }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($bytes.Length -lt 24) { throw "MSIX visual asset is too small to be a valid PNG: $path" }
    $pngSignature = [byte[]](137, 80, 78, 71, 13, 10, 26, 10)
    $validPng = $true
    for ($i = 0; $i -lt $pngSignature.Length; $i++) {
        if ($bytes[$i] -ne $pngSignature[$i]) { $validPng = $false; break }
    }
    if (-not $validPng -or [System.Text.Encoding]::ASCII.GetString($bytes, 12, 4) -ne "IHDR") {
        throw "MSIX visual asset is not a valid PNG: $path"
    }
    $width = [System.Net.IPAddress]::NetworkToHostOrder([BitConverter]::ToInt32($bytes, 16))
    $height = [System.Net.IPAddress]::NetworkToHostOrder([BitConverter]::ToInt32($bytes, 20))
    if ($width -ne $requiredAssets[$name][0] -or $height -ne $requiredAssets[$name][1]) {
        throw "Wrong dimensions for $name; expected $($requiredAssets[$name][0])x$($requiredAssets[$name][1]), got ${width}x${height}."
    }
}

$sdkRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
$makeAppx = Get-ChildItem -LiteralPath $sdkRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName "x64\makeappx.exe" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
if (-not $makeAppx) { throw "MakeAppx.exe not found. Install the Windows 10/11 SDK. Checked: $sdkRoot" }

$layoutDir = Join-Path $distDir "msix_layout"
$releaseDir = Join-Path $distDir "release"
$output = Join-Path $releaseDir "SmartGestureOS_${version}_x64.msix"
if (Test-Path -LiteralPath $layoutDir) { Remove-Item -LiteralPath $layoutDir -Recurse -Force }
New-Item -ItemType Directory -Path $layoutDir -Force | Out-Null
Copy-Item -Path (Join-Path $appDir "*") -Destination $layoutDir -Recurse -Force
Copy-Item -LiteralPath $manifestSource -Destination (Join-Path $layoutDir "AppxManifest.xml")
New-Item -ItemType Directory -Path (Join-Path $layoutDir "Assets") -Force | Out-Null
foreach ($name in $requiredAssets.Keys) {
    Copy-Item -LiteralPath (Join-Path $assetsDir $name) -Destination (Join-Path $layoutDir "Assets\$name")
}

[xml]$stagedManifest = Get-Content -LiteralPath (Join-Path $layoutDir "AppxManifest.xml") -Raw
$stagedManifest.Package.Identity.Version = $version
$stagedManifest.Save((Join-Path $layoutDir "AppxManifest.xml"))
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
& $makeAppx pack /d $layoutDir /p $output /o
if ($LASTEXITCODE -ne 0) { throw "MakeAppx failed with exit code $LASTEXITCODE" }
Write-Host "MSIX created: $output" -ForegroundColor Green
Write-Host "Sign it with a trusted certificate before sideloading. Microsoft signs Store submissions."
