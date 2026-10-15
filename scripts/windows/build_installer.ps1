param(
    [string]$Version = "",
    [string]$SourceRef = "HEAD"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PyProjectPath = Join-Path $RepoRoot "pyproject.toml"
$BuildRoot = Join-Path $RepoRoot ".build\windows-installer"
$OutputDir = Join-Path $RepoRoot "dist\windows"
$ShortDrive = "W:"
# Do not use Join-Path against the virtual drive until SUBST has created it.
# PowerShell validates PSDrive existence during Join-Path resolution.
$PayloadDir = "$ShortDrive\payload"
$LauncherDist = "$ShortDrive\launcher-dist"
$LauncherWork = "$ShortDrive\launcher-work"
$LauncherSpec = "$ShortDrive\launcher-spec"
$ArchivePath = "$ShortDrive\source.zip"
# The compiled entrypoints and installer recipe must come from the archived
# SourceRef, not potentially divergent files in the working checkout.

if (-not $Version) {
    $PyProject = Get-Content -Raw -LiteralPath $PyProjectPath
    if ($PyProject -notmatch '(?ms)^\[project\].*?^version\s*=\s*"([^"]+)"') {
        throw "Unable to resolve [project].version from pyproject.toml"
    }
    $Version = $Matches[1]
}

if ($Version -notmatch '^\d+\.\d+\.\d+(?:[.-].*)?$') {
    throw "Installer version must begin with numeric major.minor.patch: $Version"
}

$NumericVersion = ($Version -split '[.-]')[0..2] -join '.'
$VersionInfoVersion = "$NumericVersion.0"

foreach ($Path in @($BuildRoot, $OutputDir)) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path $BuildRoot, $OutputDir | Out-Null

if (Test-Path $ShortDrive) {
    throw "Temporary build drive $ShortDrive is already in use"
}
& subst $ShortDrive $BuildRoot
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ShortDrive)) {
    throw "Unable to create short Windows build drive $ShortDrive"
}
try {
New-Item -ItemType Directory -Force -Path $PayloadDir, $LauncherDist, $LauncherWork, $LauncherSpec | Out-Null

Write-Host "==> Staging curated application payload from $SourceRef via $ShortDrive"
# Read the assembly contract from the exact archived ref. All declared required
# paths must be carried into the installable payload, not just the five services.
$SourceManifestText = & git -C $RepoRoot show "$($SourceRef):skeleton/app/manifest.json"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to load application assembly manifest from SourceRef $SourceRef"
}
$SourceManifest = ($SourceManifestText -join "`n") | ConvertFrom-Json
if (-not $SourceManifest.required_paths) {
    throw "Archived application manifest has no required_paths"
}
$RuntimePaths = @(
    ".dockerignore",
    ".env.example",
    "Dockerfile",
    "README.md",
    "docker-compose.yml",
    "docker-compose.hot.yml",
    "pyproject.toml",
    "requirements.txt",
    "backend",
    "frontend",
    "skeleton",
    "scripts",
    "packaging",
    "machine/manifest.json",
    # Historical MasterMap progression snapshots are repository evidence, not
    # runtime inputs. Some intentionally verbose names breach Win32's legacy
    # destination-path boundary when installed under a normal user profile.
    ":(exclude)backend/gameforge/jeeves/jeeves_mastermap_*.json",
    ":(exclude)skeleton/ai/research/legacy/gameforge/jeeves/jeeves_mastermap_*.json"
) + @($SourceManifest.required_paths)
$RuntimePaths = @($RuntimePaths | Select-Object -Unique)
$ArchiveArgs = @(
    "-C", $RepoRoot,
    "archive",
    "--format=zip",
    "--output=$ArchivePath",
    $SourceRef,
    "--"
) + $RuntimePaths
& git @ArchiveArgs
if ($LASTEXITCODE -ne 0) {
    throw "git archive failed"
}
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $PayloadDir -Force

foreach ($RequiredPath in $SourceManifest.required_paths) {
    $StagedPath = Join-Path $PayloadDir $RequiredPath
    if (-not (Test-Path -LiteralPath $StagedPath -PathType Leaf)) {
        throw "Windows payload missing required assembly path: $RequiredPath"
    }
}

$EntryPoint = Join-Path $PayloadDir "packaging\windows\launcher_entry.py"
$ConsoleEntryPoint = Join-Path $PayloadDir "packaging\windows\offline_cli_entry.py"
$InstallerScript = Join-Path $PayloadDir "packaging\windows\SkeletonSetup.iss"
foreach ($RequiredSource in @($EntryPoint, $ConsoleEntryPoint, $InstallerScript)) {
    if (-not (Test-Path -LiteralPath $RequiredSource -PathType Leaf)) {
        throw "Staged installer source missing: $RequiredSource"
    }
}
$StagedPyProject = Get-Content -Raw -LiteralPath (Join-Path $PayloadDir "pyproject.toml")
if ($StagedPyProject -notmatch '(?ms)^\[project\].*?^version\s*=\s*"([^"]+)"') {
    throw "Staged pyproject.toml has no project version"
}
if ($Matches[1] -ne $Version) {
    throw "Installer version does not match archived SourceRef: $Version versus $($Matches[1])"
}
Write-Host "Archived source version verified: $Version"

# Keep the installed runtime portable across ordinary Windows user-profile
# paths. This is checked before compilation so path regressions fail cheaply
# and with the exact offending relative path.
$MaxRuntimeRelativePathChars = 190
$PathBudgetViolations = @(
    Get-ChildItem -LiteralPath $PayloadDir -File -Recurse | ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($PayloadDir, $_.FullName)
        if ($relative.Length -gt $MaxRuntimeRelativePathChars) {
            [PSCustomObject]@{
                Length = $relative.Length
                Path = $relative
            }
        }
    }
)
if ($PathBudgetViolations.Count -gt 0) {
    Write-Host "Windows runtime payload path budget exceeded:"
    $PathBudgetViolations |
        Sort-Object Length -Descending |
        Format-Table -AutoSize |
        Out-String |
        Write-Host
    throw "Runtime payload contains paths longer than $MaxRuntimeRelativePathChars characters"
}

Write-Host "==> Building standalone Skeleton.exe"
& python -m pip install --disable-pip-version-check --no-input "pyinstaller==6.22.3" "pydantic>=2.14.0,<3" "pydantic-settings>=2.15.0,<3"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller/runtime dependency installation failed"
}

$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "Skeleton",
    "--distpath", $LauncherDist,
    "--workpath", $LauncherWork,
    "--specpath", $LauncherSpec,
    "--paths", $PayloadDir,
    "--collect-data", "skeleton.app",
    "--hidden-import", "skeleton.app.health",
    "--hidden-import", "skeleton.app.installer",
    "--hidden-import", "skeleton.app.preloader",
    "--hidden-import", "skeleton.app.setup_runtime",
    "--hidden-import", "skeleton.app.local_ai",
    "--hidden-import", "skeleton.app.local_ai_acceptance",
    "--hidden-import", "skeleton.app.local_ai_benchmark",
    "--hidden-import", "skeleton.app.local_ai_dataset",
    "--hidden-import", "skeleton.app.local_ai_gguf",
    "--hidden-import", "skeleton.app.local_ai_improvement",
    "--hidden-import", "skeleton.app.local_ai_replay",
    "--hidden-import", "skeleton.app.local_ai_training",
    "--hidden-import", "skeleton.app.local_ai_transcript",
    "--hidden-import", "skeleton.app.offline_chat_cli",
    "--hidden-import", "skeleton.app.offline_cli",
    "--hidden-import", "skeleton.app.offline_qualification",
    "--hidden-import", "skeleton.app.offline_snapshot",
    "--hidden-import", "skeleton.app.offline_library",
    "--hidden-import", "skeleton.app.offline_workspace",
    "--hidden-import", "skeleton.app.offline_audit",
    "--hidden-import", "skeleton.app.offline_readiness",
    "--hidden-import", "skeleton.ai.training.jeeves_multidomain",
    "--hidden-import", "skeleton.ai.training.jeeves_parallel_mirrors",
    "--hidden-import", "skeleton.ai.training.jeeves_cinematic_simulation",
    "--hidden-import", "skeleton.app.offline_index_queue",
    "--hidden-import", "skeleton.app.offline_http",
    "--hidden-import", "skeleton.app.offline_knowledge",
    "--hidden-import", "skeleton.app.offline_grounding",
    "--hidden-import", "skeleton.app.offline_web",
    "--hidden-import", "skeleton.ai.runtime.inference.local",
    "--hidden-import", "skeleton.ai.runtime.inference.native_runtime",
    "--hidden-import", "skeleton.ai.runtime.inference.artifact",
    "--hidden-import", "skeleton.ai.runtime.inference.deployment",
    "--hidden-import", "skeleton.ai.runtime.inference.llama_cpp",
    "--hidden-import", "skeleton.ai.model_runtime.native_llm_runtime",
    "--hidden-import", "skeleton.ai.model_runtime.offline_chat",
    "--hidden-import", "skeleton.ai.model_runtime.chat_engine",
    "--hidden-import", "skeleton.ai.model_runtime.chat_protocol",
    "--hidden-import", "skeleton.ai.model_runtime.runtime_checkpoint",
    "--hidden-import", "skeleton.ai.model_runtime.tokenization",
    "--hidden-import", "skeleton.cortex.transformer",
    "--hidden-import", "tkinter",
    $EntryPoint
)
# Force both freezes to resolve first-party modules from the staged revision.
$PreviousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $PayloadDir
Push-Location -LiteralPath $PayloadDir
try {
& python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller launcher build failed"
}

$LauncherExe = Join-Path $LauncherDist "Skeleton.exe"
if (-not (Test-Path -LiteralPath $LauncherExe)) {
    throw "Expected launcher not found: $LauncherExe"
}
Copy-Item -LiteralPath $LauncherExe -Destination (Join-Path $PayloadDir "Skeleton.exe") -Force

# The windowed GUI is intentionally separate from the genuine console entry.
# Reuse the same pinned interpreter and source tree; no extra downloads.
$ConsoleArgs = @($PyInstallerArgs)
$WindowFlagIndex = [Array]::IndexOf($ConsoleArgs, "--windowed")
$ConsoleNameIndex = [Array]::IndexOf($ConsoleArgs, "Skeleton")
$ConsoleEntryIndex = [Array]::IndexOf($ConsoleArgs, $EntryPoint)
if ($WindowFlagIndex -lt 0 -or $ConsoleNameIndex -lt 0 -or $ConsoleEntryIndex -lt 0) {
    throw "Unable to derive canonical offline console build"
}
$ConsoleArgs[$WindowFlagIndex] = "--console"
$ConsoleArgs[$ConsoleNameIndex] = "SkeletonOffline"
$ConsoleArgs[$ConsoleEntryIndex] = $ConsoleEntryPoint
& python @ConsoleArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller offline console build failed"
}
$ConsoleExe = Join-Path $LauncherDist "SkeletonOffline.exe"
if (-not (Test-Path -LiteralPath $ConsoleExe)) {
    throw "Expected offline console not found: $ConsoleExe"
}
Copy-Item -LiteralPath $ConsoleExe -Destination (Join-Path $PayloadDir "SkeletonOffline.exe") -Force
} finally {
    Pop-Location
    $env:PYTHONPATH = $PreviousPythonPath
}


$CompilerCandidates = @(
    (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $CompilerCandidates) {
    throw "ISCC.exe not found. Install Inno Setup 7 (recommended) or Inno Setup 6."
}
$Iscc = $CompilerCandidates | Select-Object -First 1

Write-Host "==> Compiling Windows setup executable with $Iscc"
$InnoArgs = @(
    "/DAppVersion=$Version",
    "/DVersionInfoVersion=$VersionInfoVersion",
    "/DPayloadDir=$PayloadDir",
    "/DOutputDir=$OutputDir",
    $InstallerScript
)
& $Iscc @InnoArgs
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed"
}

$Installer = Get-ChildItem -LiteralPath $OutputDir -Filter "Skeleton-Setup-*-windows-x64.exe" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $Installer) {
    throw "Windows installer output was not produced"
}

$Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $Installer.FullName
$HashPath = "$($Installer.FullName).sha256"
"$($Hash.Hash.ToLowerInvariant())  $($Installer.Name)" | Set-Content -LiteralPath $HashPath -Encoding ascii

Write-Host ""
Write-Host "Windows installer built successfully:"
Write-Host "  $($Installer.FullName)"
Write-Host "  SHA256 $($Hash.Hash)"

} finally {
    # Failed compilation must never strand the virtual drive for subsequent runs.
    & subst $ShortDrive /D | Out-Null
}
