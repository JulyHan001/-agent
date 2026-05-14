$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $projectRoot "frontend"
$packageJson = Join-Path $frontendDir "package.json"
$frontendOutLog = Join-Path $frontendDir "frontend-dev.out.log"
$frontendErrLog = Join-Path $frontendDir "frontend-dev.err.log"
$port = 3000

function Stop-ProcessByPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetPort
    )

    $connections = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Host "Port $TargetPort is free."
        return
    }

    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "Stopped process $processId on port $TargetPort."
        }
        catch {
            Write-Warning "Failed to stop process $processId on port ${TargetPort}: $($_.Exception.Message)"
        }
    }
}

function Stop-FrontendProcessTree {
    $candidates = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -like "*npm*run dev*" -or
            $_.CommandLine -like "*next*dev*" -or
            $_.CommandLine -like "*next-server*"
        )
    }

    foreach ($process in $candidates) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped frontend process $($process.ProcessId)."
        }
        catch {
            Write-Warning "Failed to stop frontend process $($process.ProcessId): $($_.Exception.Message)"
        }
    }
}

if (-not (Test-Path $packageJson)) {
    throw "Frontend package.json not found: $packageJson"
}

Stop-ProcessByPort -TargetPort $port
Stop-FrontendProcessTree

Set-Location $frontendDir
Write-Host "Starting frontend on http://localhost:$port ..."
if (Test-Path $frontendOutLog) {
    Remove-Item -LiteralPath $frontendOutLog -Force -ErrorAction SilentlyContinue
}

if (Test-Path $frontendErrLog) {
    Remove-Item -LiteralPath $frontendErrLog -Force -ErrorAction SilentlyContinue
}

$process = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $frontendDir `
    -RedirectStandardOutput $frontendOutLog `
    -RedirectStandardError $frontendErrLog `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Frontend started with PID $($process.Id)."
