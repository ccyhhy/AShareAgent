param(
    [string]$PythonExe = "C:\Users\35661\miniconda3\envs\ashare-agent\python.exe",
    [string]$BindHost = "127.0.0.1",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$AutoStopSeconds = 0,
    [switch]$ForceFreePorts
)

$ErrorActionPreference = "Stop"

function Get-PortOwners {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Ensure-PortAvailable {
    param(
        [int]$Port,
        [switch]$ForceFree
    )

    $owners = Get-PortOwners -Port $Port
    if (-not $owners -or $owners.Count -eq 0) {
        return
    }

    if (-not $ForceFree) {
        throw "Port $Port is already in use. Rerun with -ForceFreePorts to auto-release it."
    }

    Write-Host "Port $Port is in use by PID(s): $($owners -join ', '). Releasing..."
    foreach ($pid in $owners) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
        }
        catch {
            throw "Failed to stop PID $pid on port ${Port}: $($_.Exception.Message)"
        }
    }

    Start-Sleep -Seconds 1

    $remaining = Get-PortOwners -Port $Port
    if ($remaining -and $remaining.Count -gt 0) {
        throw "Port $Port is still occupied by PID(s): $($remaining -join ', ')."
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
Ensure-PortAvailable -Port $BackendPort -ForceFree:$ForceFreePorts
Ensure-PortAvailable -Port $FrontendPort -ForceFree:$ForceFreePorts

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
