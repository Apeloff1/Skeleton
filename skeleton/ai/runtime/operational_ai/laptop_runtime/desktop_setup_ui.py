"""Local-only first-install assistant for the private Jeeves desktop.

The setup window delegates to the existing audited bundle installer and
descriptor-anchored private-root provisioning. It never downloads a model,
accepts generated license claims or silently migrates a previous SQLite DB.
"""
from __future__ import annotations

from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_provision import (
    inspect_existing_model, install_local_approved_archive,
    prepare_private_root,
)


class SetupWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_ui = parent
        self.title("Jeeves — Approved Offline Model Setup")
        self.geometry("840x560")
        self.minsize(700, 470)
        self._events = Queue()
        self._busy = False
        self._closed = False
        self.archive = tk.StringVar()
        self.install_root = tk.StringVar()
        self.model_id = tk.StringVar()
        self.install_id = tk.StringVar()
        self.model_root = tk.StringVar(
            value=parent.fields["model_root"].get(),
        )
        self.state_root = tk.StringVar(
            value=parent.fields["state_dir"].get(),
        )
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self.after(100, self._pump)

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        fields = (
            ("Approved ordered bundle archive", self.archive, "file"),
            ("Private installation parent", self.install_root, "directory"),
            ("Manifest model ID", self.model_id, None),
            ("New install ID", self.install_id, None),
            ("Existing installed model directory", self.model_root, "directory"),
            ("Private state directory", self.state_root, "directory"),
        )
        for i, (label, variable, picker) in enumerate(fields):
            ttk.Label(root, text=label).grid(
                row=i, column=0, sticky="w", pady=5,
            )
            ttk.Entry(root, textvariable=variable).grid(
                row=i, column=1, sticky="ew", padx=(8, 6), pady=5,
            )
            if picker is not None:
                ttk.Button(
                    root, text="Browse",
                    command=lambda v=variable, p=picker: self._browse(v, p),
                ).grid(row=i, column=2, pady=5)

        actions = ttk.Frame(root)
        actions.grid(row=6, column=0, columnspan=3, sticky="ew", pady=11)
        self.install_button = ttk.Button(
            actions, text="Install approved bundle", command=self._install,
        )
        self.install_button.pack(side="left", padx=4)
        self.inspect_button = ttk.Button(
            actions, text="Inspect model (read-only)", command=self._inspect,
        )
        self.inspect_button.pack(side="left", padx=4)
        self.prepare_button = ttk.Button(
            actions, text="Prepare private state", command=self._prepare,
        )
        self.prepare_button.pack(side="left", padx=4)
        self.adopt_button = ttk.Button(
            actions, text="Use selected paths", command=self._adopt,
        )
        self.adopt_button.pack(side="right", padx=4)

        ttk.Label(
            root, text=(
                "Only operator-approved local packages. A manifest's license "
                "metadata is NOT an independent rights review."
            ), wraplength=760,
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(5, 5))
        root.rowconfigure(8, weight=1)
        self.report = ScrolledText(
            root, height=10, wrap="word", state="disabled",
        )
        self.report.grid(row=8, column=0, columnspan=3, sticky="nsew")
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew", pady=6)

    def _browse(self, target, kind):
        selected = (
            filedialog.askopenfilename(parent=self)
            if kind == "file" else filedialog.askdirectory(parent=self)
        )
        if selected:
            target.set(selected)

    def _log(self, text):
        self.report.configure(state="normal")
        self.report.insert("end", text + "\n\n")
        self.report.configure(state="disabled")
        self.report.see("end")

    def _start(self, kind, function):
        if self._busy:
            return
        self._busy = True
        self.progress.start(90)
        for button in (self.install_button, self.inspect_button,
                       self.prepare_button):
            button.configure(state="disabled")
        self._log("Running local " + kind + " — no remote model downloads")

        def work():
            try:
                result = function()
                self._events.put(("ok", kind, result))
            except BaseException as exc:
                # The installer can include private model paths in exceptions.
                # Only the public error class may reach the GUI log.
                self._events.put(("error", kind, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _install(self):
        archive = self.archive.get()
        root = self.install_root.get()
        model = self.model_id.get()
        identity = self.install_id.get()
        self._start(
            "bounded model installation",
            lambda: install_local_approved_archive(
                archive, root, model_id=model, install_id=identity,
            ),
        )

    def _inspect(self):
        path = self.model_root.get()
        self._start(
            "source inventory inspection",
            lambda: inspect_existing_model(path),
        )

    def _prepare(self):
        path = self.state_root.get()
        self._start(
            "private state-root preparation",
            lambda: prepare_private_root(path),
        )

    def _adopt(self):
        if self._busy:
            self._log("Installation/inspection still active; cannot change active paths")
            return
        self.parent_ui.fields["model_root"].set(self.model_root.get())
        self.parent_ui.fields["state_dir"].set(self.state_root.get())
        self._log(
            "Paths selected. Connect still requires real installed rights and "
            "source verification; no native activation has occurred."
        )

    def _pump(self):
        if self._closed:
            return
        try:
            while True:
                status, kind, result = self._events.get_nowait()
                self._busy = False
                self.progress.stop()
                for button in (self.install_button, self.inspect_button,
                               self.prepare_button):
                    button.configure(state="normal")
                if status == "error":
                    self._log(kind + " held: " + str(result))
                    continue
                if kind == "bounded model installation":
                    self.model_root.set(str(result["destination"]))
                    self.parent_ui.fields["model_root"].set(str(result["destination"]))
                if kind == "private state-root preparation":
                    self.parent_ui.fields["state_dir"].set(self.state_root.get())
                # Show only finite public receipt fields, never file contents.
                visible = {
                    key: value for key, value in result.items()
                    if key not in ("destination",)
                }
                self._log(kind + " completed: " + repr(visible))
                self._log(
                    "This action does not prove native model inference, physical "
                    "laptop performance, independent license rights or release."
                )
        except Empty:
            pass
        self.after(100, self._pump)

    def _exit(self):
        if self._busy:
            self._log(
                "Model installation is active. Keep this setup window open "
                "until the canonical installer finishes safely."
            )
            return
        self._closed = True
        self.destroy()


__all__ = ["SetupWindow"]
