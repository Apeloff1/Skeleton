"""Operator-approved bounded local GGUF source generation and repair UI.

A dedicated finite source-work window takes the user's original project
root and goal, uses the existing source-checked SQLite chat and PRIVATE
model worker, and only offers a *new reviewable proposal*. It cannot start
a second model, auto-export source, invoke Git, write original files or
silently retry uncertain native turns.
"""
from __future__ import annotations

from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_source_repair import (
    NativeSourceRepairHold, SourceRepairRequest,
    NativeSourceRepairRunner,
)
from .desktop_project_context import (
    SourceContextHold, ProjectSourceContext,
    snapshot_project_context, revalidate_project_context,
)


class SourceRepairWindow(tk.Toplevel):
    """One source-bound operator session; fully controlled native repair."""

    def __init__(self, parent, *, initial_goal: str = ""):
        super().__init__(parent)
        self.parent_ui = parent
        self.title("Jeeves — Native Source Generation and Finite Repair")
        self.geometry("1060x770")
        self.minsize(830, 640)
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self.root_path = tk.StringVar()
        self.source_format = tk.StringVar(value="new-files")
        self.maximum_attempts = tk.StringVar(value="2")
        self.status = tk.StringVar(
            value="No native source work started; full project and model permissions unchanged",
        )
        self._worker = None
        self._busy = False
        self._closed = False
        self._runner = None
        self._result = None
        self._origin_request = None
        self._source_context: ProjectSourceContext | None = None
        self._source_review_inputs: tuple[str, str] | None = None
        self._events: Queue = Queue()
        self._build()
        if initial_goal:
            self.goal.insert("1.0", initial_goal)
        self.after(85, self._pump)

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=2)
        root.rowconfigure(6, weight=1)
        root.rowconfigure(8, weight=2)

        ttk.Label(
            root,
            text=(
                "The SAME installed local GGUF and existing committed SQLite "
                "session can propose NEW and EXISTING source together and "
                "repair syntax errors up "
                "to an operator-approved finite limit. Every attempt has a "
                "NEW unique SQLite request ID. No source files, tool grants, "
                "Git branches or private patch exports are created here."
            ),
            wraplength=1020,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        workspace = ttk.Frame(root)
        workspace.grid(row=1, column=0, sticky="ew")
        workspace.columnconfigure(1, weight=1)
        ttk.Label(workspace, text="Original local source project root").grid(
            row=0, column=0, sticky="w",
        )
        ttk.Entry(workspace, textvariable=self.root_path).grid(
            row=0, column=1, sticky="ew", padx=7,
        )
        ttk.Button(
            workspace, text="Choose directory",
            command=self._browse,
        ).grid(row=0, column=2)
        ttk.Label(
            workspace,
            text="Optional exact EXISTING source paths (one relative file per line)",
        ).grid(row=1, column=0, sticky="w", pady=(7, 0))
        self.source_paths = ScrolledText(
            workspace, height=3, width=55, wrap="none", undo=True,
        )
        self.source_paths.grid(
            row=1, column=1, sticky="ew", padx=7, pady=(7, 0),
        )
        self.review_sources_button = ttk.Button(
            workspace, text="Review original SHA + full text",
            command=self._review_sources,
        )
        self.review_sources_button.grid(
            row=1, column=2, sticky="e", pady=(7, 0),
        )
        ttk.Label(
            workspace, wraplength=1000,
            text=(
                "Select at most four owned UTF-8 source files (8 KiB total). "
                "The exact original SHA-256 and complete text are sent "
                "as UNTRUSTED read-only reference data to the same GGUF. "
                "No discovery or filesystem tools are granted to the model."
            ),
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        heading = ttk.Frame(root)
        heading.grid(row=2, column=0, sticky="ew", pady=(7, 4))
        ttk.Label(
            heading, text="Original human source-building goal (max 4 KiB)",
        ).pack(side="left")
        ttk.Label(
            heading, text="Never include API credentials or live secrets",
        ).pack(side="right")

        self.goal = ScrolledText(
            root, height=9, undo=True, wrap="word",
        )
        self.goal.grid(row=3, column=0, sticky="nsew")

        budgets = ttk.Frame(root)
        budgets.grid(row=4, column=0, sticky="ew", pady=(9, 6))
        ttk.Label(budgets, text="Required proposal schema").pack(side="left")
        ttk.Combobox(
            budgets, textvariable=self.source_format,
            values=("new-files", "existing-edits", "mixed-work"),
            width=18, state="readonly",
        ).pack(side="left", padx=7)
        ttk.Label(budgets, text="Maximum committed native turns").pack(
            side="left", padx=(12, 5),
        )
        ttk.Combobox(
            budgets, textvariable=self.maximum_attempts,
            values=("1", "2", "3"), width=5, state="readonly",
        ).pack(side="left")
        self.start_button = ttk.Button(
            budgets, text="Generate with explicit finite repair",
            command=self._start,
        )
        self.start_button.pack(side="right", padx=(5, 0))
        self.stop_button = ttk.Button(
            budgets, text="Stop AFTER current native turn",
            command=self._stop,
        )
        self.stop_button.pack(side="right", padx=(5, 0))

        ttk.Label(
            root, text="Original canonical SQLite request IDs — preserve on any hold",
        ).grid(row=5, column=0, sticky="w")
        self.attempts = ttk.Treeview(
            root,
            columns=("attempt", "request_id", "result", "digest"),
            show="headings", height=5,
        )
        for name, title, width in (
            ("attempt", "Attempt", 80),
            ("request_id", "Committed SQLite request ID", 300),
            ("result", "Reviewer result", 170),
            ("digest", "Exact native answer SHA-256", 420),
        ):
            self.attempts.heading(name, text=title)
            self.attempts.column(name, width=width, stretch=name == "digest")
        self.attempts.grid(row=6, column=0, sticky="nsew", pady=(5, 8))

        ttk.Label(
            root, text="Verified proposal text — inert, never applied by the model",
        ).grid(row=7, column=0, sticky="w")
        self.preview = ScrolledText(
            root, height=10, state="disabled", wrap="none",
            font=("TkFixedFont", 10),
        )
        self.preview.grid(row=8, column=0, sticky="nsew", pady=(5, 8))

        bottom = ttk.Frame(root)
        bottom.grid(row=9, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(
            bottom, textvariable=self.status,
            wraplength=790,
        ).grid(row=0, column=0, sticky="w")
        self.review_button = ttk.Button(
            bottom, text="Open COMPLETE operator patch review",
            command=self._open_review,
        )
        self.review_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.grid(row=10, column=0, sticky="ew", pady=(9, 0))
        ttk.Label(
            root, wraplength=1020,
            text=(
                "Failure/timeout means uncertain SQLite effect. Never "
                "rerun the same request ID automatically. A parser-clean "
                "proposal is NOT a build, committed source change or release. "
                "It still requires complete human patch review and SHA approval."
            ),
        ).grid(row=11, column=0, sticky="ew", pady=(7, 0))
        self._buttons()

    def _buttons(self):
        bridge = self.parent_ui._bridge
        connected = (
            bridge is not None
            and bridge.connected
            and bridge.session_id is not None
            and not self.parent_ui._busy
        )
        self.start_button.configure(
            state="normal" if not self._busy and connected else "disabled",
        )
        self.stop_button.configure(
            state="normal" if self._busy and self._runner is not None
            else "disabled",
        )
        self.review_sources_button.configure(
            state="normal" if not self._busy else "disabled",
        )
        self.review_button.configure(
            state="normal" if not self._busy
            and self._result is not None
            and self._result.status == "review-required"
            else "disabled",
        )

    def _browse(self):
        if self._busy:
            return
        selected = filedialog.askdirectory(
            parent=self, title="Choose original trusted project source root",
        )
        if selected:
            self.root_path.set(selected)
            self._result = None
            self._source_context = None
            self._source_review_inputs = None
            self._buttons()

    def _context_inputs(self) -> tuple[str, str]:
        return (
            self.root_path.get(),
            self.source_paths.get("1.0", "end-1c"),
        )

    def _review_sources(self):
        if self._busy:
            return
        root, selected = self._context_inputs()
        if not selected.strip():
            self._source_context = None
            self._source_review_inputs = None
            self.status.set("No project source selected; original goal-only workflow")
            return
        try:
            context = snapshot_project_context(root, selected)
        except (SourceContextHold, OSError, ValueError) as exc:
            self._source_context = None
            self._source_review_inputs = None
            self.status.set(
                "Exact source context refused: " + type(exc).__name__
                + " · no native model request started",
            )
            return
        self._source_context = context
        self._source_review_inputs = (root, selected)
        detail = (
            "REVIEW ORIGINAL SOURCE — No native work, no source file write.\n"
            + "Manifest SHA-256: " + context.manifest_sha256 + "\n"
            + "Original project file count: " + str(len(context.files)) + "\n\n"
        )
        for file in context.files:
            detail += (
                "EXACT SOURCE: " + file.path + "\n"
                + "SHA-256: " + file.sha256 + "\n"
                + "UTF-8 bytes: " + str(file.bytes)
                + "\n--- BEGIN READ-ONLY ORIGINAL ---\n"
                + file.text + "\n--- END READ-ONLY ORIGINAL ---\n\n"
            )
        preview = tk.Toplevel(self)
        preview.title("Reviewed exact local project source — data, not tool grants")
        preview.geometry("980x650")
        textbox = ScrolledText(preview, wrap="none", state="normal")
        textbox.pack(fill="both", expand=True)
        textbox.insert("1.0", detail)
        textbox.configure(state="disabled")
        self.status.set(
            "Reviewed " + str(len(context.files)) + " selected source files / "
            + str(context.total_bytes) + " bytes · SHA-256 "
            + context.manifest_sha256
            + ". Start still requires explicit approval; files rechecked each turn.",
        )

    def _start(self):
        if self._busy:
            return
        bridge = self.parent_ui._bridge
        if (
            bridge is None or not bridge.connected
            or bridge.session_id is None
            or self.parent_ui._busy
        ):
            self.status.set("A real installed native GGUF/SQLite session is required")
            return
        try:
            context_raw = self._context_inputs()
            source_context = None
            if context_raw[1].strip():
                if (
                    self._source_context is None
                    or context_raw != self._source_review_inputs
                ):
                    raise NativeSourceRepairHold(
                        "review exact selected source paths before native inference",
                    )
                revalidate_project_context(self._source_context)
                source_context = self._source_context
            selected = SourceRepairRequest(
                root=self.root_path.get(),
                goal=self.goal.get("1.0", "end-1c"),
                format=self.source_format.get(),
                maximum_attempts=int(self.maximum_attempts.get()),
                source_context=source_context,
            )
        except (ValueError, NativeSourceRepairHold, SourceContextHold, OSError) as exc:
            self.status.set("Source work held: " + type(exc).__name__)
            return
        if not messagebox.askyesno(
            "Approve finite ORIGINAL native work?",
            "Authorize up to " + str(selected.maximum_attempts)
            + " UNIQUE, durably committed local GGUF source attempts "
            + "on the currently active SQLite session? "
            + "No Git, shell, file write or unknown model tool is allowed. "
            + "Any separately reviewed original file text + SHA-256 will "
            + "be sent as task DATA on every native attempt (never a tool grant). "
            + "Each syntax-repair attempt is a distinct visible native "
            + "request; an uncertain request is NEVER automatically retried.",
            parent=self,
        ):
            return
        try:
            runner = NativeSourceRepairRunner(
                bridge, selected, approved=True,
                progress=lambda item: self._events.put(("progress", item)),
            )
        except (NativeSourceRepairHold, ValueError) as exc:
            self.status.set("Native source work denied: " + type(exc).__name__)
            return
        self._worker = bridge
        self._origin_request = selected
        self._result = None
        self._runner = runner
        for item in self.attempts.get_children():
            self.attempts.delete(item)
        self._preview("")
        self._busy = True
        self.progress.start(85)
        self.status.set(
            "Single native worker owns bounded source generation. "
            "Every attempted inference gets an original SQLite ID…",
        )
        self._buttons()

        def work():
            try:
                result = runner.execute()
                self._events.put(("complete", result))
            except BaseException as exc:
                self._events.put(("held", type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _stop(self):
        if self._busy and self._runner is not None:
            self._runner.stop_after_current()
            self.status.set(
                "Operator stop requested AFTER current committed native turn. "
                "In-flight SQLite effect cannot be safely cancelled by replay.",
            )

    def _preview(self, text: str):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _open_review(self):
        result = self._result
        if (
            self._busy or result is None
            or result.status != "review-required"
            or result.candidate is None
            or result.proposal is None
        ):
            return
        # A separately reviewable candidate: no trusted agent output can
        # prepopulate approval hashes or auto-call private patch export.
        from .desktop_patch_ui import PortablePatchWindow
        window = PortablePatchWindow(
            self.parent_ui, source_text=result.proposal,
        )
        window.root_path.set(result.candidate.root)
        window.expected_manifest.set("")
        window.expected_patch.set("")
        self.status.set(
            "Opened exact independent human patch review; "
            "native model has not modified any project files.",
        )

    def _pump(self):
        if self._closed:
            return
        try:
            while True:
                kind, result = self._events.get_nowait()
                if kind == "progress":
                    if not self.attempts.exists(str(result.number)):
                        self.attempts.insert(
                            "", "end", iid=str(result.number),
                            values=(
                                result.number, result.request_id,
                                result.source_result,
                                result.committed_answer_sha256,
                            ),
                        )
                    self.status.set(
                        "Native attempt " + str(result.number)
                        + ": " + result.source_result
                        + " · source issue(s): "
                        + ", ".join(result.issue_codes[:3])
                        + " · retain request ID " + result.request_id,
                    )
                    continue
                self._busy = False
                self.progress.stop()
                self._runner = None
                if kind != "complete":
                    self._result = None
                    self.status.set(
                        "Native SQLite source generation terminally held: "
                        + str(result) + ". Preserve all visible request IDs; "
                        "no automatic native retry or source publication.",
                    )
                else:
                    self._result = result
                    receipt = result.public_receipt()
                    if receipt["status"] == "review-required":
                        self._preview(result.proposal)
                        self.status.set(
                            "SOURCE PROPOSAL CREATED IN SQLITE · "
                            + str(receipt["attempt_count"]) + " native turn(s)"
                            + " · " + str(receipt["static_source_status"])
                            + " · patch SHA-256 "
                            + str(receipt["source_patch_sha256"])
                            + " · reviewed original source context "
                            + str(receipt["operator_source_context_sha256"])
                            + ". Human review and approval are STILL required.",
                        )
                    else:
                        self.status.set(
                            "Native source task " + receipt["status"]
                            + " after " + str(receipt["attempt_count"])
                            + " committed unique native turn(s). "
                            + "No source files or Git index changed.",
                        )
                self._buttons()
        except Empty:
            pass
        self.after(85, self._pump)

    def _exit(self):
        if self._busy:
            self.status.set(
                "A native SQLite turn may be in progress. "
                "Stop after current and preserve every request ID before closing.",
            )
            return
        self._closed = True
        self.destroy()


__all__ = ["SourceRepairWindow"]
