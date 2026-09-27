# Shared local/CI build checks. Dot-source this file from build entry points.
function Resolve-BuildPython {
    param([string]$PythonExe, [string]$RepoRoot)
    if (-not $PythonExe) {
        $venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
        $PythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }
    }
    & $PythonExe -c "import struct, sys; ok = sys.version_info[:2] == (3, 11) and struct.calcsize('P') == 8; print('Build interpreter: ' + sys.executable + ' (' + sys.version.split()[0] + ')'); sys.exit(0 if ok else 1)" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'Builds require 64-bit Python 3.11. Pass -PythonExe with the correct interpreter path.'
    }
    return $PythonExe
}

function Get-BuildVersion {
    param([string]$PythonExe, [string]$RepoRoot)
    $version = & $PythonExe -c "import runpy, sys; print(runpy.run_path(sys.argv[1])['__version__'])" (Join-Path $RepoRoot 'src\version.py')
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
        throw 'Could not read a three-part version from src\version.py.'
    }
    return $version
}
