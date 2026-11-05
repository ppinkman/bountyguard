param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv and install requirements.txt first.' }
    & $taskPython -m bountyguard serve --port $Port
} finally { Pop-Location }
