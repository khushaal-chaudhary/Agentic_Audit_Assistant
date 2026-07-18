$Root = Split-Path $PSScriptRoot -Parent
$Runtime = Join-Path $Root "data\runtime"

function Stop-ProcessTree([int]$Id) {
    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$Id"
    foreach ($Child in $Children) {
        Stop-ProcessTree $Child.ProcessId
    }
    Stop-Process -Id $Id -ErrorAction SilentlyContinue
}

foreach ($Name in @("api", "web")) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (Test-Path $PidFile) {
        $ProcessId = Get-Content -LiteralPath $PidFile
        Stop-ProcessTree ([int]$ProcessId)
        Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
    }
}

Write-Host "Local audit services stopped."
