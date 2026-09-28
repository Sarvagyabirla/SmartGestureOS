param([string]$PythonExe, [string]$IsccPath)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot 'build_common.ps1')
$pythonExe = Resolve-BuildPython -PythonExe $PythonExe -RepoRoot $repoRoot
$version = Get-BuildVersion -PythonExe $pythonExe -RepoRoot $repoRoot

if (-not $IsccPath) {
    $isccCommand = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($isccCommand) { $IsccPath = $isccCommand.Source }
    else {
        $IsccPath = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Antigravity IDE\resources\app\node_modules\innosetup\bin\ISCC.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) {
    throw 'Inno Setup 6 compiler was not found. Install it or pass -IsccPath with the full path to ISCC.exe.'
}

$exe = Join-Path $repoRoot "dist\SmartGestureOS\SmartGestureOS.exe"
if (-not (Test-Path $exe)) { throw "PyInstaller output is missing. Run scripts\build_windows.ps1 first." }

Push-Location -LiteralPath $repoRoot
try {
    & $IsccPath "/DAppVersion=$version" "packaging\windows\SmartGestureOS.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$installerName = "SmartGestureOS-Setup-v$version.exe"
$installer = Get-Item -LiteralPath (Join-Path $repoRoot "dist\release\$installerName")
if ($installer.Length -eq 0) { throw 'Inno Setup produced an empty installer.' }
$hash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $installerName" | Set-Content -LiteralPath (Join-Path $repoRoot 'dist\release\SHA256SUMS.txt') -Encoding Ascii
Write-Host "Installer and SHA256SUMS.txt created under dist\release for version $version." -ForegroundColor Green
