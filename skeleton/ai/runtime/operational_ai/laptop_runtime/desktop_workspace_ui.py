"""Operator-controlled Jeeves code delivery: review before local file creation.

The model cannot publish files. The operator selects the workspace, reviews
the exact proposed bytes and explicitly confirms a digest for EACH new file.
Existing files and protected Git metadata are never replaced or executed.
"""
from __future__ import annotations

from queue import Queue, Empty
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter.scrolledtext import ScrolledText

from .desktop_workspace import (
    WorkspaceDeliveryHold, WorkspacePlan,
    parse_plan, preview_file, publish_file,
)


class WorkspaceWindow(tk.Toplevel):
    def __init__(self, parent, *, source_text: str = ""):
        super().__init__(parent)
        self.title("Jeeves — Explicit Local Source Delivery")
        self.geometry("980x730")
        self.minsize(820, 600)
        self._events = Queue()
        self._busy = False
        self._closed = False
        self._plan: WorkspacePlan | None = None
        self.root_path = tk.StringVar(value="")
        self.approval_sha = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="No proposed source has been reviewed")
        self._build()
        if source_text:
            self.proposal.insert("1.0", source_text)
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self.after(100, self._pump)

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(3, weight=2)
        frame.rowconfigure(5, weight=2)
        frame.columnconfigure(0, weight=1)

        location = ttk.Frame(frame)
        location.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        location.columnconfigure(1, weight=1)
        ttk.Label(location, text="Trusted local workspace root").grid(
            row=0, column=0, padx=(0, 7),
        )
        ttk.Entry(location, textvariable=self.root_path).grid(
            row=0, column=1, sticky="ew",
        )
        ttk.Button(location, text="Browse", command=self._choose_root).grid(
            row=0, column=2, padx=(5, 0),
        )

        ttk.Label(
            frame, text=(
                "Paste a Jeeves JSON proposal. Only new files are permitted. "
                "No automatic tools, overwrites, executable launches or "
                "GitHub writes. The checked directory tree must exist already."
            ), wraplength=900,
        ).grid(row=1, column=0, sticky="w", pady=(0, 5))

        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew")
        self.stage_button = ttk.Button(
            controls, text="Inspect proposed new files", command=self._review,
        )
        self.stage_button.pack(side="left")
        self.reset_button = ttk.Button(
            controls, text="Reset review", command=self._reset,
        )
        self.reset_button.pack(side="left", padx=8)
        self.proposal = ScrolledText(frame, height=9, wrap="none", undo=True)
        self.proposal.grid(row=3, column=0, sticky="nsew", pady=(4, 9))
        self.proposal.bind("<<Modified>>", self._invalidate_on_edit)

        middle = ttk.Frame(frame)
        middle.grid(row=4, column=0, sticky="ew", pady=(0, 4))
        middle.columnconfigure(0, weight=1)
        columns = ("path", "bytes", "sha")
        self.files = ttk.Treeview(
            middle, columns=columns, show="headings", height=5,
            selectmode="browse",
        )
        for key, label, width in (
            ("path", "New relative file", 410),
            ("bytes", "UTF-8 bytes", 105),
            ("sha", "SHA-256", 380),
        ):
            self.files.heading(key, text=label)
            self.files.column(key, width=width, stretch=key == "path")
        self.files.grid(row=0, column=0, sticky="nsew")
        self.files.bind("<<TreeviewSelect>>", self._preview_selection)
        middle.rowconfigure(0, weight=1)
        scroll = ttk.Scrollbar(middle, orient="vertical", command=self.files.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.files.configure(yscrollcommand=scroll.set)

        self.preview = ScrolledText(
            frame, height=10, wrap="none", state="disabled",
        )
        self.preview.grid(row=5, column=0, sticky="nsew", pady=(0, 8))

        approve = ttk.Frame(frame)
        approve.grid(row=6, column=0, sticky="ew")
        approve.columnconfigure(1, weight=1)
        ttk.Label(approve, text="Confirm full reviewed SHA-256").grid(
            row=0, column=0, padx=(0, 6),
        )
        ttk.Entry(approve, textvariable=self.approval_sha).grid(
            row=0, column=1, sticky="ew",
        )
        self.publish_button = ttk.Button(
            approve, text="Publish only selected NEW file",
            command=self._publish,
        )
        self.publish_button.grid(row=0, column=2, padx=(7, 0))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=7, column=0, sticky="ew", pady=6)
        ttk.Label(
            frame, textvariable=self.status_text, wraplength=920,
        ).grid(row=8, column=0, sticky="w")
        self._buttons()

    def _choose_root(self):
        if self._busy:
            return
        selected = filedialog.askdirectory(
            parent=self, title="Select an already-trusted local project directory",
        )
        if selected:
            self.root_path.set(selected)
            self._reset()

    def _invalidate_on_edit(self, event):
        if self.proposal.edit_modified():
            self.proposal.edit_modified(False)
            if self._plan is not None:
                self._reset(clear_text=False)

    def _reset(self, clear_text=False):
        if self._busy:
            return
        self._plan = None
        self.approval_sha.set("")
        for row in self.files.get_children():
            self.files.delete(row)
        self._show_preview("")
        self.status_text.set("Source review invalidated; inspect exact JSON again")
        if clear_text:
            self.proposal.delete("1.0", "end")
        self._buttons()

    def _show_preview(self, text):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _buttons(self):
        self.stage_button.configure(state="disabled" if self._busy else "normal")
        self.reset_button.configure(state="disabled" if self._busy else "normal")
        self.publish_button.configure(
            state="normal" if self._plan is not None and not self._busy
            and self.files.selection() else "disabled",
        )

    def _review(self):
        if self._busy:
            return
        root = self.root_path.get()
        raw = self.proposal.get("1.0", "end-1c")
        try:
            plan = parse_plan(raw, root)
        except Exception as exc:
            # Filesystem policy errors from the canonical trusted-root layer
            # are not necessarily ValueError; never disclose their paths.
            self._reset()
            self.status_text.set(
                "Proposal held: " + type(exc).__name__
                + " — no local files created",
            )
            return
        self._plan = plan
        for row in self.files.get_children():
            self.files.delete(row)
        for index, item in enumerate(plan.entries):
            self.files.insert(
                "", "end", iid=str(index),
                values=(item.path, item.bytes, item.sha256),
            )
        self.status_text.set(
            str(len(plan.entries)) + " source files inspected; manifest "
            + plan.manifest_sha256 + " — review and approve individually",
        )
        self.approval_sha.set("")
        self._buttons()

    def _preview_selection(self, event=None):
        if self._plan is None or not self.files.selection():
            self._buttons()
            return
        index = int(self.files.selection()[0])
        try:
            details = preview_file(self._plan, index)
            self._show_preview(
                "NEW SOURCE FILE: " + details["path"] + "\n"
                + "SHA-256: " + details["sha256"] + "\n\n"
                + details["diff"],
            )
        except Exception as exc:
            self._show_preview("Preview held: " + type(exc).__name__)
        self._buttons()

    def _publish(self):
        if self._busy or self._plan is None or not self.files.selection():
            return
        index = int(self.files.selection()[0])
        expected = self._plan.entries[index].sha256
        if self.approval_sha.get() != expected:
            self.status_text.set(
                "Refused: type/paste the full source SHA-256 shown in the preview",
            )
            return
        plan = self._plan
        self._busy = True
        self.progress.start(90)
        self.status_text.set("Atomically publishing one approved source file…")
        self._buttons()

        def run():
            try:
                receipt = publish_file(
                    plan, index, expected_manifest_sha256=plan.manifest_sha256,
                    expected_file_sha256=expected, approved=True,
                )
                self._events.put(("ok", receipt))
            except BaseException as exc:
                self._events.put(("hold", type(exc).__name__))

        threading.Thread(target=run, daemon=True).start()

    def _pump(self):
        if self._closed:
            return
        try:
            while True:
                outcome, detail = self._events.get_nowait()
                self._busy = False
                self.progress.stop()
                if outcome == "ok":
                    self.status_text.set(
                        "Published " + str(detail["path"]) + " · "
                        + str(detail["sha256"])
                        + " · no existing files overwritten",
                    )
                    self.approval_sha.set("")
                    self._show_preview(
                        "Published one new source file. Other proposed files "
                        "remain unapproved; each requires its own SHA confirmation.",
                    )
                else:
                    self.status_text.set(
                        "Source publication held: " + str(detail)
                        + ". Partial I/O may be uncertain; inspect the target "
                        "manually. No automatic retry.",
                    )
                self._buttons()
        except Empty:
            pass
        self.after(100, self._pump)

    def _exit(self):
        if self._busy:
            self.status_text.set(
                "One-file atomic publication is still active; wait for "
                "its result before closing this operator review.",
            )
            return
        self._closed = True
        self.destroy()


__all__ = ["WorkspaceWindow"]
