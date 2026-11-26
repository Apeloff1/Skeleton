param(
  [Parameter(Mandatory=$true)][string]$EngineRoot,
  [Parameter(Mandatory=$true)][string]$Project,
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$Assets,
  [Parameter(Mandatory=$true)][string]$EvidenceDir,
  [int]$TimeoutSeconds=1800,
  [switch]$RequirePhysicalRTX
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($TimeoutSeconds -lt 60 -or $TimeoutSeconds -gt 7200){throw 'Bound timeout required (60-7200 seconds)'}
$Project=(Resolve-Path $Project).Path
$RepoRoot=(Resolve-Path $RepoRoot).Path
$Assets=(Resolve-Path $Assets).Path
if(-not (Test-Path -LiteralPath $EvidenceDir)){New-Item -ItemType Directory -Path $EvidenceDir -Force|Out-Null}
$EvidenceDir=(Resolve-Path $EvidenceDir).Path
if(-not ($Project.EndsWith('.uproject'))){throw 'Explicit .uproject required'}
$Editor=Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$Builder=Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat'
if(-not(Test-Path $Editor) -or -not(Test-Path $Builder)){throw 'Real installed Unreal Editor and native toolchain required'}
$RunId=[guid]::NewGuid().ToString('N').ToLowerInvariant()
$Pin=Get-Content (Join-Path $RepoRoot 'frontend\src\features\Jeeves\companion\atelier\evolutionPin.json') -Raw | ConvertFrom-Json
$Manifest=Get-Content (Join-Path $RepoRoot 'assets\emerald\evolution-v4\publication-manifest.json') -Raw | ConvertFrom-Json
if($Pin.donorSha256 -ne $Manifest.donor_sha256 -or @($Manifest.forms).Count -ne 5){throw 'Exact V4 manifest mismatch'}
foreach($Row in $Manifest.forms) {
  $Name=$Row.stage
  if($Name -notin @('hatchling','scout','scholar','pathfinder','archivist')){throw 'Unsupported stage'}
  $Input=Join-Path $Assets ($Name+'.glb')
  if(-not(Test-Path -LiteralPath $Input -PathType Leaf)){throw "Missing model $Name"}
  $Actual=(Get-FileHash -LiteralPath $Input -Algorithm SHA256).Hash.ToLowerInvariant()
  if($Actual -ne $Row.sha256 -or (Get-Item -LiteralPath $Input).Length -ne $Row.bytes){throw "Model pin mismatch $Name"}
  if($Pin.forms.$Name.sha256 -ne $Actual -or $Pin.forms.$Name.equipmentEnabled -ne $false){throw "Equipment or adoption pin mismatch $Name"}
}
$Receipt=Join-Path $EvidenceDir ('qualification_'+$RunId+'.json')
if(Test-Path -LiteralPath $Receipt){throw 'Cannot overwrite qualification run'}
$State=[ordered]@{
  schema='skeleton.emerald.unreal-v4.operator.v1';run_id=$RunId
  exact_assets_checked=$true;source_sha256=$Manifest.donor_sha256
  engine_compiled=$false;editor_import_passed=$false
  physical_rtx_verified=$false;artist_approved=$false
  continuous_collision_verified=$false;release_qualified=$false
}
function Invoke-Checked([string]$Program,[string[]]$Arguments) {
  $p=Start-Process -FilePath $Program -ArgumentList $Arguments -NoNewWindow -PassThru -Wait:$false
  if(-not $p.WaitForExit($TimeoutSeconds*1000)){
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    throw "Timed out executing $Program"
  }
  if($p.ExitCode -ne 0){throw "Process failed with exit $($p.ExitCode): $Program"}
}
try {
  $env:EMERALD_V4_RUN_ID=$RunId
  $env:EMERALD_V4_REPO=$RepoRoot
  $env:EMERALD_V4_ASSETS=$Assets
  $ProjectName=[IO.Path]::GetFileNameWithoutExtension($Project)
  Invoke-Checked $Builder @(($ProjectName+'Editor'),'Win64','Development',('-Project="'+$Project+'"'),'-WaitMutex')
  Invoke-Checked $Builder @($ProjectName,'Win64','Development',('-Project="'+$Project+'"'),'-WaitMutex')
  $State.engine_compiled=$true
  $Python=Join-Path $RepoRoot 'scripts\emerald_v4_unreal_import.py'
  Invoke-Checked $Editor @('"'+$Project+'"','-run=pythonscript',('-script="'+$Python+'"'),'-unattended','-nop4','-nosplash','-stdout','-NullRHI')
  $ActualReceipt=Join-Path (Split-Path $Project) ('Saved\Emerald\v4_import_'+$RunId+'.json')
  if(-not(Test-Path $ActualReceipt)){throw 'Native Unreal importer did not produce exact-run receipt'}
  $Import=Get-Content $ActualReceipt -Raw | ConvertFrom-Json
  if($Import.run_id -ne $RunId -or $Import.models.Count -ne 5 -or !$Import.engine_editor_imported){throw 'Editor import failed'}
  foreach($Row in $Manifest.forms) {
    $Match=@($Import.models|Where-Object { $_.stage -eq $Row.stage -and $_.source_sha256 -eq $Row.sha256 -and $_.animation_count -eq 381 })
    if($Match.Count -ne 1){throw "Missing exact imported model receipt: $($Row.stage)"}
  }
  $State.editor_import_passed=$true
  $State.engine_version=$Import.engine_version
  $State.import_receipt_sha256=(Get-FileHash -LiteralPath $ActualReceipt -Algorithm SHA256).Hash.ToLowerInvariant()
  if($RequirePhysicalRTX) {
    # No automatic hardware signoff: an imported model and reported GPU alone do
    # not prove physical ray dispatch, real time performance, driver or device qualification.
    $State.hardware_followup_required=$true
    throw 'Physical RTX requires an independently captured D3D12 render/trace and human review, not a NullRHI import.'
  }
} catch {
  $State.error=$_.Exception.Message
  throw
} finally {
  $State|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $Receipt -Encoding utf8
  Remove-Item Env:EMERALD_V4_RUN_ID,Env:EMERALD_V4_REPO,Env:EMERALD_V4_ASSETS -ErrorAction SilentlyContinue
}
Write-Output ("Exact-run Unreal import receipt: "+$Receipt+". RTX and artistic acceptance still held.")
