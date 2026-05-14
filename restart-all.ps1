$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendScript = Join-Path $projectRoot "restart-backend.ps1"
$frontendScript = Join-Path $projectRoot "restart-frontend.ps1"

if (-not (Test-Path $backendScript)) {
    throw "Missing script: $backendScript"
}

if (-not (Test-Path $frontendScript)) {
    throw "Missing script: $frontendScript"
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $backendScript
Start-Sleep -Seconds 2
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $frontendScript

Write-Host "Backend and frontend restart commands completed."
