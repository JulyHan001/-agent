$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$backendOutLog = Join-Path $backendDir "backend-dev.out.log"
$backendErrLog = Join-Path $backendDir "backend-dev.err.log"
$port = 8000

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

function Stop-BackendProcessTree {
    $candidates = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -like "*uvicorn app.main:app*" -or
            $_.CommandLine -like "*spawn_main(parent_pid=*"
        )
    }

    foreach ($process in $candidates) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped backend process $($process.ProcessId)."
        }
        catch {
            Write-Warning "Failed to stop backend process $($process.ProcessId): $($_.Exception.Message)"
        }
    }
}

if (-not (Test-Path $pythonExe)) {
    throw "Backend virtual environment not found: $pythonExe"
}

Stop-ProcessByPort -TargetPort $port
Stop-BackendProcessTree

Set-Location $backendDir
Write-Host "Starting backend on http://localhost:$port ..."
if (Test-Path $backendOutLog) {
    Remove-Item -LiteralPath $backendOutLog -Force -ErrorAction SilentlyContinue
}

if (Test-Path $backendErrLog) {
    Remove-Item -LiteralPath $backendErrLog -Force -ErrorAction SilentlyContinue
}

$process = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$port" `
    -WorkingDirectory $backendDir `
    -RedirectStandardOutput $backendOutLog `
    -RedirectStandardError $backendErrLog `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Backend started with PID $($process.Id)."
