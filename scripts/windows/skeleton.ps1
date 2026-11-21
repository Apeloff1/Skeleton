<#
.SYNOPSIS
    Skeleton launcher for a native Windows install (after bootstrap.ps1).

.DESCRIPTION
    skeleton.ps1 start            Start the local API in the background (loopback only)
    skeleton.ps1 start -Foreground  Run the API in this window (Ctrl+C to stop)
    skeleton.ps1 stop             Stop the background API
    skeleton.ps1 status           Show whether the API is running
    skeleton.ps1 doctor           Check Python, Godot, config and secrets
    skeleton.ps1 build "<idea>"   Build a playable game from a sentence (starts the API if needed)
    skeleton.ps1 play [folder]    Open the newest (or given) game in Godot; -Check proves it headlessly
    skeleton.ps1 smoke            Build and headlessly play a sample game
    skeleton.ps1 games            Open the games folder
    skeleton.ps1 logs             Show the newest API log
    skeleton.ps1 config -Provider none|openai|local [-Model m] [-RotateSeal]
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)][ValidateSet('start', 'stop', 'status', 'doctor', 'build', 'play', 'smoke', 'games', 'logs', 'config', 'help')]
    [string]$Command = 'help',
    [Parameter(Position = 1)][string]$Target,
    [switch]$Foreground,
    [switch]$Check,
    [switch]$Json,
    [ValidateSet('none', 'openai', 'local')][string]$Provider,
    [string]$Model,
    [System.Security.SecureString]$ApiKey,
    [switch]$RotateSeal,
    [string]$DataRoot
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Import-Module (Join-Path $PSScriptRoot 'SkeletonFirstInstall.psm1') -Force
$layout = Get-SkeletonLayout -DataRoot $DataRoot
if ($DataRoot) { $env:SKELETON_HOME = $layout.Root }

function Get-Port {
    $config = Get-SkeletonConfig -Layout $layout
    if (-not $config) { throw 'Skeleton is not configured yet. Run scripts\windows\bootstrap.ps1 first.' }
    return [int]$config.port
}

function Start-ApiIfNeeded {
    $port = Get-Port
    $proc = Get-SkeletonApiProcess -Layout $layout
    if (-not $proc) {
        Write-SkeletonStep "Starting the Skeleton API on http://127.0.0.1:$port"
        $proc = Start-SkeletonApi -RepoRoot $RepoRoot -Layout $layout
    }
    if (-not (Wait-SkeletonApi -Port $port -TimeoutSeconds 120)) {
        throw "The API is not answering on port $port. Run: skeleton.ps1 logs"
    }
    return $proc
}

$common = @()
if ($Json) { $common += '--json' }

try {
    switch ($Command) {
        'start' {
            if ($Foreground) {
                $code = Invoke-SkeletonPython -RepoRoot $RepoRoot -Layout $layout -Arguments @('serve')
                exit $code
            }
            $proc = Start-ApiIfNeeded
            Write-SkeletonStep "Skeleton API running at http://127.0.0.1:$(Get-Port) (pid $($proc.Id))" -Kind ok
        }
        'stop' {
            if (Stop-SkeletonApi -Layout $layout) { Write-SkeletonStep 'Stopped.' -Kind ok }
            else { Write-SkeletonStep 'The API was not running.' -Kind info }
        }
        'status' {
            $proc = Get-SkeletonApiProcess -Layout $layout
            if ($proc) { Write-SkeletonStep "Running (pid $($proc.Id)) on http://127.0.0.1:$(Get-Port)" -Kind ok }
            else { Write-SkeletonStep 'Not running. Start it with: skeleton.ps1 start' -Kind info; exit 3 }
        }
        'doctor' { exit (Invoke-SkeletonPython -RepoRoot $RepoRoot -Layout $layout -Arguments ($common + @('doctor'))) }
        'build' {
            if (-not $Target) { throw 'Describe the game, e.g.: skeleton.ps1 build "A small platformer about a fox in a rainy city"' }
            Start-ApiIfNeeded | Out-Null
            exit (Invoke-SkeletonPython -RepoRoot $RepoRoot -Layout $layout -Arguments ($common + @('build', $Target)))
        }
        'smoke' {
            Start-ApiIfNeeded | Out-Null
            $smokeArgs = $common + @('smoke')
            if ($Target) { $smokeArgs += $Target }
            exit (Invoke-SkeletonPython -RepoRoot $RepoRoot -Layout $layout -Arguments $smokeArgs)
        }
        'play' {
            $playArgs = $common + @('play')
            if ($Target) { $playArgs += $Target }
            if ($Check) { $playArgs += '--check' }
            exit (Invoke-SkeletonPython -RepoRoot $RepoRoot -Layout $layout -Arguments $playArgs)
        }
        'games' {
            if (Test-SkeletonIsWindows) { Start-Process explorer.exe -ArgumentList $layout.Games }
            else { Write-Host $layout.Games }
        }
        'logs' {
            $log = Get-ChildItem -LiteralPath $layout.Logs -Filter 'api-*.log' -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 2
            if (-not $log) { Write-SkeletonStep 'No API logs yet.' -Kind info }
            foreach ($file in $log) { Write-Host "--- $($file.FullName)"; Get-Content -LiteralPath $file.FullName -Tail 60 }
        }
        'config' {
            $existing = Get-SkeletonConfig -Layout $layout
            if (-not $existing) { throw 'Run scripts\windows\bootstrap.ps1 first.' }
            if (-not $Provider) { $Provider = [string]$existing.provider }
            if (-not $PSBoundParameters.ContainsKey('Model')) { $Model = [string]$existing.model }
            if ($Provider -eq 'openai' -and -not $ApiKey -and -not (Read-SkeletonSecretStore -Layout $layout).ContainsKey('OPENAI_API_KEY')) {
                $ApiKey = Read-Host 'OpenAI-compatible API key (input hidden)' -AsSecureString
            }
            $config = Set-SkeletonConfig -Layout $layout -RepoRoot $RepoRoot -Provider $Provider -Model $Model `
                -OpenAIBaseUrl ([string]$existing.openai_base_url) -Port ([int]$existing.port) -GodotPath ([string]$existing.godot) `
                -ApiKey $ApiKey -RotateSeal:$RotateSeal
            Write-SkeletonStep "Saved: provider=$($config.provider) model=$($config.model). Restart with: skeleton.ps1 stop; skeleton.ps1 start" -Kind ok
        }
        default { Get-Help $PSCommandPath -Detailed | Out-Host }
    }
}
catch {
    Write-SkeletonStep $_.Exception.Message -Kind fail
    exit 1
}
