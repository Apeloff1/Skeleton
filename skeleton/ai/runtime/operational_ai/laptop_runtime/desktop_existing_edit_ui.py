"""Human-reviewed change candidates for existing offline Jeeves projects.

An existing source file is never overwritten by the model, the desktop or
the candidate publisher. The operator reviews a full original/replacement
diff, approves exact SHA-256 values and writes a separate inert sibling
candidate. Applying a change to original remains an explicit editor/Git step.
"""
from __future__ import annotations

from hashlib import sha256
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_existing_edits import (
    ExistingEditHold, ExistingEditPlan,
    parse_existing_edits, preview_existing_edit,
    stage_existing_edit_candidate,
)


class ExistingEditWindow(tk.Toplevel):
    """Review finite existing-source changes with no original-file mutation."""

    def __init__(self, parent, *, source_text: str = ""):
        super().__init__(parent)
        self.title("Jeeves — Review Existing Source Change")
        self.geometry("1030x780")
        self.minsize(820, 610)
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self.root_path = tk.StringVar(value="")
        self.expected_replacement_sha = tk.StringVar(value="")
        self.status = tk.StringVar(value="No existing-file changes reviewed")
        self._queue: Queue = Queue()
        self._plan: ExistingEditPlan | None = None
        self._reviewed_proposal_sha256: str | None = None
        self._busy = False
        self._closing = False
        self._build()
        if source_text:
            self.proposal.insert("1.0", source_text)
        self.after(75, self._poll)

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=2)
        frame.rowconfigure(4, weight=3)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Existing project root").grid(
            row=0, column=0, sticky="w",
        )
        ttk.Entry(
            top, textvariable=self.root_path,
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(
            top, text="Browse", command=self._browse,
        ).grid(row=0, column=2, sticky="e")
        ttk.Label(
            top, wraplength=950, text=(
                "A model-proposed existing-file edit must supply the original "
                "full SHA-256 and complete replacement text. Review creates a "
                "NEW inert sibling candidate only; it never changes source."
            ),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, sticky="ew")
        self.review_button = ttk.Button(
            actions, text="Inspect checked source changes",
            command=self._review,
        )
        self.review_button.pack(side="left")
        self.reset_button = ttk.Button(
            actions, text="Reset review", command=self._reset,
        )
        self.reset_button.pack(side="left", padx=7)
        self.proposal = ScrolledText(
            frame, wrap="none", height=9, undo=True,
        )
        self.proposal.grid(row=2, column=0, sticky="nsew", pady=(5, 8))
        self.proposal.bind("<<Modified>>", self._edited)

        middle = ttk.Frame(frame)
        middle.grid(row=3, column=0, sticky="ew", pady=(0, 7))
        middle.columnconfigure(0, weight=1)
        columns = ("path", "old_digest", "new_digest", "bytes")
        self.files = ttk.Treeview(
            middle, columns=columns, show="headings",
            height=5, selectmode="browse",
        )
        for key, label, width in (
            ("path", "Existing path", 350),
            ("old_digest", "Original SHA-256", 245),
            ("new_digest", "Replacement SHA-256", 245),
            ("bytes", "New bytes", 90),
        ):
            self.files.heading(key, text=label)
            self.files.column(key, width=width, stretch=key == "path")
        self.files.grid(row=0, column=0, sticky="ew")
        self.files.bind("<<TreeviewSelect>>", self._select)
        scroll = ttk.Scrollbar(
            middle, orient="vertical", command=self.files.yview,
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.files.configure(yscrollcommand=scroll.set)

        self.preview = ScrolledText(
            frame, wrap="none", state="disabled",
            font=("TkFixedFont", 10),
        )
        self.preview.grid(row=4, column=0, sticky="nsew", pady=(0, 9))

        footer = ttk.Frame(frame)
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        ttk.Label(
            footer, text="Confirm FULL replacement SHA-256",
        ).grid(row=0, column=0, sticky="w", padx=(0, 7))
        ttk.Entry(
            footer, textvariable=self.expected_replacement_sha,
        ).grid(row=0, column=1, sticky="ew")
        self.publish_button = ttk.Button(
            footer, text="Stage NEW candidate only",
            command=self._stage,
        )
        self.publish_button.grid(row=0, column=2, sticky="e", padx=(7, 0))
        ttk.Label(
            frame, textvariable=self.status, wraplength=960,
        ).grid(row=6, column=0, sticky="w", pady=(7, 0))
        ttk.Label(
            frame, wraplength=960,
            text=(
                "NEVER auto-applies a change. No Git commit, shell, "
                "old-file deletion, symlink follow, or auto-retry. "
                "Manually apply reviewed candidates in your editor."
            ),
        ).grid(row=7, column=0, sticky="w", pady=(4, 0))
        self.progress = ttk.Progressbar(
            frame, mode="indeterminate",
        )
        self.progress.grid(row=8, column=0, sticky="ew", pady=(7, 0))
        self._buttons()

    def _browse(self):
        if self._busy:
            return
        selected = filedialog.askdirectory(
            parent=self, title="Choose trusted existing project root",
        )
        if selected:
            self.root_path.set(selected)
            self._reset()

    def _edited(self, event=None):
        if self.proposal.edit_modified():
            self.proposal.edit_modified(False)
            if self._plan is not None:
                self._reset()

    def _reset(self):
        if self._busy:
            return
        self._plan = None
        self._reviewed_proposal_sha256 = None
        self.expected_replacement_sha.set("")
        for row in self.files.get_children():
            self.files.delete(row)
        self._preview("")
        self.status.set("Review invalidated; inspect the exact source proposal again")
        self._buttons()

    def _preview(self, text: str):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _buttons(self):
        self.review_button.configure(
            state="disabled" if self._busy else "normal",
        )
        self.reset_button.configure(
            state="disabled" if self._busy else "normal",
        )
        self.publish_button.configure(
            state="normal" if (
                not self._busy and self._plan is not None
                and bool(self.files.selection())
            ) else "disabled",
        )

    def _review(self):
        if self._busy:
            return
        raw = self.proposal.get("1.0", "end-1c")
        try:
            plan = parse_existing_edits(raw, self.root_path.get())
        except Exception as exc:
            self._reset()
            self.status.set(
                "Untrusted proposed edit held: " + type(exc).__name__
                + " · no files changed or staged",
            )
            return
        self._plan = plan
        self._reviewed_proposal_sha256 = sha256(
            raw.encode("utf-8", "strict"),
        ).hexdigest()
        for row in self.files.get_children():
            self.files.delete(row)
        for index, edit in enumerate(plan.edits):
            self.files.insert(
                "", "end", iid=str(index),
                values=(
                    edit.path, edit.original_sha256,
                    edit.replacement_sha256, edit.replacement_bytes,
                ),
            )
        self.status.set(
            str(len(plan.edits)) + " exact source changes reviewed; "
            "manifest SHA-256 " + plan.manifest_sha256
            + " · select one diff and approve replacement digest",
        )
        self.expected_replacement_sha.set("")
        self._buttons()

    def _selected(self):
        if self._busy or self._plan is None:
            raise ExistingEditHold("review source edit before staging")
        selected = self.files.selection()
        if len(selected) != 1:
            raise ExistingEditHold("choose exactly one source edit")
        idx = int(selected[0])
        if not 0 <= idx < len(self._plan.edits):
            raise ExistingEditHold("invalid proposed edit index")
        return idx, self._plan.edits[idx]

    def _select(self, event=None):
        try:
            idx, item = self._selected()
            report = preview_existing_edit(self._plan, idx)
            self._preview(
                "REVIEW ORIGINAL SOURCE — NO AUTOMATIC OVERWRITE"
                + "\nPath: " + report["path"]
                + "\nOriginal SHA-256: " + report["original_sha256"]
                + "\nReplacement SHA-256: " + report["replacement_sha256"]
                + "\nManifest SHA-256: " + report["manifest_sha256"]
                + "\n\n" + report["diff"],
            )
        except Exception as exc:
            self._preview("Source change preview held: " + type(exc).__name__)
        self._buttons()

    def _stage(self):
        try:
            idx, edit = self._selected()
            plan = self._plan
            if (
                plan is None
                or self._reviewed_proposal_sha256 is None
                or self.root_path.get() != plan.root
                or sha256(
                    self.proposal.get("1.0", "end-1c").encode("utf-8", "strict")
                ).hexdigest() != self._reviewed_proposal_sha256
            ):
                raise ExistingEditHold("source review changed after preview")
            if (
                self.expected_replacement_sha.get()
                != edit.replacement_sha256
            ):
                raise ExistingEditHold("full replacement SHA-256 approval required")
        except (ExistingEditHold, ValueError) as exc:
            self.status.set("Candidate held: " + type(exc).__name__)
            return
        self._busy = True
        self.progress.start(90)
        self.status.set(
            "Checking original pinned source and staging a NEW candidate…",
        )
        self._buttons()

        def work():
            try:
                result = stage_existing_edit_candidate(
                    plan, idx,
                    expected_manifest_sha256=plan.manifest_sha256,
                    expected_original_sha256=edit.original_sha256,
                    expected_replacement_sha256=edit.replacement_sha256,
                    approved=True,
                )
                self._queue.put(("created", result))
            except BaseException as exc:
                self._queue.put(("held", type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        if self._closing:
            return
        try:
            while True:
                kind, result = self._queue.get_nowait()
                self._busy = False
                self.progress.stop()
                if kind == "created":
                    self.status.set(
                        "NEW inert candidate staged: "
                        + str(result["candidate_name"])
                        + " · existing source unchanged · SHA-256 "
                        + str(result["replacement_sha256"])
                        + " · manually review/apply in an editor",
                    )
                    self.expected_replacement_sha.set("")
                    # Candidate creation is not application; re-inspection
                    # is required for any changed source or proposal bytes.
                else:
                    self.status.set(
                        "Candidate publication held: " + str(result)
                        + ". An uncertain staged file must be inspected "
                        "manually; no automatic retry.",
                    )
                self._buttons()
        except Empty:
            pass
        self.after(75, self._poll)

    def _exit(self):
        if self._busy:
            self.status.set(
                "One-source candidate staging still in progress; "
                "close only after the explicit result",
            )
            return
        self._closing = True
        self.destroy()


__all__ = ["ExistingEditWindow"]
