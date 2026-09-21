param(
    [string]$Version = "",
    [string]$SourceRef = "HEAD"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PyProjectPath = Join-Path $RepoRoot "pyproject.toml"
$BuildRoot = Join-Path $RepoRoot ".build\windows-installer"
$PayloadDir = Join-Path $BuildRoot "payload"
$LauncherDist = Join-Path $BuildRoot "launcher-dist"
$LauncherWork = Join-Path $BuildRoot "launcher-work"
$LauncherSpec = Join-Path $BuildRoot "launcher-spec"
$OutputDir = Join-Path $RepoRoot "dist\windows"
$ArchivePath = Join-Path $BuildRoot "source.zip"
$EntryPoint = Join-Path $RepoRoot "packaging\windows\launcher_entry.py"
$InstallerScript = Join-Path $RepoRoot "packaging\windows\SkeletonSetup.iss"

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
New-Item -ItemType Directory -Force -Path $BuildRoot, $PayloadDir, $LauncherDist, $LauncherWork, $LauncherSpec, $OutputDir | Out-Null

Write-Host "==> Staging curated application payload from $SourceRef"
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
    "packaging"
)
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

Write-Host "==> Building standalone Skeleton.exe"
& python -m pip install --disable-pip-version-check --no-input "pyinstaller==6.22.3" "pydantic==2.13.5" "pydantic-settings==2.15.0"
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
    "--paths", $RepoRoot,
    "--collect-data", "skeleton.app",
    "--hidden-import", "skeleton.app.health",
    "--hidden-import", "skeleton.app.installer",
    "--hidden-import", "skeleton.app.preloader",
    "--hidden-import", "skeleton.app.setup_runtime",
    "--hidden-import", "tkinter",
    $EntryPoint
)
& python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller launcher build failed"
}

$LauncherExe = Join-Path $LauncherDist "Skeleton.exe"
if (-not (Test-Path -LiteralPath $LauncherExe)) {
    throw "Expected launcher not found: $LauncherExe"
}
Copy-Item -LiteralPath $LauncherExe -Destination (Join-Path $PayloadDir "Skeleton.exe") -Force

$CompilerCandidates = @(
    (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $CompilerCandidates) {
    throw "ISCC.exe not found. Install Inno Setup 7 (recommended) or Inno Setup 6."
}
$Iscc = $CompilerCandidates[0]

Write-Host "==> Compiling Windows setup executable with $Iscc"
$InnoArgs = @(
    "/DAppVersion=$Version",
    "/DVersionInfoVersion=$VersionInfoVersion",
    "/DPayloadDir=`"$PayloadDir`"",
    "/DOutputDir=`"$OutputDir`"",
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
