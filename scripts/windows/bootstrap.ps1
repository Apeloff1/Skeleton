<#
.SYNOPSIS
    One-command native Windows first install for Skeleton.

.DESCRIPTION
    From a fresh clone:

        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1 -InstallMissing -Start

    1. Checks the host (64-bit Windows 10/11, PowerShell, disk space, long paths).
    2. Finds Python 3.11+ (or installs Python 3.11 per-user with winget when -InstallMissing).
    3. Downloads the pinned Godot 4.6 build and verifies its SHA-512.
    4. Creates .venv and installs Skeleton with the backend's pinned versions as constraints.
    5. Writes per-user config under %LOCALAPPDATA%\Skeleton (owner-only ACL) and a DPAPI-protected
       secrets file: a fresh request-seal secret, plus a hosted API key only if you choose one.
    6. Runs the doctor. With -Start it launches the local API; with -Smoke it also builds and
       headlessly plays a sample game (the same check CI runs on windows-latest).

    No Docker, MongoDB or administrator rights are needed for this path. The full Docker
    Compose studio remains available through scripts\install_app.py (see the docs).

.PARAMETER Provider
    none (default; the deterministic game builder needs no model), openai (hosted, needs a key),
    or local (guarded local model; needs the trusted guard bootstrap described in the docs).

.EXAMPLE
    scripts\windows\bootstrap.ps1 -InstallMissing -Start

.EXAMPLE
    scripts\windows\bootstrap.ps1 -Provider openai -Model gpt-5.5

.LINK
    docs/install/windows-first-install.md
#>
[CmdletBinding()]
param(
    [switch]$InstallMissing,
    [ValidateSet('none', 'openai', 'local')][string]$Provider,
    [string]$Model = '',
    [string]$OpenAIBaseUrl = '',
    [System.Security.SecureString]$ApiKey,
    [ValidateRange(1024, 65535)][int]$Port = 8710,
    [string]$PythonPath,
    [string]$GodotPath,
    [string]$GodotArchive,
    [switch]$SkipGodot,
    [string]$DataRoot,
    [switch]$RotateSeal,
    [switch]$Start,
    [switch]$Smoke,
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Import-Module (Join-Path $PSScriptRoot 'SkeletonFirstInstall.psm1') -Force

$layout = Get-SkeletonLayout -DataRoot $DataRoot
if ($DataRoot) { $env:SKELETON_HOME = $layout.Root }
Initialize-SkeletonLayout -Layout $layout
$transcript = Join-Path $layout.Logs ("bootstrap-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
try { Start-Transcript -Path $transcript -Append | Out-Null } catch { $transcript = $null }

try {
    Write-SkeletonStep "Skeleton first install (repo: $RepoRoot, data: $($layout.Root))"

    # 1. Host
    Write-SkeletonStep 'Checking this computer'
    $hostChecks = Test-SkeletonHost -Layout $layout
    foreach ($check in $hostChecks) {
        $kind = if ($check.Ok) { 'ok' } elseif ($check.Required) { 'fail' } else { 'warn' }
        Write-SkeletonStep "$($check.Id): $($check.Detail)" -Kind $kind
        if (-not $check.Ok) { Write-SkeletonStep "fix: $($check.Fix)" -Kind info }
    }
    if (@($hostChecks | Where-Object { $_.Required -and -not $_.Ok }).Count -gt 0) {
        throw 'This computer does not meet the requirements above.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'pyproject.toml'))) {
        throw "Run this script from a Skeleton checkout (pyproject.toml not found under $RepoRoot)."
    }

    # 2. Python
    Write-SkeletonStep 'Finding Python 3.11+'
    $python = Find-SkeletonPython -Explicit $PythonPath
    if (-not $python -and $InstallMissing -and (Test-SkeletonIsWindows)) {
        Install-SkeletonWingetPackage -Id 'Python.Python.3.11'
        $python = Find-SkeletonPython -Explicit $PythonPath
    }
    if (-not $python) {
        throw 'Python 3.11 or newer was not found. Re-run with -InstallMissing, or install it from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH").'
    }
    Write-SkeletonStep "Python $($python.Version) at $($python.Path)" -Kind ok
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if ($InstallMissing -and (Test-SkeletonIsWindows)) { Install-SkeletonWingetPackage -Id 'Git.Git' }
        else { Write-SkeletonStep 'Git not found: optional for running, needed to update (winget install Git.Git).' -Kind warn }
    }

    # 3. Godot
    $godot = $GodotPath
    if ($godot) {
        if (-not (Test-Path -LiteralPath $godot)) { throw "Godot binary not found: $godot" }
        Write-SkeletonStep "Using Godot at $godot" -Kind ok
    }
    elseif (-not $SkipGodot) {
        Write-SkeletonStep 'Installing the pinned Godot engine'
        $godot = Install-SkeletonGodot -Layout $layout -ArchivePath $GodotArchive
        Write-SkeletonStep "Godot ready: $godot (SHA-512 verified)" -Kind ok
    }
    else { Write-SkeletonStep 'Skipping Godot: games can be built but not played or proven.' -Kind warn }

    # 4. Dependencies
    $venvPython = Initialize-SkeletonVenv -RepoRoot $RepoRoot -Python $python -Layout $layout
    Write-SkeletonStep "Dependencies installed into $venvPython" -Kind ok

    # 5. Configuration and secrets
    $existing = Get-SkeletonConfig -Layout $layout
    if (-not $Provider) {
        if ($existing) { $Provider = [string]$existing.provider }
        elseif ($NonInteractive) { $Provider = 'none' }
        else {
            Write-Host ''
            Write-Host 'Choose an AI provider (you can change this later with: skeleton.ps1 config):'
            Write-Host '  1) none   - build games with the deterministic builder (recommended to start)'
            Write-Host '  2) openai - hosted model for chat/design help (needs an API key)'
            Write-Host '  3) local  - guarded local model (advanced; see docs)'
            $choice = Read-Host 'Provider [1]'
            $Provider = @{ '' = 'none'; '1' = 'none'; '2' = 'openai'; '3' = 'local' }[$choice.Trim()]
            if (-not $Provider) { throw "Unknown choice '$choice'" }
        }
    }
    if ($Provider -eq 'openai' -and -not $ApiKey) {
        if ($env:OPENAI_API_KEY) {
            $ApiKey = ConvertTo-SecureString -String $env:OPENAI_API_KEY -AsPlainText -Force
        }
        elseif (-not $NonInteractive -and -not ((Read-SkeletonSecretStore -Layout $layout).ContainsKey('OPENAI_API_KEY'))) {
            $ApiKey = Read-Host 'OpenAI-compatible API key (input hidden)' -AsSecureString
        }
    }
    if (-not $Model -and $existing) { $Model = [string]$existing.model }
    $config = Set-SkeletonConfig -Layout $layout -RepoRoot $RepoRoot -Provider $Provider -Model $Model `
        -OpenAIBaseUrl $OpenAIBaseUrl -Port $Port -GodotPath ([string]$godot) -ApiKey $ApiKey -RotateSeal:$RotateSeal
    Write-SkeletonStep "Configuration saved (provider: $($config.provider), port: $($config.port)); secrets are protected for $([Environment]::UserName) only" -Kind ok

    # 6. Doctor, start, smoke
    Write-SkeletonStep 'Running the Skeleton doctor'
    $doctorArgs = @('doctor')
    if (-not $godot) { $doctorArgs += '--no-godot' }
    $code = Invoke-SkeletonPython -RepoRoot $RepoRoot -Layout $layout -Arguments $doctorArgs
    if ($code -ne 0) { throw "Doctor reported problems (exit $code). Fix them and re-run bootstrap.ps1." }

    if ($Start -or $Smoke) {
        Write-SkeletonStep "Starting the Skeleton API on http://127.0.0.1:$($config.port)"
        $proc = Start-SkeletonApi -RepoRoot $RepoRoot -Layout $layout
        if (-not (Wait-SkeletonApi -Port $config.port -TimeoutSeconds 120)) {
            throw "The API did not start; see logs in $($layout.Logs)"
        }
        Write-SkeletonStep "API running (pid $($proc.Id)); logs in $($layout.Logs)" -Kind ok
    }
    if ($Smoke) {
        Write-SkeletonStep 'Smoke test: build and play a sample game'
        $code = Invoke-SkeletonPython -RepoRoot $RepoRoot -Layout $layout -Arguments @('smoke')
        if ($code -ne 0) { throw "Smoke test failed (exit $code)." }
        Write-SkeletonStep 'Smoke test passed' -Kind ok
    }

    Write-Host ''
    Write-SkeletonStep 'Skeleton is installed.' -Kind ok
    Write-Host '  Start the app:      scripts\windows\skeleton.cmd start'
    Write-Host '  Build a game:       scripts\windows\skeleton.cmd build "A small platformer about a fox in a rainy city"'
    Write-Host '  Play the last game: scripts\windows\skeleton.cmd play'
    Write-Host '  Check health:       scripts\windows\skeleton.cmd doctor'
    if ($transcript) { Write-Host "  Install log:        $transcript" }
    $exitCode = 0
}
catch {
    Write-SkeletonStep $_.Exception.Message -Kind fail
    Write-SkeletonStep 'See docs\install\windows-first-install.md#troubleshooting' -Kind info
    if ($transcript) { Write-SkeletonStep "Install log: $transcript" -Kind info }
    $exitCode = 1
}
finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch { Write-Verbose "Transcript was already stopped." } }
}
exit $exitCode
