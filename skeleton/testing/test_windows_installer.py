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
            (
                relative.startswith("backend/gameforge/jeeves/jeeves_mastermap_")
                or relative.startswith("skeleton/ai/research/legacy/gameforge/jeeves/jeeves_mastermap_")
            )
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
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source
    assert "dist/windows/Skeleton-Setup-*-windows-x64.exe" in source


def test_frozen_offline_console_is_packaged_and_smoke_tested():
    build = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    installer = Path("packaging/windows/SkeletonSetup.iss").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "packaging\\windows\\offline_cli_entry.py" in build
    assert '"--console"' in build
    assert '"SkeletonOffline"' in build
    assert "SkeletonOffline.exe" in build
    assert "SkeletonOffline.exe" in workflow
    assert "& $offline --native-smoke" in workflow
    assert "SkeletonOffline.exe" in installer
    assert 'skeleton-offline = "skeleton.app.offline_cli:main"' in pyproject


def test_installed_frozen_console_qualifies_two_local_inference_turns() -> None:
    workflow = Path(".github/workflows/windows-installer.yml").read_text("utf-8")
    build = Path("scripts/windows/build_installer.ps1").read_text("utf-8")
    fixture = Path("scripts/windows/create_offline_native_fixture.py").read_text("utf-8")
    source = Path("skeleton/app/offline_qualification.py").read_text("utf-8")

    assert "scripts/windows/create_offline_native_fixture.py" in workflow
    assert "& $offline --model $nativeFixture --qualify-model" in workflow
    assert "sqlite_context_restored_and_verified" in workflow
    assert "artifacts_verified_before_and_after" in workflow
    assert "network_isolation_verified" in workflow
    assert "trained_model_quality_verified" in workflow
    assert '"skeleton.app.offline_qualification"' in build
    assert "write_local_model_artifact" in fixture
    assert "TinyTransformer" in fixture
    assert "DurableOfflineSession" in source
    assert "TemporaryDirectory" in source
    assert '"trained_model_quality_verified": False' in source


def test_installed_offline_capability_engine_is_bundled_and_actually_exercised():
    workflow = Path(".github/workflows/windows-installer.yml").read_text("utf-8")
    build = Path("scripts/windows/build_installer.ps1").read_text("utf-8")
    cli = Path("skeleton/app/offline_cli.py").read_text("utf-8")

    assert '"skeleton.ai.runtime.deterministic_capabilities"' in build
    assert "& $offline --capability-list --json" in workflow
    assert "$capabilityCatalog.operations.Count -ne 30" in workflow
    assert "& $offline --capability-file $capabilityTask --json" in workflow
    assert '$capabilityReport.result.steps -ne 5' in workflow
    assert "$capabilityReport.model_inference_used" in workflow
    assert "$capabilityReport.network_access_used" in workflow
    assert "duplicate JSON" in workflow
    assert '"skeleton/ai/runtime/deterministic_capabilities.py"' in workflow
    assert '"skeleton/ai/runtime/capability_graph.py"' in workflow
    assert "& $offline --capability-graph-file $capabilityGraphTask --json" in workflow
    assert "$graphReport.outputs.score -ne 28" in workflow
    assert "self-referencing task" in workflow
    assert "args.capability_file" in cli
    assert "execute_capability_json" in cli
    assert "stat.S_ISREG" in cli


def test_installer_contains_dedicated_one_click_offline_game_executable():
    """Real native .exe, not a browser page or a console-only simulation."""
    build = Path("scripts/windows/build_installer.ps1").read_text("utf-8")
    inno = Path("packaging/windows/SkeletonSetup.iss").read_text("utf-8")
    entry = Path("packaging/windows/game_preview_entry.py").read_text("utf-8")
    workflow = Path(".github/workflows/windows-installer.yml").read_text("utf-8")

    assert "$GamePreviewEntryPoint" in build
    assert 'game_preview_entry.py' in build
    assert '"--name", "SkeletonGame"' in build
    assert '"--windowed"' in build
    assert '"skeleton.app.offline_game_preview"' in build
    assert '"skeleton.ai.runtime.gameplay_capabilities"' in build
    assert 'Join-Path $LauncherDist "SkeletonGame.exe"' in build
    assert 'Join-Path $PayloadDir "SkeletonGame.exe"' in build
    assert 'Filename: "{app}\\SkeletonGame.exe"' in inno
    assert "Skeleton Game Preview" in inno
    assert "from skeleton.app.offline_game_preview import run_game_preview" in entry
    assert "return run_game_preview()" in entry
    assert "installed SkeletonGame.exe native game is missing" in workflow
    assert "installed native SkeletonGame.exe looks truncated" in workflow
    assert "& $offline --game-preview-check --game-seed 1729 --json" in workflow
    assert "$headlessGame.terminal_won" in workflow
    assert "$headlessGame.replay_deterministic" in workflow
    assert "$headlessGameRepeat.replay_sha256" in workflow
    assert "$headlessGame.installed_tk_display_verified" in workflow
