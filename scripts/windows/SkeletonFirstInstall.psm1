<#
.SYNOPSIS
    Shared functions for the native Windows first install of Skeleton.

.DESCRIPTION
    Used by bootstrap.ps1 (one-command setup) and skeleton.ps1 (launcher).
    Compatible with Windows PowerShell 5.1 and PowerShell 7+. The functions are
    also loadable by PowerShell 7 on Linux/macOS so the same code is exercised
    by developer tests; DPAPI secret protection is Windows-only and other hosts
    fall back to an owner-only (0600) file.

    Nothing here prints a secret value. Downloads are pinned and verified by
    SHA-512 before extraction. All product steps are delegated to
    `python -m skeleton.app.windows_first_install`.
#>

Set-StrictMode -Version 3.0

$script:GodotRelease = '4.6-stable'
$script:GodotAssets = @{
    'windows-x64' = @{
        File   = 'Godot_v4.6-stable_win64.exe.zip'
        Sha512 = '3b2f0b4b3c490cb1a78db8fd2afc924412edab996b436c08e38957388976e9dfaf203cb50a8916036bc810f68da3dd6b9f16561e6549062ef225b4a97877081b'
        Binary = 'Godot_v4.6-stable_win64_console.exe'
    }
    'linux-x64'   = @{
        File   = 'Godot_v4.6-stable_linux.x86_64.zip'
        Sha512 = '0c1bc5e8dca8f892a9a5fd0628b742f399fbd520e5f0051ecac021c0aa4ea5a8f0d237c8ed6b767b2afda7f7a4b32001118f1b04a82e335a5e35b947a1217940'
        Binary = 'Godot_v4.6-stable_linux.x86_64'
    }
}
$script:MinPython = [version]'3.11'
$script:PythonWingetId = 'Python.Python.3.11'
$script:GitWingetId = 'Git.Git'
$script:DefaultPort = 8710
$script:SecretNames = @('GF_SEAL_SECRET', 'OPENAI_API_KEY')
$script:Providers = @('none', 'openai', 'local')

function Test-SkeletonIsWindows {
    [CmdletBinding()] param()
    if (Get-Variable -Name IsWindows -Scope Global -ErrorAction SilentlyContinue) {
        return [bool]$global:IsWindows
    }
    return $true  # Windows PowerShell 5.1 only runs on Windows.
}

function Write-SkeletonStep {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Message, [ValidateSet('step', 'ok', 'warn', 'fail', 'info')][string]$Kind = 'step')
    $prefix = @{ step = '==>'; ok = '[OK]'; warn = '[WARN]'; fail = '[FAIL]'; info = '   ' }[$Kind]
    $color = @{ step = 'Cyan'; ok = 'Green'; warn = 'Yellow'; fail = 'Red'; info = 'Gray' }[$Kind]
    Write-Host "$prefix $Message" -ForegroundColor $color
}

function Get-SkeletonPlatformKey {
    [CmdletBinding()] param()
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    if ($arch -ne 'x64') { return $null }
    if (Test-SkeletonIsWindows) { return 'windows-x64' }
    if ($IsLinux) { return 'linux-x64' }
    return $null
}

function Get-SkeletonLayout {
    <# Per-user data layout. Override with -DataRoot or SKELETON_HOME. #>
    [CmdletBinding()] param([string]$DataRoot)
    if (-not $DataRoot) { $DataRoot = $env:SKELETON_HOME }
    if (-not $DataRoot) {
        if ($env:LOCALAPPDATA) { $DataRoot = Join-Path $env:LOCALAPPDATA 'Skeleton' }
        else { $DataRoot = Join-Path (Join-Path (Join-Path $HOME '.local') 'share') 'skeleton' }
    }
    $root = [System.IO.Path]::GetFullPath($DataRoot)
    [pscustomobject]@{
        Root    = $root
        Config  = Join-Path $root 'config'
        Tools   = Join-Path $root 'tools'
        Logs    = Join-Path $root 'logs'
        Games   = Join-Path $root 'games'
        Run     = Join-Path $root 'run'
        ConfigFile  = Join-Path (Join-Path $root 'config') 'config.json'
        SecretsFile = Join-Path (Join-Path $root 'config') 'secrets.json'
        PidFile     = Join-Path (Join-Path $root 'run') 'api.pid'
    }
}

function Set-SkeletonOwnerOnly {
    <# Restrict a file or directory to the current user (ACL on Windows, chmod elsewhere). #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    if (Test-SkeletonIsWindows) {
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $isDir = Test-Path -LiteralPath $Path -PathType Container
        $grant = if ($isDir) { "${identity}:(OI)(CI)F" } else { "${identity}:F" }
        $out = & icacls.exe $Path /inheritance:r /grant:r $grant 2>&1
        if ($LASTEXITCODE -ne 0) { throw "icacls failed for ${Path}: $out" }
    }
    else {
        $mode = if (Test-Path -LiteralPath $Path -PathType Container) { '700' } else { '600' }
        & chmod $mode $Path | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "chmod failed for $Path" }
    }
}

function Initialize-SkeletonLayout {
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout)
    foreach ($dir in @($Layout.Root, $Layout.Config, $Layout.Tools, $Layout.Logs, $Layout.Games, $Layout.Run)) {
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    }
    Set-SkeletonOwnerOnly -Path $Layout.Config
}

function Test-SkeletonHost {
    <# Returns check objects for OS, PowerShell, architecture, disk space and long paths. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout, [long]$MinFreeBytes = 4GB)
    $checks = New-Object System.Collections.Generic.List[object]
    $platformKey = Get-SkeletonPlatformKey
    $checks.Add([pscustomobject]@{ Id = 'platform'; Ok = [bool]$platformKey; Required = $true
            Detail = "$([System.Runtime.InteropServices.RuntimeInformation]::OSDescription) / $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
            Fix = 'Skeleton first install supports 64-bit Windows 10/11 (x64).' })
    $psOk = $PSVersionTable.PSVersion -ge [version]'5.1'
    $checks.Add([pscustomobject]@{ Id = 'powershell'; Ok = $psOk; Required = $true
            Detail = "PowerShell $($PSVersionTable.PSVersion)"; Fix = 'Use Windows PowerShell 5.1 or PowerShell 7.' })
    $probe = $Layout.Root
    while ($probe -and -not (Test-Path -LiteralPath $probe)) { $probe = Split-Path -Parent $probe }
    $free = $null
    try { $free = ([System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($probe))).AvailableFreeSpace } catch { $free = $null }
    $checks.Add([pscustomobject]@{ Id = 'disk'; Ok = ($null -eq $free -or $free -ge $MinFreeBytes); Required = $true
            Detail = $(if ($null -eq $free) { 'free space unknown' } else { '{0:N1} GiB free' -f ($free / 1GB) })
            Fix = 'Free at least 4 GiB for Python packages, Godot and generated games.' })
    if (Test-SkeletonIsWindows) {
        $long = $false
        try { $long = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled -eq 1 } catch { $long = $false }
        $checks.Add([pscustomobject]@{ Id = 'long_paths'; Ok = $long; Required = $false
                Detail = $(if ($long) { 'Win32 long paths enabled' } else { 'Win32 long paths disabled' })
                Fix = 'Optional: enable long paths (admin): New-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force' })
    }
    return , $checks.ToArray()
}

function Get-SkeletonPythonVersion {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Exe, [string[]]$Prefix = @())
    try {
        $out = & $Exe @Prefix -c 'import sys; print(sys.executable); print("%d.%d.%d" % sys.version_info[:3])' 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $lines = @($out)
        if ($lines.Count -lt 2) { return $null }
        # The Microsoft Store alias prints nothing and exits non-zero; real interpreters report both lines.
        return [pscustomobject]@{ Path = $lines[0].Trim(); Version = [version]$lines[1].Trim() }
    }
    catch { return $null }
}

function Find-SkeletonPython {
    <# Find Python >= 3.11: explicit path, py launcher (newest first), then PATH. #>
    [CmdletBinding()] param([string]$Explicit)
    $candidates = New-Object System.Collections.Generic.List[object]
    if ($Explicit) { $candidates.Add(@($Explicit, @())) }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($minor in '3.13', '3.12', '3.11', '3.14') { $candidates.Add(@('py', @("-$minor"))) }
    }
    foreach ($name in 'python', 'python3') {
        $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { $candidates.Add(@($cmd.Source, @())) }
    }
    foreach ($candidate in $candidates) {
        $found = Get-SkeletonPythonVersion -Exe $candidate[0] -Prefix $candidate[1]
        if ($found -and $found.Version -ge $script:MinPython) { return $found }
    }
    return $null
}

function Install-SkeletonWingetPackage {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Id)
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is not available. Install '$Id' manually (https://aka.ms/getwinget) and re-run."
    }
    Write-SkeletonStep "Installing $Id with winget (per-user)"
    & winget install --id $Id --exact --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {  # 0x8A15002B: already installed
        throw "winget install $Id failed with exit code $LASTEXITCODE"
    }
    # Refresh PATH for this session so the new tools resolve without a new shell.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
}

function Get-SkeletonFileSha512 {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA512).Hash.ToLowerInvariant()
}

function Install-SkeletonGodot {
    <# Download the pinned Godot release, verify SHA-512, extract under tools\. Returns the console binary path. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout, [string]$ArchivePath, [switch]$Force)
    $key = Get-SkeletonPlatformKey
    if (-not $key) { throw 'No pinned Godot build for this platform/architecture.' }
    $asset = $script:GodotAssets[$key]
    $dest = Join-Path $Layout.Tools "godot-$($script:GodotRelease)"
    $binary = Join-Path $dest $asset.Binary
    if ((Test-Path -LiteralPath $binary) -and -not $Force) { return $binary }
    $archive = $ArchivePath
    if (-not $archive) {
        $archive = Join-Path $Layout.Tools $asset.File
        if (-not (Test-Path -LiteralPath $archive) -or ((Get-SkeletonFileSha512 $archive) -ne $asset.Sha512)) {
            $url = "https://github.com/godotengine/godot/releases/download/$($script:GodotRelease)/$($asset.File)"
            Write-SkeletonStep "Downloading Godot $($script:GodotRelease) ($($asset.File))"
            $partial = "$archive.partial"
            $previous = $ProgressPreference
            $ProgressPreference = 'SilentlyContinue'
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
                Invoke-WebRequest -Uri $url -OutFile $partial -UseBasicParsing -MaximumRedirection 5
            }
            finally { $ProgressPreference = $previous }
            Move-Item -LiteralPath $partial -Destination $archive -Force
        }
    }
    $actual = Get-SkeletonFileSha512 $archive
    if ($actual -ne $asset.Sha512) {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        throw "Godot archive SHA-512 mismatch (expected $($asset.Sha512.Substring(0,16))..., got $($actual.Substring(0,16))...). The download was discarded."
    }
    $staging = "$dest.partial"
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    Expand-Archive -LiteralPath $archive -DestinationPath $staging -Force
    if (-not (Test-Path -LiteralPath (Join-Path $staging $asset.Binary))) {
        Remove-Item -LiteralPath $staging -Recurse -Force
        throw "Godot archive did not contain $($asset.Binary)"
    }
    if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
    Move-Item -LiteralPath $staging -Destination $dest
    if (-not (Test-SkeletonIsWindows)) { & chmod +x $binary | Out-Null }
    return $binary
}

function Get-SkeletonVenvPython {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$RepoRoot)
    if (Test-SkeletonIsWindows) { return Join-Path $RepoRoot '.venv\Scripts\python.exe' }
    return Join-Path (Join-Path (Join-Path $RepoRoot '.venv') 'bin') 'python'
}

function ConvertTo-SkeletonConstraints {
    <#
    Turn a requirements file into a pip constraints file: pip rejects extras,
    editables and options in constraints, so keep only "name==version[; marker]".
    #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Requirements, [Parameter(Mandatory)][string]$Destination)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($raw in Get-Content -LiteralPath $Requirements) {
        $line = ($raw -replace '\s+#.*$', '').Trim()
        if (-not $line -or $line.StartsWith('#') -or $line.StartsWith('-')) { continue }
        $line = $line -replace '\[[^\]]*\]', ''
        if ($line -match '^[A-Za-z0-9][A-Za-z0-9._-]*\s*==\s*[^\s;]+(\s*;.*)?$') { $out.Add($line) }
    }
    Set-Content -LiteralPath $Destination -Value $out -Encoding ASCII
    return $out.Count
}

function Initialize-SkeletonVenv {
    <# Create .venv and install Skeleton with the backend's pinned versions as constraints. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)]$Python, [Parameter(Mandatory)]$Layout)
    $venvPython = Get-SkeletonVenvPython -RepoRoot $RepoRoot
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-SkeletonStep "Creating virtual environment (.venv) with Python $($Python.Version)"
        & $Python.Path -m venv (Join-Path $RepoRoot '.venv') | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'python -m venv failed' }
    }
    $pinned = Join-Path (Join-Path $RepoRoot 'backend') 'requirements.txt'
    $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--require-virtualenv')
    if (Test-Path -LiteralPath $pinned) {
        $constraints = Join-Path $Layout.Run 'constraints.txt'
        $count = ConvertTo-SkeletonConstraints -Requirements $pinned -Destination $constraints
        Write-SkeletonStep "Using $count pinned versions from backend\requirements.txt as constraints" -Kind info
        $pipArgs += @('--constraint', $constraints)
    }
    $pipArgs += @('--editable', $RepoRoot)
    Write-SkeletonStep 'Installing Skeleton and pinned dependencies (first run takes a few minutes)'
    $previous = $env:PIP_DISABLE_PIP_VERSION_CHECK
    try {
        $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
        & $venvPython @pipArgs | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE" }
    }
    finally { $env:PIP_DISABLE_PIP_VERSION_CHECK = $previous }
    return $venvPython
}

function Protect-SkeletonSecretText {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Plain)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Plain)
    if (Test-SkeletonIsWindows) {
        Add-Type -AssemblyName System.Security -ErrorAction SilentlyContinue
        $protected = [System.Security.Cryptography.ProtectedData]::Protect($bytes, [System.Text.Encoding]::UTF8.GetBytes('skeleton-first-install'), [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
        return 'dpapi:' + [Convert]::ToBase64String($protected)
    }
    return 'plain0600:' + [Convert]::ToBase64String($bytes)
}

function Unprotect-SkeletonSecretText {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Stored)
    if ($Stored.StartsWith('dpapi:')) {
        Add-Type -AssemblyName System.Security -ErrorAction SilentlyContinue
        $raw = [Convert]::FromBase64String($Stored.Substring(6))
        $plain = [System.Security.Cryptography.ProtectedData]::Unprotect($raw, [System.Text.Encoding]::UTF8.GetBytes('skeleton-first-install'), [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
        return [System.Text.Encoding]::UTF8.GetString($plain)
    }
    if ($Stored.StartsWith('plain0600:')) {
        return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Stored.Substring(10)))
    }
    throw 'Unknown secret encoding in secrets.json'
}

function New-SkeletonRandomSecret {
    [CmdletBinding()] param([int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return (($buffer | ForEach-Object { $_.ToString('x2') }) -join '')
}

function ConvertFrom-SkeletonSecureString {
    [CmdletBinding()] param([Parameter(Mandatory)][System.Security.SecureString]$Secure)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Read-SkeletonSecrets {
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout)
    $result = @{}
    if (-not (Test-Path -LiteralPath $Layout.SecretsFile)) { return $result }
    $doc = Get-Content -LiteralPath $Layout.SecretsFile -Raw | ConvertFrom-Json
    foreach ($property in $doc.values.PSObject.Properties) {
        if ($script:SecretNames -contains $property.Name) {
            $result[$property.Name] = Unprotect-SkeletonSecretText -Stored ([string]$property.Value)
        }
    }
    return $result
}

function Write-SkeletonSecrets {
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout, [Parameter(Mandatory)][hashtable]$Values)
    $stored = [ordered]@{}
    foreach ($name in ($Values.Keys | Sort-Object)) {
        if ($script:SecretNames -notcontains $name) { throw "Refusing to store unknown secret '$name'" }
        if ($Values[$name]) { $stored[$name] = Protect-SkeletonSecretText -Plain $Values[$name] }
    }
    $doc = [ordered]@{ schema = 'skeleton.windows_first_install.secrets.v1'; values = $stored }
    $tmp = "$($Layout.SecretsFile).tmp"
    ($doc | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $tmp -Encoding UTF8
    Set-SkeletonOwnerOnly -Path $tmp
    Move-Item -LiteralPath $tmp -Destination $Layout.SecretsFile -Force
}

function Get-SkeletonConfig {
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout)
    if (-not (Test-Path -LiteralPath $Layout.ConfigFile)) { return $null }
    return Get-Content -LiteralPath $Layout.ConfigFile -Raw | ConvertFrom-Json
}

function Set-SkeletonConfig {
    <# Write non-secret config and (re)store secrets. An existing seal secret is preserved unless -RotateSeal. #>
    [CmdletBinding()] param(
        [Parameter(Mandatory)]$Layout,
        [Parameter(Mandatory)][string]$RepoRoot,
        [ValidateSet('none', 'openai', 'local')][string]$Provider = 'none',
        [string]$Model = '',
        [string]$OpenAIBaseUrl = '',
        [int]$Port = 8710,
        [string]$GodotPath = '',
        [System.Security.SecureString]$ApiKey,
        [switch]$RotateSeal
    )
    if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535' }
    if ($OpenAIBaseUrl -and $OpenAIBaseUrl -notmatch '^https://') { throw 'OpenAI-compatible base URL must use https://' }
    $secrets = Read-SkeletonSecrets -Layout $Layout
    if ($RotateSeal -or -not $secrets.ContainsKey('GF_SEAL_SECRET')) { $secrets['GF_SEAL_SECRET'] = New-SkeletonRandomSecret }
    if ($Provider -eq 'openai') {
        if ($ApiKey) { $secrets['OPENAI_API_KEY'] = ConvertFrom-SkeletonSecureString -Secure $ApiKey }
        if (-not $secrets.ContainsKey('OPENAI_API_KEY')) { throw 'Provider openai needs an API key (-ApiKey or OPENAI_API_KEY).' }
    }
    elseif ($secrets.ContainsKey('OPENAI_API_KEY')) { $secrets.Remove('OPENAI_API_KEY') }
    Write-SkeletonSecrets -Layout $Layout -Values $secrets
    $config = [ordered]@{
        schema       = 'skeleton.windows_first_install.config.v1'
        repo_root    = $RepoRoot
        provider     = $Provider
        model        = $Model
        openai_base_url = $OpenAIBaseUrl
        port         = $Port
        godot        = $GodotPath
        games_dir    = $Layout.Games
        godot_release = $script:GodotRelease
        updated_utc  = [DateTime]::UtcNow.ToString('o')
    }
    $tmp = "$($Layout.ConfigFile).tmp"
    ($config | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $Layout.ConfigFile -Force
    return [pscustomobject]$config
}

function Get-SkeletonChildEnvironment {
    <# Environment for the Python child processes. Contains secrets: never log it. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout)
    $config = Get-SkeletonConfig -Layout $Layout
    if (-not $config) { throw 'Skeleton is not configured yet. Run scripts\windows\bootstrap.ps1 first.' }
    $secrets = Read-SkeletonSecrets -Layout $Layout
    $envMap = [ordered]@{
        SKELETON_HOME      = $Layout.Root
        SKELETON_GAMES_DIR = [string]$config.games_dir
        SKELETON_API_PORT  = [string]$config.port
        PYTHONUTF8         = '1'
        PYTHONIOENCODING   = 'utf-8'
        GF_SEAL_SECRET     = $secrets['GF_SEAL_SECRET']
    }
    if ($config.godot) { $envMap['SKELETON_GODOT_BIN'] = [string]$config.godot }
    switch ([string]$config.provider) {
        'openai' {
            $envMap['AI_PROVIDER'] = 'openai'
            $envMap['OPENAI_API_KEY'] = $secrets['OPENAI_API_KEY']
            if ($config.model) { $envMap['AI_MODEL'] = [string]$config.model }
            if ($config.openai_base_url) { $envMap['OPENAI_BASE_URL'] = [string]$config.openai_base_url }
        }
        'local' { $envMap['AI_PROVIDER'] = 'local' }
        default { }
    }
    return $envMap
}

function Invoke-SkeletonWithEnvironment {
    <# Run a script block with temporary process environment variables, restoring them afterwards. #>
    [CmdletBinding()] param([Parameter(Mandatory)][System.Collections.IDictionary]$Environment, [Parameter(Mandatory)][scriptblock]$Script)
    $saved = @{}
    foreach ($name in $Environment.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, [string]$Environment[$name], 'Process')
    }
    try { return & $Script }
    finally {
        foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    }
}

function Invoke-SkeletonPython {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)]$Layout, [string[]]$Arguments = @())
    $py = Get-SkeletonVenvPython -RepoRoot $RepoRoot
    if (-not (Test-Path -LiteralPath $py)) { throw 'The .venv is missing. Run scripts\windows\bootstrap.ps1 first.' }
    $envMap = Get-SkeletonChildEnvironment -Layout $Layout
    Push-Location $RepoRoot
    try {
        Invoke-SkeletonWithEnvironment -Environment $envMap -Script {
            & $py -m skeleton.app.windows_first_install @Arguments
            $global:LASTEXITCODE = $LASTEXITCODE
        } | Out-Host
        return $global:LASTEXITCODE
    }
    finally { Pop-Location }
}

function Get-SkeletonApiProcess {
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout)
    if (-not (Test-Path -LiteralPath $Layout.PidFile)) { return $null }
    $raw = (Get-Content -LiteralPath $Layout.PidFile -Raw).Trim()
    $procId = 0
    if (-not [int]::TryParse($raw, [ref]$procId)) { return $null }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -match '^python') { return $proc }
    return $null
}

function Start-SkeletonApi {
    <# Start the loopback API in the background, logging to logs\api-*.log. Returns the process. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)]$Layout)
    $existing = Get-SkeletonApiProcess -Layout $Layout
    if ($existing) { return $existing }
    $py = Get-SkeletonVenvPython -RepoRoot $RepoRoot
    if (-not (Test-Path -LiteralPath $py)) { throw 'The .venv is missing. Run scripts\windows\bootstrap.ps1 first.' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $out = Join-Path $Layout.Logs "api-$stamp.out.log"
    $err = Join-Path $Layout.Logs "api-$stamp.err.log"
    $envMap = Get-SkeletonChildEnvironment -Layout $Layout
    $startArgs = @{
        FilePath               = $py
        ArgumentList           = @('-m', 'skeleton.app.windows_first_install', 'serve')
        WorkingDirectory       = $RepoRoot
        RedirectStandardOutput = $out
        RedirectStandardError  = $err
        PassThru               = $true
    }
    if (Test-SkeletonIsWindows) { $startArgs['WindowStyle'] = 'Hidden' }
    $proc = Invoke-SkeletonWithEnvironment -Environment $envMap -Script { Start-Process @startArgs }
    Set-Content -LiteralPath $Layout.PidFile -Value $proc.Id -Encoding ASCII
    return $proc
}

function Stop-SkeletonApi {
    [CmdletBinding()] param([Parameter(Mandatory)]$Layout)
    $proc = Get-SkeletonApiProcess -Layout $Layout
    if ($proc) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; $proc.WaitForExit(10000) | Out-Null }
    if (Test-Path -LiteralPath $Layout.PidFile) { Remove-Item -LiteralPath $Layout.PidFile -Force }
    return [bool]$proc
}

function Wait-SkeletonApi {
    <# Poll the open liveness probe until the API answers or the timeout elapses. #>
    [CmdletBinding()] param([int]$Port = 8710, [int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/health/live" -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) { return $true }
        }
        catch {
            # 401 means the app is up but the probe is sealed on this build: still "listening".
            $status = $null
            try { $status = [int]$_.Exception.Response.StatusCode } catch { $status = $null }
            if ($status -eq 401) { return $true }
        }
        Start-Sleep -Milliseconds 750
    }
    return $false
}

Export-ModuleMember -Function *-Skeleton*
