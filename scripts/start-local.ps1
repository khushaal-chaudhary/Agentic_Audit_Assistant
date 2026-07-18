$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Runtime = Join-Path $Root "data\runtime"

if (-not (Test-Path $Python)) {
    throw "Create the virtual environment and install dependencies first; see README.md."
}

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

$WebRoot = Join-Path $Root "apps\web"
if (-not (Test-Path (Join-Path $WebRoot ".next\BUILD_ID"))) {
    & npm.cmd run build --prefix $WebRoot
    if ($LASTEXITCODE -ne 0) { throw "Web build failed." }
}

$Api = Start-Process -FilePath $Python -ArgumentList @(
    "-m", "uvicorn", "services.api.main:app", "--host", "127.0.0.1", "--port", "8000"
) -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Runtime "api.log") `
    -RedirectStandardError (Join-Path $Runtime "api-error.log") -WindowStyle Hidden -PassThru

$Web = Start-Process -FilePath "npm.cmd" -ArgumentList @(
    "run", "start", "--", "--hostname", "127.0.0.1"
) -WorkingDirectory $WebRoot -RedirectStandardOutput (Join-Path $Runtime "web.log") `
    -RedirectStandardError (Join-Path $Runtime "web-error.log") -WindowStyle Hidden -PassThru

Set-Content -LiteralPath (Join-Path $Runtime "api.pid") -Value $Api.Id
Set-Content -LiteralPath (Join-Path $Runtime "web.pid") -Value $Web.Id

Write-Host "Audit API: http://127.0.0.1:8000"
Write-Host "Audit UI:  http://127.0.0.1:3000"
Write-Host "Stop both with .\scripts\stop-local.ps1"
