param([ValidateSet('fake', 'ollama')][string]$Backend = 'fake', [switch]$Frontend)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run sh/setup_venv.ps1 first.' }
$env:PYTHONUTF8 = '1'
if ($Frontend) {
    & '.\.venv\Scripts\python.exe' web_demo_server.py
} else {
    $env:LLM_BACKEND = $Backend
    & '.\.venv\Scripts\python.exe' server.py
}
if ($LASTEXITCODE -ne 0) { throw 'Server stopped with an error.' }
