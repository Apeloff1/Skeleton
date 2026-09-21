"""Windows GUI launcher for the installed Skeleton application.

The launcher is packaged with PyInstaller and therefore does not require a
system Python installation. Docker Desktop / Compose remains the external
runtime boundary for the assembled application services.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser

from skeleton.app.assembly import compose_command, load_manifest
from skeleton.app.health import probe_application, probes_ok
from skeleton.app.installer import InstallReceipt, install_application
from skeleton.app.preloader import PreloadReport, inspect_host


APP_URL = "http://localhost:3000"
DOCKER_DESKTOP_URL = "https://www.docker.com/products/docker-desktop/"


def installation_root() -> Path:
    """Resolve the writable application payload root."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _hidden_runner(
    command,
    *,
    cwd=None,
    check: bool = False,
    capture_output: bool = False,
    text: bool = False,
    timeout: float | None = None,
    env=None,
):
    """Run an argument-vector child process without a Windows console flash."""

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        env=env,
        shell=False,
        creationflags=creationflags,
    )


def _format_preload(report: PreloadReport) -> str:
    lines = [
        f"Host: {report.platform}",
        f"Application files: {report.root}",
        "",
    ]
    for check in report.checks:
        state = "PASS" if check.ok else ("WARN" if not check.required else "FAIL")
        suffix = " (optional)" if not check.required else ""
        lines.append(f"[{state}] {check.code}{suffix}: {check.detail}")
        if not check.ok and check.remediation:
            lines.append(f"       {check.remediation}")
    lines.append("")
    lines.append("System is ready." if report.ready else "System needs attention before startup.")
    return "\n".join(lines)


def _format_receipt(receipt: InstallReceipt) -> str:
    lines = []
    for phase in receipt.phases:
        state = "PASS" if phase.ok else ("WARN" if not phase.required else "FAIL")
        suffix = " (optional)" if not phase.required else ""
        lines.append(f"[{state}] {phase.name}{suffix}: {phase.detail}")
    lines.append("")
    lines.append("Runtime is ready." if receipt.ok else "Setup stopped at a failed phase.")
    return "\n".join(lines)


def check_host(root: Path | None = None) -> PreloadReport:
    return inspect_host(
        root or installation_root(),
        runner=_hidden_runner,
        require_python=False,
        require_pip=False,
    )


def repair_runtime(root: Path | None = None) -> InstallReceipt:
    return install_application(
        root or installation_root(),
        install_python=False,
        bundled_runtime=True,
        start=False,
        runner=_hidden_runner,
    )


def start_runtime(
    root: Path | None = None,
    *,
    production: bool = True,
    full: bool = False,
) -> InstallReceipt:
    return install_application(
        root or installation_root(),
        install_python=False,
        bundled_runtime=True,
        start=True,
        production=production,
        full=full,
        runner=_hidden_runner,
    )


def stop_runtime(root: Path | None = None) -> tuple[bool, str]:
    root = (root or installation_root()).resolve()
    try:
        completed = _hidden_runner(
            list(compose_command("down", manifest=load_manifest())),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Unable to stop services: {type(exc).__name__}: {exc}"
    if completed.returncode == 0:
        return True, "Skeleton services stopped."
    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
    tail = detail[-1][:300] if detail else f"exit {completed.returncode}"
    return False, f"Stop command failed: {tail}"


def runtime_status(root: Path | None = None) -> tuple[bool, str]:
    del root
    try:
        results = probe_application(manifest=load_manifest(), timeout=2.0)
    except Exception as exc:
        return False, f"Runtime probe failed: {type(exc).__name__}: {exc}"
    if not results:
        return False, "No public health probes are configured."
    lines = []
    for result in results:
        state = "ONLINE" if result.ok else "OFFLINE"
        status = result.status if result.status is not None else "-"
        lines.append(f"[{state}] {result.service}: HTTP {status} — {result.detail}")
    return probes_ok(results), "\n".join(lines)


class WindowsLauncher:
    """Small Windows setup/runtime control surface."""

    def __init__(self, root: Path) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.app_root = root.resolve()
        self.window = tk.Tk()
        self.window.title("Skeleton Setup & Runtime")
        self.window.geometry("820x610")
        self.window.minsize(720, 520)

        self.status = tk.StringVar(value="Checking system…")
        self._buttons: list[ttk.Button] = []

        outer = ttk.Frame(self.window, padding=20)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="Skeleton", font=("Segoe UI", 22, "bold"))
        title.pack(anchor="w")
        subtitle = ttk.Label(
            outer,
            text="Windows setup, repair and application runtime",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(0, 16))

        status_frame = ttk.Frame(outer)
        status_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(status_frame, textvariable=self.status, font=("Segoe UI", 10, "bold")).pack(
            side="left"
        )
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=170)
        self.progress.pack(side="right")

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(0, 14))
        self._add_button(buttons, "System Check", self.system_check)
        self._add_button(buttons, "Install / Repair", self.repair)
        self._add_button(buttons, "Start Skeleton", self.start)
        self._add_button(buttons, "Open App", self.open_app)
        self._add_button(buttons, "Stop", self.stop)

        helper = ttk.Frame(outer)
        helper.pack(fill="x", pady=(0, 10))
        ttk.Label(
            helper,
            text="Docker Desktop with Docker Compose is required to run the assembled services.",
            font=("Segoe UI", 9),
        ).pack(side="left")
        ttk.Button(helper, text="Get Docker Desktop", command=self.open_docker).pack(side="right")

        self.log = tk.Text(
            outer,
            wrap="word",
            height=24,
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
        )
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        footer = ttk.Label(
            outer,
            text=f"Installed at {self.app_root}",
            font=("Segoe UI", 8),
        )
        footer.pack(anchor="w", pady=(10, 0))

        self.window.after(200, self.system_check)

    def _add_button(self, parent, text: str, command) -> None:
        button = self.ttk.Button(parent, text=text, command=command)
        button.pack(side="left", padx=(0, 8))
        self._buttons.append(button)

    def _set_log(self, value: str) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("1.0", value)
        self.log.configure(state="disabled")

    def _busy(self, value: bool, status: str = "") -> None:
        state = "disabled" if value else "normal"
        for button in self._buttons:
            button.configure(state=state)
        if value:
            self.progress.start(12)
        else:
            self.progress.stop()
        if status:
            self.status.set(status)

    def _run_worker(self, label: str, work, render) -> None:
        if any(str(button.cget("state")) == "disabled" for button in self._buttons):
            return
        self._busy(True, label)

        def worker() -> None:
            try:
                result = work()
                rendered = render(result)
                error = None
            except Exception as exc:
                rendered = f"{type(exc).__name__}: {exc}"
                error = exc

            def finish() -> None:
                self._set_log(rendered)
                self._busy(False, "Ready" if error is None else "Action failed")

            self.window.after(0, finish)

        threading.Thread(target=worker, name="skeleton-windows-launcher", daemon=True).start()

    def system_check(self) -> None:
        self._run_worker(
            "Checking Windows host…",
            lambda: check_host(self.app_root),
            _format_preload,
        )

    def repair(self) -> None:
        self._run_worker(
            "Installing / repairing runtime…",
            lambda: repair_runtime(self.app_root),
            _format_receipt,
        )

    def start(self) -> None:
        self._run_worker(
            "Building and starting Skeleton…",
            lambda: start_runtime(self.app_root),
            _format_receipt,
        )

    def stop(self) -> None:
        self._run_worker(
            "Stopping services…",
            lambda: stop_runtime(self.app_root),
            lambda result: result[1],
        )

    def open_app(self) -> None:
        online, detail = runtime_status(self.app_root)
        self._set_log(detail)
        if online:
            webbrowser.open(APP_URL)
            self.status.set("Application opened")
        else:
            self.status.set("Application is not ready")

    def open_docker(self) -> None:
        webbrowser.open(DOCKER_DESKTOP_URL)

    def run(self) -> int:
        self.window.mainloop()
        return 0


def _headless(args: argparse.Namespace, root: Path) -> int:
    if args.check:
        report = check_host(root)
        if not args.quiet:
            print(_format_preload(report))
        return 0 if report.ready else 1
    if args.repair:
        receipt = repair_runtime(root)
        if not args.quiet:
            print(_format_receipt(receipt))
        return 0 if receipt.ok else 1
    if args.start:
        receipt = start_runtime(root, production=not args.development, full=args.full)
        if not args.quiet:
            print(_format_receipt(receipt))
        return 0 if receipt.ok else 1
    if args.stop:
        ok, detail = stop_runtime(root)
        if not args.quiet:
            print(detail)
        return 0 if ok else 1
    if args.open:
        online, detail = runtime_status(root)
        if not args.quiet:
            print(detail)
        if online:
            webbrowser.open(APP_URL)
            return 0
        return 1
    return -1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="Skeleton.exe")
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--repair", action="store_true")
    mode.add_argument("--start", action="store_true")
    mode.add_argument("--stop", action="store_true")
    mode.add_argument("--open", action="store_true")
    result.add_argument(
        "--development",
        action="store_true",
        help="start development image stages instead of the installed production topology",
    )
    result.add_argument("--full", action="store_true")
    result.add_argument("--quiet", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = installation_root()
    headless = _headless(args, root)
    if headless >= 0:
        return headless
    if os.name != "nt":
        print("Skeleton Windows launcher requires Windows.")
        return 2
    return WindowsLauncher(root).run()


if __name__ == "__main__":
    raise SystemExit(main())
