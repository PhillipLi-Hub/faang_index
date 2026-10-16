$ErrorActionPreference = 'Stop'
$apiPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $apiPython)) {
    $condaPython = Join-Path $env:USERPROFILE 'anaconda3\python.exe'
    if (Test-Path -LiteralPath $condaPython) { & $condaPython -m venv (Join-Path $PSScriptRoot '.venv') }
    else { py -3 -m venv (Join-Path $PSScriptRoot '.venv') }
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $apiPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
} finally { Pop-Location }
