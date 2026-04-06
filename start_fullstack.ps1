param(
    [string]$PythonExe = "C:\Users\35661\miniconda3\envs\ashare-agent\python.exe",
    [string]$BindHost = "127.0.0.1",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$AutoStopSeconds = 0
)

$ErrorActionPreference = "Stop"

function Test-PortFree {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($conn) {
        throw "Port $Port is already in use. Please free it and retry."
    }
}

function Ensure-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Required command not found: $Name"
    }
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Proc)
    if (-not $Proc) {
        return
    }
    try {
        $Proc.Refresh()
        if (-not $Proc.HasExited) {
            & taskkill /PID $Proc.Id /T /F | Out-Null
        }
    }
    catch {
        # Ignore cleanup errors during shutdown.
    }
}

$repoRoot = $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

Ensure-Command "npm.cmd"
Test-PortFree -Port $BackendPort
Test-PortFree -Port $FrontendPort

$backendProc = $null
$frontendProc = $null

try {
    $backendArgs = @(
        "-m", "uvicorn", "backend.main:app",
        "--host", $BindHost,
        "--port", $BackendPort.ToString()
    )
    $frontendArgs = @(
        "run", "dev", "--",
        "--host", $BindHost,
        "--port", $FrontendPort.ToString()
    )

    $backendProc = Start-Process -FilePath $PythonExe -ArgumentList $backendArgs -WorkingDirectory $repoRoot -PassThru
    $frontendProc = Start-Process -FilePath "npm.cmd" -ArgumentList $frontendArgs -WorkingDirectory $frontendDir -PassThru

    Write-Host ""
    Write-Host "Full stack is starting..."
    Write-Host "Frontend: http://$BindHost`:$FrontendPort"
    Write-Host "Backend : http://$BindHost`:$BackendPort/docs"
    Write-Host "Press Ctrl+C to stop both services."
    Write-Host ""

    $deadline = $null
    if ($AutoStopSeconds -gt 0) {
        $deadline = (Get-Date).AddSeconds($AutoStopSeconds)
    }

    while ($true) {
        $backendProc.Refresh()
        $frontendProc.Refresh()

        if ($backendProc.HasExited) {
            throw "Backend exited unexpectedly with code $($backendProc.ExitCode)."
        }
        if ($frontendProc.HasExited) {
            throw "Frontend exited unexpectedly with code $($frontendProc.ExitCode)."
        }

        if ($deadline -and (Get-Date) -ge $deadline) {
            Write-Host "Auto stop timeout reached. Stopping services..."
            break
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    Stop-ProcessTree -Proc $frontendProc
    Stop-ProcessTree -Proc $backendProc
}
