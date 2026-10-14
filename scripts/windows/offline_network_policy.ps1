<#
.SYNOPSIS
    Operator-controlled outbound firewall blocking for a local Skeleton
    offline executable and an optional llama.cpp runtime.

.DESCRIPTION
    This script never executes automatically during installation. Apply and
    Remove require administrator rights; Status requires read access.
    Rules target exact executable paths and never alter global firewall
    policy. This is not a device airgap or protection for unrelated programs.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Apply", "Status", "Remove")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$OfflineExe,

    [string]$LlamaCli = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Windows Defender Firewall controls require Windows."
}

function Resolve-Program([string]$Candidate, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        throw "$Label requires an executable."
    }
    if (-not [IO.Path]::IsPathRooted($Candidate)) {
        throw "$Label requires an absolute path."
    }
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        throw "$Label executable is missing."
    }
    $Resolved = (Resolve-Path -LiteralPath $Candidate).Path
    if (-not $Resolved.EndsWith(".exe", [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must be a Windows executable."
    }
    return [IO.Path]::GetFullPath($Resolved)
}

function Rule-Name([string]$Program) {
    $Bytes = [Text.Encoding]::UTF8.GetBytes($Program.ToLowerInvariant())
    $Hash = [Security.Cryptography.SHA256]::HashData($Bytes)
    $Hex = [Convert]::ToHexString($Hash).ToLowerInvariant()
    return "SkeletonOffline-OutboundBlock-" + $Hex.Substring(0, 24)
}

function Require-Administrator() {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Apply and Remove require an elevated PowerShell process."
    }
}

function Assert-RulePath($Rule, [string]$Program) {
    $Filter = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $Rule -ErrorAction Stop
    if ($null -eq $Filter -or $Filter.Program -ine $Program) {
        throw "Firewall rule path is not the selected executable."
    }
}

$Selected = [ordered]@{}
$Selected["offline"] = Resolve-Program $OfflineExe "Skeleton Offline"
if (-not [string]::IsNullOrWhiteSpace($LlamaCli)) {
    $Selected["llama"] = Resolve-Program $LlamaCli "Local llama.cpp"
}
if ($Mode -ne "Status") {
    Require-Administrator
}

$Results = @()
foreach ($Key in $Selected.Keys) {
    $Program = $Selected[$Key]
    $Name = Rule-Name $Program
    $Current = Get-NetFirewallRule -Name $Name -ErrorAction SilentlyContinue

    if ($Mode -eq "Apply") {
        if ($null -eq $Current) {
            $RuleArgs = @{
                Name = $Name
                DisplayName = "Skeleton Offline outbound block ($Key)"
                Description = "Operator-authorized local outbound block."
                Program = $Program
                Direction = "Outbound"
                Action = "Block"
                Profile = "Any"
                Enabled = "True"
                ErrorAction = "Stop"
            }
            $Current = New-NetFirewallRule @RuleArgs
        }
        Assert-RulePath $Current $Program
    }
    elseif ($Mode -eq "Remove") {
        if ($null -ne $Current) {
            Assert-RulePath $Current $Program
            Remove-NetFirewallRule -Name $Name -ErrorAction Stop
            $Current = $null
        }
    }
    elseif ($null -ne $Current) {
        Assert-RulePath $Current $Program
    }

    $Effective = $false
    if ($null -ne $Current) {
        $Effective = (
            $Current.Direction -eq "Outbound" -and
            $Current.Action -eq "Block" -and
            $Current.Enabled -eq "True"
        )
        if ($Mode -eq "Apply" -and -not $Effective) {
            throw "Existing firewall rule does not enforce outbound blocking."
        }
    }
    $Results += [PSCustomObject]@{
        schema_version = "skeleton.offline_firewall.v1"
        mode = $Mode
        target = $Key
        executable = $Program
        rule_name = $Name
        outbound_block_rule_present = [bool]$Effective
        host_isolation_proven = $false
    }
}

$Results | ConvertTo-Json -Depth 3
if ($Mode -eq "Status" -and @($Results | Where-Object { -not $_.outbound_block_rule_present }).Count -gt 0) {
    exit 1
}
exit 0
