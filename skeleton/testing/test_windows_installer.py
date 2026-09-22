from __future__ import annotations

from pathlib import Path
import subprocess

from skeleton.app.installer import install_application
from skeleton.app.preloader import PreloadCheck, PreloadReport, inspect_host
from skeleton.app.setup_runtime import SetupResult


def test_bundled_preloader_does_not_probe_system_pip(monkeypatch, tmp_path):
    monkeypatch.setattr("skeleton.app.preloader.preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr("skeleton.app.preloader.checks_ok", lambda checks: True)
    monkeypatch.setattr("skeleton.app.preloader.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "skeleton.app.preloader.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 20 * 1024**3})(),
    )

    calls = []

    def runner(command, **kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    report = inspect_host(
        tmp_path,
        runner=runner,
        require_python=False,
        require_pip=False,
    )

    pip_check = next(check for check in report.checks if check.code == "host:pip")
    assert pip_check.ok is True
    assert pip_check.required is False
    assert "bundled application runtime" in pip_check.detail
    assert not any("-m" in call and "pip" in call for call in calls)


def test_bundled_installer_disables_external_python_requirements(monkeypatch, tmp_path):
    captured = {}

    def fake_preload(root, **kwargs):
        captured.update(kwargs)
        return PreloadReport(
            root=Path(root),
            platform="Windows AMD64",
            python="3.14",
            checks=(PreloadCheck("host:ready", True, "ready"),),
        )

    monkeypatch.setattr("skeleton.app.installer.inspect_host", fake_preload)
    monkeypatch.setattr(
        "skeleton.app.installer.ensure_runtime_environment",
        lambda root, rotate_secrets=False: SetupResult(
            env_path=Path(root) / ".env",
            created=False,
            changed=False,
            configured_keys=(),
            preserved_keys=(),
            warnings=(),
        ),
    )
    monkeypatch.setattr("skeleton.app.installer.preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr("skeleton.app.installer.checks_ok", lambda checks: True)
    monkeypatch.setattr(
        "skeleton.app.installer.compose_command",
        lambda action, **kwargs: ("docker", "compose", "config"),
    )

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="valid", stderr="")

    receipt = install_application(
        tmp_path,
        install_python=False,
        bundled_runtime=True,
        runner=runner,
    )

    assert receipt.ok is True
    assert captured["require_python"] is False
    assert captured["require_pip"] is False
    python_phase = next(phase for phase in receipt.phases if phase.name == "python-install")
    assert python_phase.required is False
    assert "bundled runtime" in python_phase.detail


def test_inno_setup_contract_is_per_user_and_uninstallable():
    source = Path("packaging/windows/SkeletonSetup.iss").read_text(encoding="utf-8")

    assert "DefaultDirName={localappdata}\\Programs\\Skeleton" in source
    assert "PrivilegesRequired=lowest" in source
    assert "ArchitecturesAllowed=x64compatible" in source
    assert "Uninstallable=yes" in source
    assert 'Filename: "{app}\\{#AppExeName}"' in source
    assert 'Parameters: "--stop --quiet"' in source
    assert 'Type: files; Name: "{app}\\.env"' in source
    assert "{userdesktop}\\Skeleton" in source
    assert "{commondesktop}" not in source


def test_windows_launcher_is_bundled_runtime_control_surface():
    source = Path("skeleton/app/windows_launcher.py").read_text(encoding="utf-8")

    assert "bundled_runtime=True" in source
    assert 'install_python=False' in source
    assert 'APP_URL = "http://localhost:3000"' in source
    assert "production: bool = True" in source
    assert 'compose_command("down"' in source
    assert "shell=True" not in source
    assert "shell=False" in source
    assert "CREATE_NO_WINDOW" in source


def test_windows_build_is_pinned_and_hashes_installer():
    source = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")

    assert '"pyinstaller==6.22.3"' in source
    assert "$RuntimePaths = @(" in source
    assert '"backend"' in source
    assert '"frontend"' in source
    assert '"skeleton"' in source
    assert '":(exclude)backend/gameforge/jeeves/jeeves_mastermap_*.json"' in source
    assert "$MaxRuntimeRelativePathChars = 190" in source
    assert "$PathBudgetViolations" in source
    assert "& git @ArchiveArgs" in source
    assert "Get-FileHash -Algorithm SHA256" in source
    assert "Skeleton-Setup-*-windows-x64.exe" in source
    assert "ISCC.exe" in source



def test_windows_runtime_payload_respects_portable_path_budget():
    # The installer payload is created by git archive, so validate exactly the
    # tracked files that can enter that archive. CI creates frontend/node_modules
    # before this test runs; walking the workspace would incorrectly treat those
    # transient dependencies as installer payload.
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--",
            "backend",
            "frontend",
            "skeleton",
            "scripts",
            "packaging",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_paths = [line.strip().replace("\\", "/") for line in completed.stdout.splitlines()]
    violations: list[tuple[int, str]] = []

    for relative in tracked_paths:
        if not relative:
            continue
        if (
            relative.startswith("backend/gameforge/jeeves/jeeves_mastermap_")
            and relative.endswith(".json")
        ):
            continue
        if len(relative) > 190:
            violations.append((len(relative), relative))

    assert violations == [], (
        "Windows runtime payload exceeds the 190-character relative path budget: "
        + ", ".join(f"{length}:{path}" for length, path in sorted(violations, reverse=True))
    )

def test_windows_workflow_builds_and_uploads_setup_exe():
    source = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")

    assert "runs-on: windows-latest" in source
    assert 'PYTHON_VERSION: "3.14.7"' in source
    assert "JRSoftware.InnoSetup.7" in source
    assert "--version 7.1.0" in source
    assert "core.longpaths true" in source
    assert "sparse-checkout-cone-mode: false" in source
    assert "scripts/windows/build_installer.ps1" in source
    assert "Smoke install generated Setup.exe" in source
    assert '"/VERYSILENT"' in source
    assert 'Start-Process -FilePath $launcher -ArgumentList @("--help") -Wait -PassThru' in source
    assert "$launch.ExitCode" in source
    assert '"unins000.exe"' in source
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in source
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in source
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in source
    assert "dist/windows/Skeleton-Setup-*-windows-x64.exe" in source
