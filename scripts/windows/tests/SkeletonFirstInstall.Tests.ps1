#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
<#
    Pester 5 tests for SkeletonFirstInstall.psm1. Cross-platform cases run on any
    PowerShell 7 host; Windows-only cases (DPAPI, icacls) run on Windows.

        Invoke-Pester -Path scripts/windows/tests -Output Detailed
#>

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'SkeletonFirstInstall.psm1') -Force
    $script:OnWindows = Test-SkeletonIsWindows
}

Describe 'Get-SkeletonLayout' {
    It 'uses an explicit data root and derives every path from it' {
        $root = Join-Path $TestDrive 'data'
        $layout = Get-SkeletonLayout -DataRoot $root
        $layout.Root | Should -Be ([System.IO.Path]::GetFullPath($root))
        $layout.ConfigFile | Should -BeLike (Join-Path $layout.Config '*config.json')
        $layout.SecretsFile | Should -BeLike (Join-Path $layout.Config '*secrets.json')
        $layout.PidFile | Should -BeLike (Join-Path $layout.Run '*api.pid')
    }
    It 'honours SKELETON_HOME when no root is given' {
        $previous = $env:SKELETON_HOME
        try {
            $env:SKELETON_HOME = Join-Path $TestDrive 'from-env'
            (Get-SkeletonLayout).Root | Should -Be ([System.IO.Path]::GetFullPath($env:SKELETON_HOME))
        }
        finally { $env:SKELETON_HOME = $previous }
    }
}

Describe 'Initialize-SkeletonLayout' {
    It 'creates the folders and restricts config to the owner' {
        $layout = Get-SkeletonLayout -DataRoot (Join-Path $TestDrive 'init')
        Initialize-SkeletonLayout -Layout $layout
        foreach ($dir in $layout.Config, $layout.Tools, $layout.Logs, $layout.Games, $layout.Run) {
            Test-Path -LiteralPath $dir -PathType Container | Should -BeTrue
        }
        if ($script:OnWindows) {
            $rules = (Get-Acl -LiteralPath $layout.Config).Access
            ($rules | Where-Object { $_.IdentityReference -match 'Everyone|\\Users$' }) | Should -BeNullOrEmpty
            (Get-Acl -LiteralPath $layout.Config).AreAccessRulesProtected | Should -BeTrue
        }
        else {
            (& stat -c '%a' $layout.Config) | Should -Be '700'
        }
    }
}

Describe 'ConvertTo-SkeletonConstraintFile' {
    It 'keeps exact pins, strips extras, comments and options' {
        $req = Join-Path $TestDrive 'req.txt'
        @(
            '# comment', '', '-r other.txt', '-e .', 'fastapi==0.162.0',
            'uvicorn[standard]==0.54.0   # inline', 'loose>=1.0', 'pywin32==311; sys_platform == "win32"'
        ) | Set-Content -LiteralPath $req
        $out = Join-Path $TestDrive 'c.txt'
        $count = ConvertTo-SkeletonConstraintFile -Requirements $req -Destination $out
        $count | Should -Be 3
        $lines = Get-Content -LiteralPath $out
        $lines | Should -Contain 'fastapi==0.162.0'
        $lines | Should -Contain 'uvicorn==0.54.0'
        $lines | Should -Contain 'pywin32==311; sys_platform == "win32"'
        ($lines -join "`n") | Should -Not -Match '\[|loose|^-'
    }
    It 'produces constraints pip accepts for the real backend pins' {
        $repo = Resolve-Path (Join-Path $PSScriptRoot '..' '..' '..')
        $out = Join-Path $TestDrive 'backend-constraints.txt'
        $count = ConvertTo-SkeletonConstraintFile -Requirements (Join-Path $repo 'backend' 'requirements.txt') -Destination $out
        $count | Should -BeGreaterThan 20
        (Get-Content -LiteralPath $out) | ForEach-Object { $_ | Should -Not -Match '\[' }
    }
}

Describe 'Secret protection' {
    It 'round-trips a secret without storing the plain value' {
        $plain = 'sk-test-' + (New-SkeletonRandomSecret -Bytes 8)
        $stored = Protect-SkeletonSecretText -Plain $plain
        $stored | Should -Not -BeLike "*$plain*"
        if ($script:OnWindows) { $stored | Should -BeLike 'dpapi:*' } else { $stored | Should -BeLike 'plain0600:*' }
        Unprotect-SkeletonSecretText -Stored $stored | Should -Be $plain
    }
    It 'rejects unknown encodings' {
        { Unprotect-SkeletonSecretText -Stored 'rot13:abc' } | Should -Throw '*Unknown secret encoding*'
    }
    It 'generates 256-bit hex secrets that differ' {
        $a = New-SkeletonRandomSecret
        $b = New-SkeletonRandomSecret
        $a | Should -Match '^[0-9a-f]{64}$'
        $a | Should -Not -Be $b
    }
}

Describe 'Set-SkeletonConfig' {
    BeforeEach {
        $script:layout = Get-SkeletonLayout -DataRoot (Join-Path $TestDrive ([guid]::NewGuid().ToString('n')))
        Initialize-SkeletonLayout -Layout $script:layout
    }
    It 'writes non-secret config and a protected seal secret' {
        $config = Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive -Provider none -Port 8799
        $config.provider | Should -Be 'none'
        $config.port | Should -Be 8799
        $raw = Get-Content -LiteralPath $script:layout.ConfigFile -Raw
        $raw | Should -Not -Match 'GF_SEAL_SECRET'
        $secrets = Read-SkeletonSecretStore -Layout $script:layout
        $secrets['GF_SEAL_SECRET'] | Should -Match '^[0-9a-f]{64}$'
        (Get-Content -LiteralPath $script:layout.SecretsFile -Raw) | Should -Not -Match $secrets['GF_SEAL_SECRET']
    }
    It 'keeps the seal secret across re-runs unless rotated' {
        Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive | Out-Null
        $first = (Read-SkeletonSecretStore -Layout $script:layout)['GF_SEAL_SECRET']
        Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive | Out-Null
        (Read-SkeletonSecretStore -Layout $script:layout)['GF_SEAL_SECRET'] | Should -Be $first
        Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive -RotateSeal | Out-Null
        (Read-SkeletonSecretStore -Layout $script:layout)['GF_SEAL_SECRET'] | Should -Not -Be $first
    }
    It 'requires a key for openai and drops it when switching back to none' {
        { Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive -Provider openai } | Should -Throw '*API key*'
        $key = ConvertTo-SecureString 'sk-unit-test-key' -AsPlainText -Force
        Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive -Provider openai -Model 'gpt-5.5' -ApiKey $key | Out-Null
        (Get-Content -LiteralPath $script:layout.SecretsFile -Raw) | Should -Not -Match 'sk-unit-test-key'
        $envMap = Get-SkeletonChildEnvironment -Layout $script:layout
        $envMap['AI_PROVIDER'] | Should -Be 'openai'
        $envMap['OPENAI_API_KEY'] | Should -Be 'sk-unit-test-key'
        $envMap['AI_MODEL'] | Should -Be 'gpt-5.5'
        Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive -Provider none | Out-Null
        (Read-SkeletonSecretStore -Layout $script:layout).ContainsKey('OPENAI_API_KEY') | Should -BeFalse
        (Get-SkeletonChildEnvironment -Layout $script:layout).Contains('AI_PROVIDER') | Should -BeFalse
    }
    It 'rejects insecure base URLs and privileged ports' {
        { Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive -OpenAIBaseUrl 'http://example.test' } | Should -Throw '*https*'
        { Set-SkeletonConfig -Layout $script:layout -RepoRoot $TestDrive -Port 80 } | Should -Throw '*Port*'
    }
    It 'refuses to store unknown secret names' {
        { Write-SkeletonSecretStore -Layout $script:layout -Values @{ AWS_SECRET = 'x' } } | Should -Throw '*unknown secret*'
    }
}

Describe 'Invoke-SkeletonWithEnvironment' {
    It 'sets variables only for the block and restores them' {
        $env:SKELETON_PESTER_PROBE = 'before'
        $seen = Invoke-SkeletonWithEnvironment -Environment @{ SKELETON_PESTER_PROBE = 'inside'; SKELETON_PESTER_NEW = '1' } -Script {
            "$env:SKELETON_PESTER_PROBE|$env:SKELETON_PESTER_NEW"
        }
        $seen | Should -Be 'inside|1'
        $env:SKELETON_PESTER_PROBE | Should -Be 'before'
        $env:SKELETON_PESTER_NEW | Should -BeNullOrEmpty
        Remove-Item Env:SKELETON_PESTER_PROBE
    }
}

Describe 'Find-SkeletonPython' {
    It 'finds an interpreter of at least 3.11 or returns null' {
        $found = Find-SkeletonPython
        if ($found) { $found.Version | Should -BeGreaterOrEqual ([version]'3.11') }
    }
    It 'rejects a path that is not Python' {
        Get-SkeletonPythonVersion -Exe (Join-Path $TestDrive 'nope.exe') | Should -BeNullOrEmpty
    }
}

Describe 'Install-SkeletonGodot' {
    It 'refuses an archive whose SHA-512 does not match the pin' {
        $layout = Get-SkeletonLayout -DataRoot (Join-Path $TestDrive 'godot')
        Initialize-SkeletonLayout -Layout $layout
        $fake = Join-Path $TestDrive 'fake-godot.zip'
        Set-Content -LiteralPath $fake -Value 'not godot'
        { Install-SkeletonGodot -Layout $layout -ArchivePath $fake } | Should -Throw '*SHA-512 mismatch*'
        Get-ChildItem -LiteralPath $layout.Tools -Directory | Should -BeNullOrEmpty
    }
}

Describe 'Test-SkeletonHost' {
    It 'reports platform, PowerShell and disk checks' {
        $layout = Get-SkeletonLayout -DataRoot (Join-Path $TestDrive 'host')
        $checks = Test-SkeletonHost -Layout $layout
        ($checks | ForEach-Object Id) | Should -Contain 'platform'
        ($checks | ForEach-Object Id) | Should -Contain 'powershell'
        ($checks | ForEach-Object Id) | Should -Contain 'disk'
        ($checks | Where-Object Id -eq 'powershell').Ok | Should -BeTrue
    }
}

Describe 'API process tracking' {
    It 'ignores a stale or foreign pid file' {
        $layout = Get-SkeletonLayout -DataRoot (Join-Path $TestDrive 'pid')
        Initialize-SkeletonLayout -Layout $layout
        Set-Content -LiteralPath $layout.PidFile -Value $PID
        Get-SkeletonApiProcess -Layout $layout | Should -BeNullOrEmpty   # this pwsh is not python
        Set-Content -LiteralPath $layout.PidFile -Value 'garbage'
        Get-SkeletonApiProcess -Layout $layout | Should -BeNullOrEmpty
        Stop-SkeletonApi -Layout $layout | Should -BeFalse
        Test-Path -LiteralPath $layout.PidFile | Should -BeFalse
    }
}
