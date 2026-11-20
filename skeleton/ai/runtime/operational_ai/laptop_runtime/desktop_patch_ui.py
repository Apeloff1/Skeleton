"""Desktop review and export of one original no-clobber offline Git patch.

Two existing Jeeves source interfaces become one coherent operator-approved
delivery: NEW files and checked existing-file edits. Neither model text nor
this Tk window may execute Git, stage the repository, overwrite originals,
create executable files, or silently apply the patch.
"""
from __future__ import annotations

import json
from pathlib import Path
from queue import Empty, Queue
import threading
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
    from tkinter.scrolledtext import ScrolledText
except ImportError:
    tk = None  # type: ignore
    filedialog = messagebox = simpledialog = ttk = None  # type: ignore
    ScrolledText = None  # type: ignore

from .desktop_existing_edits import SCHEMA as EDIT_SCHEMA
from .desktop_patch_bundle import (
    PortablePatchPlan, review_patch_bundle, get_reviewed_patch,
)
from .desktop_patch_export import export_reviewed_patch, verify_saved_patch
from .desktop_private_overlay import (
    stage_reviewed_overlay, verify_staged_overlay,
)
from .desktop_source_qualification import qualify_patch_sources
from .desktop_source_graph import analyze_python_source_graph
from .desktop_patch_reconcile import reconcile_reviewed_patch
from .desktop_private_capsule import (
    prepare_private_capsule, publish_private_capsule, verify_private_capsule,
)
from .desktop_project_work import (
    SCHEMA as MIXED_WORK_SCHEMA,
    MixedWorkHold, parse_mixed_work,
)


class PortablePatchWindow(tk.Toplevel if tk is not None else object):
    """Human-selected project, exact untrusted sources, private exported diff."""

    def __init__(self, parent, *, source_text: str = ""):
        super().__init__(parent)
        self.parent_ui = parent
        self.title("Jeeves — Review and Export Native Git Patch")
        self.geometry("1180x850")
        self.minsize(900, 675)
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self.root_path = tk.StringVar()
        self.export_path = tk.StringVar()
        self.expected_manifest = tk.StringVar()
        self.expected_patch = tk.StringVar()
        self.capsule_expected = tk.StringVar()
        self._capsule_plan = None
        self._capsule_source_selection = None
        self._capsule_receipt = None
        self._capsule_path = None
        self.status = tk.StringVar(
            value="No source patch reviewed. The model has no Git/file-write tools.",
        )
        self._busy = False
        self._closed = False
        self._epoch = 0
        self._plan: PortablePatchPlan | None = None
        self._reviewed_texts = None
        self._export_receipt = None
        self._stage_receipt = None
        self._stage_path = None
        self._qualification = None
        self._source_graph = None
        self._queue: Queue = Queue()
        self._build()
        if source_text:
            self._seed_model_proposal(source_text)
        self.after(85, self._poll)

    def _build(self):
        frame = ttk.Frame(self, padding=11)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=2)
        frame.rowconfigure(5, weight=2)
        frame.rowconfigure(7, weight=3)

        ttk.Label(
            frame, wraplength=1100,
            text=(
                "Jeeves can propose original NEW project files and edits to EXISTING "
                "files. Combine those two independent strict JSON plans below, "
                "review the complete Git diff and SHA-256 hashes, then explicitly "
                "export a patch to a separate owner-private directory. "
                "No Git command runs, no source file changes, no network use."
            ),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        location = ttk.Frame(frame)
        location.grid(row=1, column=0, sticky="ew")
        location.columnconfigure(1, weight=1)
        ttk.Label(location, text="Original local source project root").grid(
            row=0, column=0, sticky="w",
        )
        ttk.Entry(location, textvariable=self.root_path).grid(
            row=0, column=1, sticky="ew", padx=6,
        )
        ttk.Button(
            location, text="Browse", command=self._browse_root,
        ).grid(row=0, column=2)

        labels = ttk.Frame(frame)
        labels.grid(row=2, column=0, sticky="ew", pady=(8, 3))
        labels.columnconfigure(0, weight=1)
        labels.columnconfigure(1, weight=1)
        ttk.Label(
            labels, text="NEW files (optional): jeeves.workspace.new-files.v1",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            labels, text="EXISTING edits (optional): jeeves.workspace.existing-file-edits.v1",
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        sources = ttk.Frame(frame)
        sources.grid(row=3, column=0, sticky="nsew")
        sources.columnconfigure(0, weight=1)
        sources.columnconfigure(1, weight=1)
        sources.rowconfigure(0, weight=1)
        self.new_text = ScrolledText(
            sources, height=8, wrap="none", undo=True,
        )
        self.new_text.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.existing_text = ScrolledText(
            sources, height=8, wrap="none", undo=True,
        )
        self.existing_text.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        for widget in (self.new_text, self.existing_text):
            widget.bind("<<Modified>>", self._edited)

        controls = ttk.Frame(frame)
        controls.grid(row=4, column=0, sticky="ew", pady=(9, 4))
        self.review_button = ttk.Button(
            controls, text="Review COMPLETE project diff",
            command=self._review,
        )
        self.review_button.pack(side="left")
        self.reset_button = ttk.Button(
            controls, text="Invalidate source review",
            command=self._invalidate,
        )
        self.reset_button.pack(side="left", padx=6)
        self.reconcile_button = ttk.Button(
            controls,
            text="Reconcile original edits after external changes",
            command=self._reconcile_changed_sources,
        )
        self.reconcile_button.pack(side="left", padx=6)
        ttk.Label(
            controls, text="Conflicts never overwrite source or carry prior approval.",
        ).pack(side="left", padx=12)

        self.files = ttk.Treeview(
            frame,
            columns=("path", "kind", "original", "replacement", "bytes"),
            show="headings", height=5,
        )
        for key, title, width in (
            ("path", "Relative source path", 330),
            ("kind", "Change", 85),
            ("original", "Original SHA-256", 235),
            ("replacement", "Replacement SHA-256", 235),
            ("bytes", "New bytes", 88),
        ):
            self.files.heading(key, text=title)
            self.files.column(key, width=width, stretch=key == "path")
        self.files.grid(row=5, column=0, sticky="nsew", pady=(4, 8))

        ttk.Label(
            frame, text="FULL patch for review — Git-compatible, inert text",
        ).grid(row=6, column=0, sticky="w")
        self.preview = ScrolledText(
            frame, height=10, wrap="none", state="disabled",
            font=("TkFixedFont", 10),
        )
        self.preview.grid(row=7, column=0, sticky="nsew", pady=(4, 8))

        approvals = ttk.LabelFrame(
            frame, text="Explicit full SHA-256 approval", padding=7,
        )
        approvals.grid(row=8, column=0, sticky="ew")
        approvals.columnconfigure(1, weight=1)
        ttk.Label(approvals, text="Source manifest SHA-256").grid(
            row=0, column=0, sticky="w",
        )
        ttk.Entry(
            approvals, textvariable=self.expected_manifest,
        ).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(approvals, text="Final Git patch SHA-256").grid(
            row=1, column=0, sticky="w",
        )
        ttk.Entry(
            approvals, textvariable=self.expected_patch,
        ).grid(row=1, column=1, sticky="ew", padx=6)
        self.export_button = ttk.Button(
            approvals, text="Export NEW private .patch only",
            command=self._export,
        )
        self.export_button.grid(row=0, column=2, padx=(6, 0))
        self.stage_button = ttk.Button(
            approvals,
            text="Stage reviewed SOURCE files privately",
            command=self._stage_sources,
        )
        self.stage_button.grid(row=1, column=2, padx=(6, 0), pady=(5, 0))

        destination = ttk.Frame(frame)
        destination.grid(row=9, column=0, sticky="ew", pady=(7, 0))
        destination.columnconfigure(1, weight=1)
        ttk.Label(destination, text="Export outside project, inside existing 0700 folder").grid(
            row=0, column=0, sticky="w",
        )
        ttk.Entry(destination, textvariable=self.export_path).grid(
            row=0, column=1, sticky="ew", padx=6,
        )
        ttk.Button(
            destination, text="Choose NEW .patch",
            command=self._choose_export,
        ).grid(row=0, column=2, padx=(0, 6))
        self.verify_button = ttk.Button(
            destination, text="Verify saved patch",
            command=self._verify_export,
        )
        self.verify_button.grid(row=0, column=3)
        self.verify_stage_button = ttk.Button(
            destination, text="Reverify private staged sources",
            command=self._verify_stage,
        )
        self.verify_stage_button.grid(row=1, column=3, pady=(5, 0), sticky="e")
        ttk.Label(
            destination, wraplength=880,
            text=(
                "Private stage: creates NEW owner-only directory with actual "
                "changed source files, canonical SHA manifest and final seal. "
                "It is NOT a runnable whole project and never changes checkout."
            ),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))

        capsule = ttk.LabelFrame(frame, text="Private selected-source capsule — no execution", padding=5)
        capsule.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        capsule.columnconfigure(1, weight=1)
        ttk.Label(capsule, text="Explicit original dependencies (one relative path per line)").grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.capsule_sources = ScrolledText(capsule, height=3, wrap="none")
        self.capsule_sources.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.capsule_sources.bind("<<Modified>>", self._capsule_edited)
        self.review_capsule_button = ttk.Button(capsule, text="Review selected-source capsule", command=self._review_capsule)
        self.review_capsule_button.grid(row=2, column=0, sticky="w")
        ttk.Label(capsule, text="Third full SHA-256").grid(row=3, column=0, sticky="w")
        ttk.Entry(capsule, textvariable=self.capsule_expected).grid(row=3, column=1, sticky="ew", padx=5)
        self.publish_capsule_button = ttk.Button(capsule, text="Publish NEW private capsule", command=self._publish_capsule)
        self.publish_capsule_button.grid(row=3, column=2)
        self.verify_capsule_button = ttk.Button(capsule, text="Reverify sealed capsule", command=self._verify_capsule)
        self.verify_capsule_button.grid(row=2, column=2, sticky="e")

        ttk.Label(
            frame, textvariable=self.status, wraplength=1130,
        ).grid(row=11, column=0, sticky="ew", pady=(7, 0))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=12, column=0, sticky="ew", pady=(7, 0))
        self._buttons()

    def _source_inputs(self):
        return (
            self.root_path.get(),
            self.new_text.get("1.0", "end-1c"),
            self.existing_text.get("1.0", "end-1c"),
        )

    def _seed_model_proposal(self, text: str):
        # This is only input organization, NOT proof a model is allowed to
        # write or a shortcut around the verified source proposal parsers.
        try:
            candidate = json.loads(text)
            schema = candidate.get("schema") if type(candidate) is dict else None
        except (ValueError, TypeError):
            schema = None
        if schema == MIXED_WORK_SCHEMA:
            try:
                mixed = parse_mixed_work(text)
            except (MixedWorkHold, ValueError):
                # Keep the exact invalid native bytes visible for the
                # normal strict reviewer; never sanitize and approve them.
                self.new_text.insert("1.0", text)
                self.new_text.edit_modified(False)
                return
            if mixed.new_plan() is not None:
                self.new_text.insert("1.0", mixed.new_plan())
            if mixed.edits_plan() is not None:
                self.existing_text.insert("1.0", mixed.edits_plan())
            self.new_text.edit_modified(False)
            self.existing_text.edit_modified(False)
            self.status.set(
                "Mixed native source-work split for INDEPENDENT original "
                "new-file and existing-file review; NO auto-export or "
                "model permission to modify source.",
            )
            return
        target = self.existing_text if schema == EDIT_SCHEMA else self.new_text
        target.insert("1.0", text)
        target.edit_modified(False)

    def _browse_root(self):
        if self._busy:
            return
        root = filedialog.askdirectory(
            parent=self, title="Select trusted original source project",
        )
        if root:
            self.root_path.set(root)
            self._invalidate()

    def _choose_export(self):
        if self._busy:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Choose NEW owner-private .patch file",
            defaultextension=".patch",
            filetypes=[("Inert reviewed Git patch", "*.patch")],
        )
        if path:
            self.export_path.set(path)

    def _preview(self, text: str):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _edited(self, _event=None):
        if (
            self.new_text.edit_modified()
            or self.existing_text.edit_modified()
        ):
            self.new_text.edit_modified(False)
            self.existing_text.edit_modified(False)
            if self._plan is not None and not self._busy:
                self._invalidate()

    def _invalidate(self):
        if self._busy:
            return
        self._epoch += 1
        self._plan = None
        self._reviewed_texts = None
        self._export_receipt = None
        self._stage_receipt = None
        self._stage_path = None
        self._qualification = None
        self._source_graph = None
        self.expected_manifest.set("")
        self.expected_patch.set("")
        self._capsule_plan = None
        self._capsule_source_selection = None
        self._capsule_receipt = None
        self._capsule_path = None
        if hasattr(self, "capsule_expected"):
            self.capsule_expected.set("")
        for item in self.files.get_children():
            self.files.delete(item)
        self._preview("")
        self.status.set(
            "Review invalidated: re-read all original project bytes, then "
            "confirm both full SHA-256 values again",
        )
        self._buttons()

    def _buttons(self):
        self.review_button.configure(state="disabled" if self._busy else "normal")
        self.reset_button.configure(state="disabled" if self._busy else "normal")
        self.reconcile_button.configure(
            state="normal" if not self._busy and self._plan is not None
            else "disabled",
        )
        self.export_button.configure(
            state="normal" if (
                not self._busy and self._plan is not None
                and self._qualification is not None
                and self._qualification.permits_inert_export
                and self._source_graph is not None
                and self._source_graph.permits_inert_export
            ) else "disabled",
        )
        self.verify_button.configure(
            state="normal" if not self._busy and self._export_receipt is not None
            else "disabled",
        )
        self.stage_button.configure(
            state="normal" if (
                not self._busy and self._plan is not None
                and self._qualification is not None
                and self._qualification.permits_inert_export
                and self._source_graph is not None
                and self._source_graph.permits_inert_export
            ) else "disabled",
        )
        self.verify_stage_button.configure(
            state="normal" if (
                not self._busy and self._stage_receipt is not None
                and self._stage_path is not None
            ) else "disabled",
        )
        if hasattr(self, "review_capsule_button"):
            eligible = (
                not self._busy and self._plan is not None
                and self._qualification is not None and self._qualification.permits_inert_export
                and self._source_graph is not None and self._source_graph.permits_inert_export
            )
            self.review_capsule_button.configure(state="normal" if eligible else "disabled")
            self.publish_capsule_button.configure(
                state="normal" if eligible and self._capsule_plan is not None else "disabled")
            self.verify_capsule_button.configure(state="normal" if (
                not self._busy and self._capsule_receipt is not None
                and self._capsule_path is not None and self._capsule_plan is not None
            ) else "disabled")

    def _capsule_selected(self):
        return self.capsule_sources.get("1.0", "end-1c")

    def _capsule_edited(self, _event=None):
        if not self.capsule_sources.edit_modified():
            return
        self.capsule_sources.edit_modified(False)
        if self._busy:
            return
        self._capsule_plan = None
        self._capsule_source_selection = None
        self._capsule_receipt = None
        self._capsule_path = None
        self.capsule_expected.set("")
        self.status.set("Dependency selection changed. Independent capsule review and approval required.")
        self._buttons()

    def _review_capsule(self):
        plan = self._plan
        if (self._busy or plan is None or self._qualification is None
                or not self._qualification.permits_inert_export
                or self._source_graph is None or not self._source_graph.permits_inert_export):
            return
        if self._reviewed_texts != self._source_inputs():
            self._invalidate()
            return
        selection = self._capsule_selected()
        self._capsule_plan = None
        self._capsule_source_selection = None
        self._capsule_receipt = None
        self._capsule_path = None
        self.capsule_expected.set("")
        epoch = self._epoch
        self._busy = True
        self.progress.start(85)
        self.status.set("Reading explicitly selected original sources and custody closure; no files written.")
        self._buttons()

        def work():
            try:
                reviewed = prepare_private_capsule(plan, selection)
                self._queue.put(("capsule-reviewed", epoch, selection, reviewed, reviewed.public_review()))
            except Exception as exc:
                self._queue.put(("capsule-held", epoch, selection, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _publish_capsule(self):
        plan = self._capsule_plan
        if (self._busy or plan is None or self._plan is None
                or self._qualification is None or not self._qualification.permits_inert_export
                or self._source_graph is None or not self._source_graph.permits_inert_export):
            return
        selection = self._capsule_selected()
        inputs = self._source_inputs()
        if (self._reviewed_texts != inputs or selection != self._capsule_source_selection
                or plan.patch is not self._plan):
            self._invalidate()
            return
        digests = (plan.patch.manifest_sha256, plan.patch.patch_sha256, plan.capsule_sha256)
        if (self.expected_manifest.get(), self.expected_patch.get(), self.capsule_expected.get()) != digests:
            self.status.set("Type all THREE full reviewed SHA-256 values exactly before publication.")
            return
        parent = filedialog.askdirectory(parent=self, title="Choose existing private folder OUTSIDE original project")
        if not parent:
            return
        name = simpledialog.askstring("New private capsule", "Name a NEW folder (no existing files overwritten).", parent=self)
        if not name:
            return
        if name in (".", "..") or Path(name).name != name or "/" in name or "\\" in name:
            self.status.set("Choose a single new private folder name.")
            return
        destination = str(Path(parent) / name)
        if not messagebox.askyesno(
            "Publish private selected-source capsule?",
            "Write explicitly reviewed original dependencies and changed sources into a NEW owner-private folder. "
            "No execution, Git operations, checkout changes, release or complete-project certification. Continue?",
            parent=self,
        ):
            return
        # A Tk modal dialog can process edits or callbacks. Recheck the same
        # reviewed source selection and approvals after the dialog returns.
        if (self._busy or self._plan is not plan.patch or self._capsule_plan is not plan
                or self._source_inputs() != inputs or self._capsule_selected() != selection
                or (self.expected_manifest.get(), self.expected_patch.get(), self.capsule_expected.get()) != digests):
            self.status.set("Review or approval changed during confirmation; nothing published.")
            return
        epoch = self._epoch
        self._busy = True
        self.progress.start(85)
        self._buttons()
        self.status.set("Revalidating sources and publishing private no-clobber capsule; seal written last.")

        def work():
            try:
                receipt = publish_private_capsule(
                    plan, destination,
                    expected_capsule_sha256=digests[2],
                    expected_manifest_sha256=digests[0],
                    expected_patch_sha256=digests[1],
                    approve_private_capsule=True,
                )
                self._queue.put(("capsule-published", epoch, destination, receipt))
            except Exception as exc:
                self._queue.put(("capsule-held", epoch, destination, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _verify_capsule(self):
        plan = self._capsule_plan
        receipt = self._capsule_receipt
        path = self._capsule_path
        if self._busy or plan is None or receipt is None or not path:
            return
        seal = receipt.get("seal_sha256")
        if not isinstance(seal, str) or len(seal) != 64 or any(c not in "0123456789abcdef" for c in seal):
            self.status.set("A complete independently recorded capsule seal is required.")
            return
        epoch = self._epoch
        self._busy = True
        self.progress.start(85)
        self._buttons()
        self.status.set("Cold verifying sealed inert files; no model call or source execution.")

        def work():
            try:
                result = verify_private_capsule(
                    path, original_project_root=plan.patch.root,
                    expected_capsule_sha256=plan.capsule_sha256,
                    expected_seal_sha256=seal,
                )
                self._queue.put(("capsule-verified", epoch, path, result))
            except Exception as exc:
                self._queue.put(("capsule-held", epoch, path, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _review(self):
        if self._busy:
            return
        self._invalidate()
        values = self._source_inputs()
        epoch = self._epoch
        self._busy = True
        self.status.set("Reading real source hashes and constructing exact Git patch…")
        self.progress.start(85)
        self._buttons()

        def work():
            try:
                root, additions, edits = values
                plan = review_patch_bundle(
                    root, new_files=additions, existing_edits=edits,
                )
                diff = get_reviewed_patch(plan)
                qualification = qualify_patch_sources(plan)
                graph = analyze_python_source_graph(plan)
                self._queue.put((
                    "reviewed", epoch, values, plan, diff, qualification, graph,
                ))
            except BaseException as exc:
                self._queue.put(("held", epoch, values, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _reconcile_changed_sources(self):
        # Changed real source cannot be silently accepted, merged or applied
        # by the model. Only a new original-source proposal can be produced;
        # fresh complete patch review and digest approval remain mandatory.
        plan = self._plan
        if self._busy or plan is None:
            return
        original_inputs = self._source_inputs()
        if original_inputs != self._reviewed_texts:
            self._invalidate()
            return
        self._busy = True
        epoch = self._epoch
        self.status.set(
            "Inspecting current source drift; only independent line changes "
            "may become a NEW reviewed proposal…",
        )
        self.progress.start(85)
        self._buttons()

        def work():
            try:
                outcome = reconcile_reviewed_patch(plan)
                self._queue.put((
                    "reconciled", epoch, original_inputs, outcome,
                ))
            except BaseException as exc:
                self._queue.put((
                    "reconcile-held", epoch, original_inputs,
                    type(exc).__name__,
                ))

        threading.Thread(target=work, daemon=True).start()

    def _export(self):
        plan = self._plan
        if (
            self._busy or plan is None or self._qualification is None
            or not self._qualification.permits_inert_export
            or self._source_graph is None
            or not self._source_graph.permits_inert_export
        ):
            return
        if self._reviewed_texts != self._source_inputs():
            self._invalidate()
            return
        if (
            self.expected_manifest.get() != plan.manifest_sha256
            or self.expected_patch.get() != plan.patch_sha256
        ):
            self.status.set("Type BOTH original full SHA-256 digests exactly")
            return
        destination = self.export_path.get()
        if not messagebox.askyesno(
            "Export original inert patch only?",
            "This creates a NEW 0600 private Git patch outside your source "
            "tree. It does NOT apply the patch, run shell commands, or "
            "commit changes. Never export into .git, a shared folder, "
            "or any source project. Continue?",
            parent=self,
        ):
            return
        self._busy = True
        self.progress.start(85)
        self.status.set(
            "Rechecking every original SHA and exporting one no-overwrite patch…",
        )
        self._buttons()
        epoch = self._epoch
        manifest = plan.manifest_sha256
        patch_digest = plan.patch_sha256

        def work():
            try:
                result = export_reviewed_patch(
                    plan, destination,
                    expected_manifest_sha256=manifest,
                    expected_patch_sha256=patch_digest,
                    approve_export=True,
                )
                self._queue.put(("exported", epoch, destination, result))
            except BaseException as exc:
                self._queue.put(("export-held", epoch, destination, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _stage_sources(self):
        plan = self._plan
        if (
            self._busy or plan is None or self._qualification is None
            or not self._qualification.permits_inert_export
            or self._source_graph is None
            or not self._source_graph.permits_inert_export
        ):
            return
        if self._reviewed_texts != self._source_inputs():
            self._invalidate()
            return
        if (
            self.expected_manifest.get() != plan.manifest_sha256
            or self.expected_patch.get() != plan.patch_sha256
        ):
            self.status.set(
                "Type BOTH original SHA-256 values before staging source bytes",
            )
            return
        parent = filedialog.askdirectory(
            parent=self,
            title="Choose EXISTING owner-private directory OUTSIDE original project",
        )
        if not parent:
            return
        name = simpledialog.askstring(
            "New source overlay directory",
            "Enter a NEW private folder name for the exact changed source files. "
            "An existing folder will NEVER be used or overwritten.",
            parent=self,
        )
        if not name:
            return
        destination = str(Path(parent) / name)
        if not messagebox.askyesno(
            "Stage actual revised source files?",
            "Create a NEW 0700 owner-private preview directory outside the "
            "source project, with exact reviewed replacement bytes at 0600. "
            "An incomplete stage can remain if storage fails. NO original "
            "files, Git index, model tool grants, or executables are changed. "
            "The new tree is not a runnable complete checkout. Continue?",
            parent=self,
        ):
            return
        epoch = self._epoch
        manifest = plan.manifest_sha256
        patch_digest = plan.patch_sha256
        self._busy = True
        self.progress.start(85)
        self._buttons()
        self.status.set(
            "Staging privately under no-follow descriptors after source "
            "and syntax recheck; complete seal written LAST…",
        )

        def work():
            try:
                receipt = stage_reviewed_overlay(
                    plan, destination,
                    expected_manifest_sha256=manifest,
                    expected_patch_sha256=patch_digest,
                    approve_staging=True,
                )
                self._queue.put(("staged", epoch, destination, receipt))
            except BaseException as exc:
                self._queue.put((
                    "stage-held", epoch, destination, type(exc).__name__,
                ))

        threading.Thread(target=work, daemon=True).start()

    def _verify_stage(self):
        if (
            self._busy or self._stage_path is None
            or self._stage_receipt is None or self._plan is None
        ):
            return
        epoch = self._epoch
        path = self._stage_path
        plan = self._plan
        self._busy = True
        self.progress.start(85)
        self._buttons()
        self.status.set("Reopening owner-private completed source overlay…")

        def work():
            try:
                receipt = verify_staged_overlay(
                    path, expected_manifest_sha256=plan.manifest_sha256,
                    expected_patch_sha256=plan.patch_sha256,
                    workspace_root=plan.root,
                )
                self._queue.put(("stage-verified", epoch, path, receipt))
            except BaseException as exc:
                self._queue.put((
                    "stage-held", epoch, path, type(exc).__name__,
                ))

        threading.Thread(target=work, daemon=True).start()

    def _verify_export(self):
        receipt = self._export_receipt
        plan = self._plan
        if self._busy or receipt is None or plan is None:
            return
        source = self.export_path.get()
        if not source:
            return
        self._busy = True
        epoch = self._epoch
        self.progress.start(80)
        self._buttons()

        def work():
            try:
                result = verify_saved_patch(
                    source, expected_patch_sha256=plan.patch_sha256,
                    expected_bytes=plan.patch_bytes, workspace_root=plan.root,
                )
                self._queue.put(("verified", epoch, source, result))
            except BaseException as exc:
                self._queue.put(("verify-held", epoch, source, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                message = self._queue.get_nowait()
                kind, epoch = message[0], message[1]
                if epoch != self._epoch:
                    continue
                self._busy = False
                self.progress.stop()
                if kind == "reviewed":
                    _, _, inputs, plan, patch, qualification, graph = message
                    if inputs != self._source_inputs():
                        self.status.set(
                            "Source inputs changed during review. Re-review required.",
                        )
                        self._buttons()
                        continue
                    self._plan = plan
                    self._qualification = qualification
                    self._source_graph = graph
                    self._reviewed_texts = inputs
                    for index, item in enumerate(plan.entries):
                        self.files.insert(
                            "", "end", iid=str(index),
                            values=(
                                item.path, item.kind, item.original_sha256 or "-",
                                item.replacement_sha256, item.replacement_bytes,
                            ),
                        )
                    self._preview(patch.decode("utf-8", "strict"))
                    report = qualification.to_public()
                    issues = [
                        issue["code"] + "@" + str(issue["line"] or "?")
                        + ":" + str(issue["column"] or "?")
                        + " in " + info["path"]
                        for info in report["files"]
                        for issue in info["issues"]
                    ]
                    self.status.set(
                        "COMPLETE source review · "
                        + str(len(plan.entries)) + " changes / "
                        + str(plan.patch_bytes) + " bytes · "
                        + "STRUCTURAL: " + report["status"]
                        + " · clean " + str(report["parse_clean_count"])
                        + " / unverified " + str(report["unverified_count"])
                        + " / held " + str(report["syntax_held_count"])
                        + (" · " + "; ".join(issues[:3]) if issues else "")
                        + " · PYTHON GRAPH " + graph.status
                        + " / linked " + str(graph.linked_import_count)
                        + " / unverified " + str(graph.unverified_import_count)
                        + " / invalid relatives " + str(graph.invalid_relative_count)
                        + " / observed cycles " + str(len(graph.cycles))
                        + " · GRAPH SHA " + graph.graph_sha256
                        + " · MANIFEST " + plan.manifest_sha256
                        + " · PATCH " + plan.patch_sha256,
                    )
                elif kind == "capsule-reviewed":
                    _, _, selection, plan, report = message
                    if (selection != self._capsule_selected()
                            or self._reviewed_texts != self._source_inputs()
                            or self._plan is not plan.patch):
                        self._capsule_plan = None
                        self._capsule_source_selection = None
                        self.capsule_expected.set("")
                        self.status.set("Capsule review became stale; review again before publication.")
                        self._buttons()
                        continue
                    self._capsule_plan = plan
                    self._capsule_source_selection = selection
                    self.capsule_expected.set("")
                    self.status.set(
                        "REVIEW ONLY · capsule SHA " + plan.capsule_sha256
                        + " · " + str(len(plan.originals)) + " selected originals · "
                        + str(plan.total_bytes) + " bytes · closure "
                        + str(report["selected_python_closure_status"])
                        + " · unresolved imports " + str(report["unverified_external_or_unselected_imports"])
                        + " · closure SHA " + str(report["python_closure_sha256"])
                        + " · type third SHA and confirm separately; not a complete project."
                    )
                elif kind == "capsule-published":
                    _, _, destination, receipt = message
                    self._capsule_receipt = receipt
                    self._capsule_path = destination
                    self.status.set("Private inert capsule published at " + destination
                                    + " · seal SHA " + str(receipt["seal_sha256"])
                                    + " · no code executed; verify before separate use.")
                elif kind == "capsule-verified":
                    self.status.set("Cold capsule verified: " + str(message[3]["file_count"])
                                    + " sealed files · no execution or release certification.")
                elif kind == "capsule-held":
                    self.status.set("Private capsule held: " + str(message[-1])
                                    + " · inspect possible incomplete destination; no automatic retry.")
                elif kind == "reconciled":
                    _, _, original_inputs, report = message
                    if original_inputs != self._source_inputs():
                        self._invalidate()
                        self.status.set(
                            "Proposal changed during reconciliation; "
                            "re-review original sources before any export.",
                        )
                        continue
                    public = report.to_public()
                    if report.status == "rebased-review-required":
                        # This replaces only the source *proposal panes*,
                        # never files in the project, the native model, or
                        # the user's Git index. Old digest approval is
                        # invalidated before any new review.
                        self._invalidate()
                        self.new_text.delete("1.0", "end")
                        self.existing_text.delete("1.0", "end")
                        if report.new_proposal is not None:
                            self.new_text.insert("1.0", report.new_proposal)
                        if report.existing_proposal is not None:
                            self.existing_text.insert(
                                "1.0", report.existing_proposal,
                            )
                        self.new_text.edit_modified(False)
                        self.existing_text.edit_modified(False)
                        self.status.set(
                            "NEW SOURCE PROPOSAL ONLY · "
                            + str(public["rebased_count"])
                            + " nonoverlapping model edits reconciled · "
                            + str(public["already_present_count"])
                            + " already present · RE-REVIEW and re-approve "
                            + "fresh manifest/patch SHA-256 before export · "
                            + report.rebase_sha256,
                        )
                    else:
                        conflicts = [
                            f["path"] for f in public["files"]
                            if f["status"] in (
                                "conflict", "new-path-collision",
                            )
                        ]
                        self.status.set(
                            "RECONCILIATION HELD: " + report.status
                            + " · " + str(public["conflict_count"])
                            + " conflicting source paths · "
                            + ", ".join(conflicts[:3])
                            + " · NO auto-merge; original proposal untouched.",
                        )
                elif kind == "reconcile-held":
                    self.status.set(
                        "Source reconciliation refused: " + str(message[-1])
                        + " · originals untouched; re-review manually.",
                    )
                elif kind == "exported":
                    _, _, destination, result = message
                    if destination != self.export_path.get():
                        self.status.set("Export destination changed: inspect manually")
                    else:
                        self._export_receipt = result
                        self.status.set(
                            "NEW private inert patch exported · SHA-256 "
                            + str(result["patch_sha256"])
                            + " · " + str(result["file_count"]) + " source changes"
                            + " · static " + str(result["static_source_status"])
                            + " / unknown " + str(result["unverified_source_count"])
                            + ". Apply only after separate Git source-review, "
                            + "git apply --check and operator authorization.",
                        )
                elif kind == "staged":
                    self._stage_path = message[2]
                    self._stage_receipt = message[3]
                    self.status.set(
                        "PRIVATE source files STAGED, NOT applied · "
                        + str(message[3]["file_count"]) + " exact outputs in "
                        + self._stage_path
                        + " · seal verified · source SHA "
                        + str(message[3]["manifest_sha256"])
                        + " · no code executed or checkout changes. "
                        + "Inspect the private folder manually.",
                    )
                elif kind == "stage-verified":
                    self.status.set(
                        "COLD RECHECK: " + str(message[3]["file_count"])
                        + " staged source files verified at "
                        + str(message[2])
                        + " · complete seal and hashes intact · no execution.",
                    )
                elif kind == "verified":
                    self.status.set(
                        "Saved patch bytes independently rechecked: "
                        + str(message[3]["patch_sha256"])
                        + " · no source modifications or Git execution",
                    )
                else:
                    self.status.set(
                        "Original source patch held: " + str(message[-1])
                        + " · no auto-retry, no source changes.",
                    )
                self._buttons()
        except Empty:
            pass
        self.after(85, self._poll)

    def _exit(self):
        if self._busy:
            self.status.set(
                "Source/export still in flight; closing now could hide "
                "an uncertain private file. Inspect the result before closing.",
            )
            return
        self._closed = True
        self.destroy()


__all__ = ["PortablePatchWindow"]
