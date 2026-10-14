"""Static safety contracts for opt-in Windows executable firewall control."""
from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/windows/offline_network_policy.ps1")


def test_offline_firewall_is_never_automatic_or_host_wide() -> None:
    data = SCRIPT.read_text(encoding="utf-8")
    assert '[ValidateSet("Apply", "Status", "Remove")]' in data
    assert '[Parameter(Mandatory = $true)]' in data
    assert 'function Require-Administrator()' in data
    assert 'if ($Mode -ne "Status")' in data
    assert 'Require-Administrator' in data
    assert 'Get-NetFirewallApplicationFilter' in data
    assert 'Assert-RulePath $Current $Program' in data
    assert 'New-NetFirewallRule @RuleArgs' in data
    assert 'Remove-NetFirewallRule -Name $Name' in data
    assert 'Program = $Program' in data
    assert 'Direction = "Outbound"' in data
    assert 'Action = "Block"' in data
    assert 'host_isolation_proven = $false' in data
    assert "Set-NetFirewallProfile" not in data
    assert "Disable-NetFirewallRule" not in data
    assert "Remove-NetFirewallRule -DisplayName" not in data
    assert "Invoke-Expression" not in data
    assert "Start-Process" not in data


def test_rule_identity_is_path_scoped_and_status_read_only() -> None:
    data = SCRIPT.read_text(encoding="utf-8")
    assert "GetBytes($Program.ToLowerInvariant())" in data
    assert "SHA256" in data
    assert "Get-NetFirewallRule -Name $Name" in data
    assert 'if ($Mode -eq "Apply")' in data
    assert 'elseif ($Mode -eq "Remove")' in data
    assert 'elseif ($null -ne $Current)' in data
    assert 'exit 1' in data
