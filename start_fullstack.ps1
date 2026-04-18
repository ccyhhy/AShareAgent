param(
    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$AutoStopSeconds = 0,
    [switch]$ForceFreePorts,
    [switch]$NoBootstrapDeps,
    [switch]$NoOpenBrowser
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

function Stop-PidsByPort {
    param([int]$Port)
    $owners = Get-PortOwners -Port $Port
    if (-not $owners -or $owners.Count -eq 0) {
        return
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

function Resolve-AvailablePort {
    param(
        [int]$Preferred,
        [string]$Label,
        [switch]$ForceFree
    )

    if ($ForceFree) {
        Stop-PidsByPort -Port $Preferred
        return $Preferred
    }

    if ((Get-PortOwners -Port $Preferred).Count -eq 0) {
        return $Preferred
    }

    for ($offset = 1; $offset -le 30; $offset++) {
        $candidate = $Preferred + $offset
        if ((Get-PortOwners -Port $candidate).Count -eq 0) {
            Write-Host "$Label port $Preferred is busy; using $candidate instead."
            return $candidate
        }
    }

    throw "No available $Label port found near $Preferred."
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

function Test-PythonImport {
    param(
        [string]$Exe,
        [string]$ModuleName
    )
    & $Exe -c "import $ModuleName" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-BackendDependencies {
    param(
        [string]$Exe,
        [string]$RepoRoot,
        [bool]$AllowInstall
    )
    $requiredModules = @("fastapi", "uvicorn")
    $missing = @()
    foreach ($module in $requiredModules) {
        if (-not (Test-PythonImport -Exe $Exe -ModuleName $module)) {
            $missing += $module
        }
    }

    if ($missing.Count -eq 0) {
        return
    }

    if (-not $AllowInstall) {
        throw "Missing backend dependency modules: $($missing -join ', '). Re-run with -BootstrapDeps `$true."
    }

    $requirementsFile = Join-Path $RepoRoot "requirements.txt"
    if (-not (Test-Path $requirementsFile)) {
        throw "requirements.txt not found: $requirementsFile"
    }

    Write-Host "Installing backend dependencies..."
    & $Exe -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install backend dependencies."
    }
}

function Ensure-FrontendDependencies {
    param(
        [string]$FrontendDir,
        [bool]$AllowInstall
    )
    $nodeModulesDir = Join-Path $FrontendDir "node_modules"
    if (Test-Path $nodeModulesDir) {
        return
    }

    if (-not $AllowInstall) {
        throw "frontend/node_modules is missing. Re-run with -BootstrapDeps `$true."
    }

    Write-Host "Installing frontend dependencies..."
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install frontend dependencies."
    }
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

$repoRoot = $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"
$bootstrapDeps = -not $NoBootstrapDeps
$openBrowser = -not $NoOpenBrowser

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $candidatePaths = @(
        (Join-Path $repoRoot ".venv\Scripts\python.exe"),
        (Join-Path $repoRoot "venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            $PythonExe = $candidate
            break
        }
    }

    if ([string]::IsNullOrWhiteSpace($PythonExe)) {
        $pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            $PythonExe = $pythonCmd.Source
        }
    }
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "Python executable not found. Set -PythonExe or create a .venv/venv in the repository root."
}
if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

Ensure-Command "node"
Ensure-Command "npm.cmd"
Ensure-BackendDependencies -Exe $PythonExe -RepoRoot $repoRoot -AllowInstall:$bootstrapDeps
Push-Location $frontendDir
try {
    Ensure-FrontendDependencies -FrontendDir $frontendDir -AllowInstall:$bootstrapDeps
}
finally {
    Pop-Location
}

$resolvedBackendPort = Resolve-AvailablePort -Preferred $BackendPort -Label "Backend" -ForceFree:$ForceFreePorts
$resolvedFrontendPort = Resolve-AvailablePort -Preferred $FrontendPort -Label "Frontend" -ForceFree:$ForceFreePorts

if ($resolvedBackendPort -eq $resolvedFrontendPort) {
    $resolvedFrontendPort = Resolve-AvailablePort -Preferred ($resolvedFrontendPort + 1) -Label "Frontend" -ForceFree:$ForceFreePorts
}

$backendProc = $null
$frontendProc = $null

try {
    $backendArgs = @(
        "-m", "uvicorn", "backend.main:app",
        "--host", $BindHost,
        "--port", $resolvedBackendPort.ToString()
    )
    $frontendArgs = @(
        "run", "dev", "--",
        "--host", $BindHost,
        "--port", $resolvedFrontendPort.ToString()
    )

    $backendProc = Start-Process -FilePath $PythonExe -ArgumentList $backendArgs -WorkingDirectory $repoRoot -PassThru
    $frontendProc = Start-Process -FilePath "npm.cmd" -ArgumentList $frontendArgs -WorkingDirectory $frontendDir -PassThru

    $frontendUrl = "http://$BindHost`:$resolvedFrontendPort"
    $backendUrl = "http://$BindHost`:$resolvedBackendPort/docs"

    Write-Host ""
    Write-Host "Full stack is starting..."
    Write-Host "Frontend: $frontendUrl"
    Write-Host "Backend : $backendUrl"
    Write-Host "Press Ctrl+C to stop both services."
    Write-Host ""

    [void](Wait-HttpReady -Url $frontendUrl -TimeoutSeconds 40)
    [void](Wait-HttpReady -Url "http://$BindHost`:$resolvedBackendPort/health" -TimeoutSeconds 40)

    if ($openBrowser) {
        try {
            Start-Process $frontendUrl | Out-Null
        }
        catch {
            Write-Host "Unable to open browser automatically: $($_.Exception.Message)"
        }
    }

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
