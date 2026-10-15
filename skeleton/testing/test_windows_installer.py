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
    # Uninstall retains database volumes: credentials must survive for reinstall.
    assert 'Type: files; Name: "{app}\\.env"' not in source
    assert "User-generated .env intentionally remains" in source
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
    assert '"pydantic>=2.14.0,<3"' in source
    assert '"pydantic-settings>=2.15.0,<3"' in source
    assert 'Join-Path $PayloadDir "packaging\\windows\\launcher_entry.py"' in source
    assert 'Join-Path $PayloadDir "packaging\\windows\\offline_cli_entry.py"' in source
    assert 'Join-Path $PayloadDir "packaging\\windows\\SkeletonSetup.iss"' in source
    assert '"--paths", $PayloadDir' in source
    assert "Push-Location -LiteralPath $PayloadDir" in source
    assert "Pop-Location" in source
    assert '$env:PYTHONPATH = $PayloadDir' in source
    assert '$env:PYTHONPATH = $PreviousPythonPath' in source
    assert '"machine/manifest.json"' in source
    assert "Installer version does not match archived SourceRef" in source
    assert "& subst $ShortDrive /D | Out-Null" in source
    assert '"--paths", $RepoRoot' not in source
    assert "$RuntimePaths = @(" in source
    assert '"backend"' in source
    assert '"frontend"' in source
    assert '"skeleton"' in source
    assert '"machine"' in source
    assert '":(exclude)backend/gameforge/jeeves/jeeves_mastermap_*.json"' in source
    assert "$MaxRuntimeRelativePathChars = 190" in source
    assert "$PathBudgetViolations" in source
    assert "& git @ArchiveArgs" in source
    assert 'git -C $RepoRoot show "$($SourceRef):skeleton/app/manifest.json"' in source
    assert '$RuntimePaths = @($RuntimePaths | Select-Object -Unique)' in source
    assert 'Windows payload missing required assembly path' in source
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
            "machine",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_paths = [line.strip().replace("\\", "/") for line in completed.stdout.splitlines()]
    # Assembly-required paths are archived even when outside the primary
    # runtime roots. The same portability budget applies to those files.
    import json

    required = json.loads(
        Path("skeleton/app/manifest.json").read_text(encoding="utf-8")
    )["required_paths"]
    tracked_paths.extend(required)
    tracked_paths.append("machine/manifest.json")
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
    assert 'PYTHON_VERSION: "3.11"' in source
    assert '"pydantic>=2.14.0,<3"' in source
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
    assert "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9" in source
    assert "dist/windows/Skeleton-Setup-*-windows-x64.exe" in source

def test_windows_installer_packages_jeeves_curriculum_and_mirror_routes():
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    launcher = Path("skeleton/app/windows_launcher.py").read_text(encoding="utf-8")
    builder = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    assert "/machine/jeeves_training_modules.json" in workflow
    assert "test_jeeves_multidomain.py" in workflow
    assert 'ArgumentList @("--training-modules")' in workflow
    assert '"Jeeves Training Modules", self.inspect_jeeves_modules' in launcher
    assert "No model weights were trained or promoted by this check." in launcher
    assert '"skeleton.ai.training.jeeves_parallel_mirrors"' in builder
    assert '"skeleton.ai.training.jeeves_multidomain"' in builder

def test_windows_bundle_includes_cutscene_multi_sim_and_review_runtime():
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    launcher = Path("skeleton/app/windows_launcher.py").read_text(encoding="utf-8")
    builder = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    assert "test_jeeves_cinematic_simulation.py" in workflow
    assert '"--cinematic-sim", "--help"' in workflow
    assert '"Cutscene Multi-Sim", self.run_cutscene_sim' in launcher
    assert "args.cinematic_sim" not in launcher
    assert '"skeleton.ai.training.jeeves_cinematic_simulation"' in builder

def test_installed_adaptive_scenario_training_is_packaged_without_auto_training():
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    app = Path("skeleton/app/windows_launcher.py").read_text(encoding="utf-8")
    builder = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    assert "test_jeeves_adaptive_sim_training.py" in workflow
    assert '"--adaptive-sim", "--help"' in workflow
    assert '"Adaptive Simulation", self.run_adaptive_sim' in app
    assert '"skeleton.ai.training.jeeves_adaptive_sim_training"' in builder
    assert '"source-bound rehearsals"' not in app.lower()

def test_windows_capacity_growth_is_opt_in_candidate_only():
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    installer = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    trainer = Path("skeleton/ai/training/jeeves_production_game_train.py").read_text(encoding="utf-8")
    assert "test_jeeves_capacity_growth.py" in workflow
    assert '"skeleton.ai.training.jeeves_capacity_growth"' in installer
    assert '"--capacity-growth"' in trainer
    assert '"--max-added-parameters"' in trainer
    assert "candidate_promoted" in trainer

def test_windows_packages_capability_replay_and_attested_parameter_training():
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    installer = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    trainer = Path("skeleton/ai/training/jeeves_production_game_train.py").read_text(encoding="utf-8")
    assert "test_jeeves_capability_replay.py" in workflow
    assert '"skeleton.ai.training.jeeves_capability_replay"' in installer
    assert '"--adaptive-replay"' in trainer
    assert '"--max-scored-examples"' in trainer

def test_installed_boomerang_sim_queue_is_source_pinned_and_review_only():
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    launcher = Path("skeleton/app/windows_launcher.py").read_text(encoding="utf-8")
    packager = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    assert "test_jeeves_boomerang_queue.py" in workflow
    assert '"--boomerang-queue", "--help"' in workflow
    assert '"Boomerang Sim Queue", self.run_boomerang_queue' in launcher
    assert '"skeleton.ai.training.jeeves_boomerang_queue"' in packager
    assert "candidate evidence only" in launcher


def test_windows_payload_covers_manifest_and_docker_copy_inputs():
    """Installed copies must have every file required by their own preflight."""
    import json
    import re

    source = Path("scripts/windows/build_installer.ps1").read_text(encoding="utf-8")
    paths_section = source.split("$RuntimePaths = @(", 1)[1].split("\n)\n$ArchiveArgs", 1)[0]
    staged = set(re.findall(r'^\s*"([^"]+)"', paths_section, flags=re.MULTILINE))

    def included(path: str) -> bool:
        return any(path == entry or path.startswith(entry + "/") for entry in staged
                   if not entry.startswith(":("))

    manifest = json.loads(Path("skeleton/app/manifest.json").read_text(encoding="utf-8"))
    sources = set(manifest["required_paths"])
    for dockerfile in ("Dockerfile", "backend/Dockerfile"):
        docker_text = Path(dockerfile).read_text(encoding="utf-8")
        sources.update(re.findall(
            r"^\s*COPY\s+(?:--\S+\s+)*((?:machine|docs)/\S+)\s",
            docker_text,
            flags=re.MULTILINE,
        ))

    missing = sorted(path for path in sources if not included(path))
    assert not missing, f"first-install payload excludes required files: {missing}"
    assert "$MissingPayloadPaths.Count -gt 0" in source
    assert "Windows payload lacks required app/Docker inputs" in source


def test_host_preload_rejects_stopped_docker_daemon(monkeypatch, tmp_path):
    from skeleton.app.preloader import inspect_host
    from subprocess import CompletedProcess

    monkeypatch.setattr("skeleton.app.preloader.preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr("skeleton.app.preloader.checks_ok", lambda checks: True)
    monkeypatch.setattr("skeleton.app.preloader.shutil.which", lambda name: "docker")
    monkeypatch.setattr(
        "skeleton.app.preloader.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 20 * 1024**3})(),
    )
    def runner(command, **kwargs):
        if command[1] == "info":
            return CompletedProcess(command, 1, stdout="", stderr="Docker daemon unavailable")
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    report = inspect_host(tmp_path, runner=runner, require_python=False, require_pip=False)
    daemon = next(check for check in report.checks if check.code == "host:docker-daemon")
    assert report.ready is False
    assert daemon.required is True
    assert "Start Docker Desktop" in daemon.remediation

def test_windows_launcher_failure_receipts_do_not_show_ready_status(tmp_path):
    from skeleton.app.installer import InstallPhase, InstallReceipt
    from skeleton.app.preloader import PreloadCheck, PreloadReport
    from skeleton.app.windows_launcher import _action_succeeded

    failure = InstallReceipt(tmp_path, (InstallPhase("runtime-preflight", False, "Docker missing"),))
    passed = InstallReceipt(tmp_path, (InstallPhase("runtime-preflight", True, "ok"),))
    blocked = PreloadReport(
        tmp_path, "Windows AMD64", "3.14",
        (PreloadCheck("host:docker-daemon", False, "Docker stopped"),),
    )
    assert not _action_succeeded(failure)
    assert _action_succeeded(passed)
    assert not _action_succeeded(blocked)
    assert not _action_succeeded((False, "cannot stop services"))
    assert _action_succeeded((True, "stopped"))

def test_default_uninstall_retains_credentials_needed_by_existing_mongo_volume():
    source = Path("packaging/windows/SkeletonSetup.iss").read_text(encoding="utf-8")
    assert "[UninstallRun]" in source
    assert 'Parameters: "--stop --quiet"' in source
    assert "[UninstallDelete]" not in source
    assert "preserves named database volumes" in source

def test_windows_installer_runs_actual_frozen_payload_preflight():
    launcher = Path("skeleton/app/windows_launcher.py").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    assert 'mode.add_argument("--verify-payload"' in launcher
    assert "preflight(root, runtime=False, manifest=load_manifest())" in launcher
    assert "return 0 if checks_ok(checks) else 1" in launcher
    assert 'ArgumentList @("--verify-payload")' in workflow
    assert "SkeletonOffline.exe" in workflow
    assert 'ArgumentList @("--help") -Wait -PassThru' in workflow

def test_open_app_does_not_spawn_browser_when_application_is_down(monkeypatch):
    from skeleton.app import windows_launcher as launcher

    monkeypatch.setattr(launcher, "runtime_status", lambda root: (False, "backend offline"))
    calls = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: calls.append(url) or True)
    ok, detail = launcher.open_running_application()
    assert not ok
    assert "backend offline" in detail
    assert calls == []


def test_open_app_reports_browser_failure_after_successful_health_probe(monkeypatch):
    from skeleton.app import windows_launcher as launcher

    monkeypatch.setattr(launcher, "runtime_status", lambda root: (True, "all services healthy"))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: False)
    ok, detail = launcher.open_running_application()
    assert not ok
    assert "no browser accepted" in detail

    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: True)
    ok, detail = launcher.open_running_application()
    assert ok
    assert "all services healthy" in detail

def test_windows_ci_sparse_checkout_contains_every_installer_root():
    source = Path(".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    for required in (
        "/machine/", "/docs/", "/AGENTS.md", "/CLAUDE.md",
        "/GEMINI.md", "/.cursor/rules/architecture.mdc",
        "/.github/copilot-instructions.md",
    ):
        assert required in source


def test_open_app_uses_configured_frontend_port(monkeypatch, tmp_path):
    from skeleton.app import windows_launcher as launcher

    (tmp_path / ".env").write_text("FRONTEND_PORT=3300\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "runtime_status", lambda root: (True, "healthy"))
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url) or True)

    success, detail = launcher.open_running_application(tmp_path)
    assert success
    assert opened == ["http://localhost:3300"]
    assert "http://localhost:3300" in detail


def test_docker_stop_failure_never_echoes_credentials(monkeypatch, tmp_path):
    from skeleton.app import windows_launcher as launcher

    secret = "sensitive-compose-secret"
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 5, stdout=f"MONGO_URL={secret}", stderr=f"JWT_SECRET={secret}",
        )

    monkeypatch.setattr(launcher, "_hidden_runner", runner)
    success, detail = launcher.stop_runtime(tmp_path)
    assert not success
    assert "exit 5" in detail
    assert secret not in detail

def test_disk_preflight_fails_closed_when_installation_drive_disappears(tmp_path, monkeypatch):
    monkeypatch.setattr("skeleton.app.preloader.preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr("skeleton.app.preloader.checks_ok", lambda checks: True)
    monkeypatch.setattr("skeleton.app.preloader.shutil.which", lambda name: None)
    def disk_missing(root):
        raise OSError("drive missing")
    monkeypatch.setattr("skeleton.app.preloader.shutil.disk_usage", disk_missing)

    report = inspect_host(tmp_path, require_python=False, require_pip=False)
    disk = next(item for item in report.checks if item.code == "host:disk")
    assert not disk.ok
    assert report.ready is False
    assert "cannot inspect installation filesystem" in disk.detail
    assert "drive missing" not in disk.detail


def test_windows_hidden_runner_forwards_streaming_compose_output(monkeypatch, tmp_path):
    from skeleton.app import windows_launcher

    observed = {}
    def fake_run(command, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(windows_launcher.subprocess, "run", fake_run)
    log_path = tmp_path / "build.log"
    with log_path.open("w", encoding="utf-8") as output:
        result = windows_launcher._hidden_runner(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=tmp_path, check=False,
            stdout=output, stderr=subprocess.STDOUT, text=True,
            env={"APP_MODE": "production"},
        )
    assert result.returncode == 0
    assert observed["stdout"].closed
    assert observed["stderr"] is subprocess.STDOUT
    assert observed["capture_output"] is False
    assert observed["cwd"] == tmp_path
    assert observed["env"]["APP_MODE"] == "production"
    assert observed["shell"] is False


def test_host_preloader_never_echoes_docker_daemon_credentials(monkeypatch, tmp_path):
    from skeleton.app.preloader import _command_check

    credential = "private-token-present-only-in-child-output"
    for status in (0, 17):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command, status,
                stdout=f"DOCKER_HOST=https://user:{credential}@daemon.internal",
                stderr=f"DOCKER_HOST=https://user:{credential}@daemon.internal",
            )

        probe = _command_check(
            ["docker", "info"], code="host:docker-daemon",
            label="Docker daemon", remediation="Start Docker Desktop",
            runner=runner,
        )
        assert probe.ok is (status == 0)
        assert credential not in probe.detail
        assert "DOCKER_HOST" not in probe.detail


def test_windows_stop_command_raised_error_does_not_show_sensitive_text(monkeypatch, tmp_path):
    from skeleton.app import windows_launcher as launcher

    def runner(command, **kwargs):
        raise OSError("Secret environment variable JWT_SECRET=internal-test-secret")

    monkeypatch.setattr(launcher, "_hidden_runner", runner)
    ok, detail = launcher.stop_runtime(tmp_path)
    assert not ok
    assert "OSError" in detail
    assert "internal-test-secret" not in detail
    assert "JWT_SECRET" not in detail


def test_windows_runtime_probe_exception_uses_type_only(monkeypatch, tmp_path):
    from skeleton.app import windows_launcher as launcher

    def raise_probe(*args, **kwargs):
        raise RuntimeError("private service token leaked from diagnostic")

    monkeypatch.setattr(launcher, "public_service_urls", raise_probe)
    ok, detail = launcher.runtime_status(tmp_path)
    assert not ok
    assert "RuntimeError" in detail
    assert "private service token" not in detail
