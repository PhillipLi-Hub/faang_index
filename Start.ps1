param([ValidateRange(1,65535)][int]$Port = 8002)
$ErrorActionPreference = 'Stop'
$apiPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $apiPython)) { throw 'Run .\Setup.ps1 first.' }
Write-Host 'Phone: connect to the same Wi-Fi, then open:'
Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | ForEach-Object {
    Write-Host ('http://{0}:{1}/docs' -f $_.IPv4Address.IPAddress, $Port)
}
Write-Host 'Keep this terminal open. Ctrl+C stops the API.'
Push-Location -LiteralPath $PSScriptRoot
try { & $apiPython -m uvicorn faang_index_api.main:app --host 0.0.0.0 --port $Port --workers 1 }
finally { Pop-Location }
