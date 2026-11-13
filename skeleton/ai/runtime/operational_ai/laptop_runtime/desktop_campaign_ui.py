"""Private Tk workbench for native coding campaigns and merged source delivery.

Only exact operator request JSON and output receipt metadata occupy this GUI.
Time-consuming source/model work runs in ONE background thread per action.
No automatic retry, approval bypass, hidden model requests, generated code
execution or source checkout writes. The existing local GGUF/SQLite owner
still performs all native effects and private source custody.
"""
from __future__ import annotations

import json
from queue import Queue, Empty
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from .desktop_campaign_operator import (
    NativeCampaignOperator, NativeCampaignOperatorHold,
)

MAX_VISIBLE_RESULT = 32768


class NativeCampaignWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Jeeves — Real Local Native Coding Campaigns")
        self.geometry("1040x850")
        self.minsize(850, 700)
        self._owner = parent
        self._operator = NativeCampaignOperator()
        self._queue: Queue = Queue()
        self._busy = False
        self._closing = False
        self._epoch = 0
        self._worker: threading.Thread | None = None
        self._composer = None  # Exactly one private goal-to-campaign preview.
        self.status = tk.StringVar(value=(
            "Paste the original inspected campaign JSON. No model starts during review."
        ))
        self.typed_manifest = tk.StringVar(value="")
        self.grant_campaign = tk.BooleanVar(value=False)
        self.grant_native = tk.BooleanVar(value=False)
        self.grant_private_storage = tk.BooleanVar(value=False)
        self.verify_original = tk.BooleanVar(value=True)
        self.stage_destination = tk.StringVar(value="")
        self.assembly_sha256 = tk.StringVar(value="")
        self.source_manifest_sha256 = tk.StringVar(value="")
        self.patch_sha256 = tk.StringVar(value="")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._pump)

    def _build(self):
        content = ttk.Frame(self, padding=10)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)

        ttk.Label(content, text=(
            "Native campaign: inspected source → real GGUF + SQLite → "
            "owner-private escrows → reviewed integrated source"
        )).grid(row=0, column=0, sticky="w")
        ttk.Label(content, text=(
            "The model never receives write/Git tools. Only approve SHA values "
            "after reviewing every original source goal and private target."
        )).grid(row=1, column=0, sticky="w", pady=(3, 5))

        request = ttk.LabelFrame(content, text="Private original campaign JSON (not sent to network)", padding=6)
        request.grid(row=2, column=0, sticky="nsew")
        request.columnconfigure(0, weight=1)
        self.original_json = ScrolledText(
            request, wrap="none", height=12, font=("TkFixedFont", 9), undo=True,
        )
        self.original_json.grid(row=0, column=0, sticky="nsew")
        self.original_json.bind("<<Modified>>", self._edited)
        request.rowconfigure(0, weight=1)
        content.rowconfigure(2, weight=2)

        phase_one = ttk.LabelFrame(content, text="1 — Source and resource inspection", padding=7)
        phase_one.grid(row=3, column=0, sticky="ew", pady=(7, 4))
        phase_one.columnconfigure(1, weight=1)
        self.inspect_button = ttk.Button(
            phase_one, text="Inspect ORIGINAL campaign (no model)",
            command=lambda: self._dispatch("inspect"),
        )
        self.inspect_button.grid(row=0, column=0, sticky="w")
        self.compose_button = ttk.Button(
            phase_one, text="Compose tasks from original goals",
            command=self._compose,
        )
        self.compose_button.grid(row=0, column=1, sticky="w", padx=9)
        ttk.Label(phase_one, text="Type FULL reviewed campaign SHA-256").grid(
            row=1, column=0, sticky="w", pady=(4, 0),
        )
        ttk.Entry(
            phase_one, textvariable=self.typed_manifest, width=71,
        ).grid(row=1, column=1, sticky="ew", padx=5, pady=(4, 0))

        phase_two = ttk.LabelFrame(content, text="2 — Explicit native GGUF/SQLite source generation", padding=7)
        phase_two.grid(row=4, column=0, sticky="ew", pady=(5, 4))
        ttk.Checkbutton(
            phase_two, text="I approved the full unchanged task manifest",
            variable=self.grant_campaign,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            phase_two, text="I approve the actual installed local GGUF model and SQLite requests",
            variable=self.grant_native,
        ).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(
            phase_two, text="I approve new no-clobber owner-private source escrow files",
            variable=self.grant_private_storage,
        ).grid(row=2, column=0, sticky="w")
        self.run_button = ttk.Button(
            phase_two, text="RUN one approved native campaign (NO RETRY)",
            command=lambda: self._dispatch("run"),
        )
        self.run_button.grid(row=3, column=0, sticky="w", pady=(4, 0))

        phase_three = ttk.LabelFrame(content, text="3 — Cold original-source and aggregate-patch proof", padding=7)
        phase_three.grid(row=5, column=0, sticky="ew", pady=(5, 4))
        self.verify_button = ttk.Button(
            phase_three, text="Cold verify saved SQLite/source receipts",
            command=lambda: self._dispatch("verify"),
        )
        self.verify_button.grid(row=0, column=0, padx=3)
        ttk.Checkbutton(
            phase_three, text="Also recheck the current original project sources",
            variable=self.verify_original,
        ).grid(row=0, column=1, padx=6)
        self.assembly_button = ttk.Button(
            phase_three, text="Inspect ONE cross-task reviewed source patch",
            command=lambda: self._dispatch("assembly"),
        )
        self.assembly_button.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        phase_four = ttk.LabelFrame(content, text="4 — Separate human-approved PRIVATE publication", padding=7)
        phase_four.grid(row=6, column=0, sticky="ew", pady=(5, 4))
        phase_four.columnconfigure(1, weight=1)
        for row, (name, variable) in enumerate((
            ("New private output path", self.stage_destination),
            ("Type full assembly SHA", self.assembly_sha256),
            ("Type combined original manifest SHA", self.source_manifest_sha256),
            ("Type complete Git patch SHA", self.patch_sha256),
        )):
            ttk.Label(phase_four, text=name).grid(row=row, column=0, sticky="w")
            ttk.Entry(phase_four, textvariable=variable).grid(
                row=row, column=1, sticky="ew", padx=5, pady=2,
            )
        self.stage_button = ttk.Button(
            phase_four, text="Approve NEW private source stage",
            command=lambda: self._dispatch("private-stage"),
        )
        self.stage_button.grid(row=4, column=0, sticky="w", pady=(5, 0))
        self.patch_button = ttk.Button(
            phase_four, text="Approve NEW inert Git patch",
            command=lambda: self._dispatch("git-patch"),
        )
        self.patch_button.grid(row=4, column=1, sticky="w", pady=(5, 0))

        receipt = ttk.LabelFrame(content, text="SHA receipts (never original model source bytes)", padding=6)
        receipt.grid(row=7, column=0, sticky="nsew", pady=(7, 4))
        receipt.columnconfigure(0, weight=1)
        receipt.rowconfigure(0, weight=1)
        self.output = ScrolledText(
            receipt, wrap="word", height=8, state="disabled",
            font=("TkFixedFont", 9),
        )
        self.output.grid(row=0, column=0, sticky="nsew")
        content.rowconfigure(7, weight=1)
        ttk.Label(content, textvariable=self.status, wraplength=980).grid(
            row=8, column=0, sticky="w", pady=(5, 0),
        )

    def _compose(self):
        if self._busy or self._closing or self._operator.native_launch_consumed:
            self.status.set(
                "Native campaign may already have committed; do not rearm "
                "task planning in this operator window.",
            )
            return
        if self._composer is not None:
            self._composer.lift()
            self._composer.focus_set()
            return
        from .desktop_campaign_composer_ui import NativeCampaignComposerWindow
        self._composer = NativeCampaignComposerWindow(self)

    def _edited(self, _event=None):
        self.original_json.edit_modified(False)
        if not self._busy:
            # RAM review is kept, but run will independently verify exact
            # canonical original source bytes, not the UI text label.
            self.status.set("Source JSON edited. Re-inspect if its content changed; prior SHA is not transferable.")

    def _original(self) -> bytes:
        return self.original_json.get("1.0", "end-1c").encode("utf-8", "strict")

    def _native_owner_available(self) -> bool:
        bridge = getattr(self._owner, "_bridge", None)
        connecting = getattr(self._owner, "_connecting", None)
        return (
            not bool(getattr(bridge, "connected", False))
            and not bool(getattr(connecting, "connected", False))
            and not bool(getattr(self._owner, "_busy", False))
        )

    def _dispatch(self, action: str) -> None:
        if self._busy or self._closing:
            return
        if self._composer is not None and getattr(self._composer, "_busy", False):
            self.status.set("Finish current original source task inspection first.")
            return
        try:
            raw = self._original()
            payload = {}
            if action == "run":
                if not self._native_owner_available():
                    raise NativeCampaignOperatorHold(
                        "disconnect the active chat GGUF worker before running an additional source campaign",
                    )
                payload = {
                    "typed_manifest_sha256": self.typed_manifest.get(),
                    "approve_campaign": self.grant_campaign.get(),
                    "approve_native": self.grant_native.get(),
                    "approve_private_storage": self.grant_private_storage.get(),
                }
                if not messagebox.askyesno(
                    "Begin real native GGUF work?",
                    "Each task can commit to canonical private SQLite. "
                    "An uncertain or interrupted request must NEVER be automatically retried. "
                    "Have you reviewed the exact FULL task and resource SHA?",
                    parent=self,
                ):
                    return
            elif action == "verify":
                payload = {"recheck_original": self.verify_original.get()}
            elif action in ("git-patch", "private-stage"):
                payload = {
                    "destination": self.stage_destination.get(),
                    "output_kind": action,
                    "assembly_sha256": self.assembly_sha256.get(),
                    "source_manifest_sha256": self.source_manifest_sha256.get(),
                    "patch_sha256": self.patch_sha256.get(),
                    "approve_private_stage": action == "private-stage",
                    "approve_git_patch": action == "git-patch",
                }
                if not messagebox.askyesno(
                    "Publish reviewed source to a NEW private output?",
                    "This publishes inert source data to a new owner-private location. "
                    "It never applies Git, executes model code or changes the original checkout. "
                    "Confirm the exact THREE full SHA-256 approvals.",
                    parent=self,
                ):
                    return
        except (Exception, UnicodeError):
            self.status.set("Original source/approval is malformed; no action started.")
            return
        self._busy = True
        self._epoch += 1
        epoch = self._epoch
        self.original_json.configure(state="disabled")
        self._controls()
        self.status.set(action + " in progress — no automatic retry or source write.")
        worker = threading.Thread(
            target=self._run_worker, args=(epoch, action, raw, payload),
            daemon=True,
        )
        self._worker = worker
        worker.start()

    def _controls(self):
        state = "disabled" if self._busy else "normal"
        for button in (
            self.compose_button, self.inspect_button, self.run_button, self.verify_button,
            self.assembly_button, self.stage_button, self.patch_button,
        ):
            button.configure(state=state)

    def _run_worker(self, epoch: int, action: str, raw: bytes, payload: dict):
        try:
            if action == "inspect":
                result = self._operator.inspect(raw)
            elif action == "run":
                result = self._operator.run(raw, **payload)
            elif action == "verify":
                result = self._operator.verify(raw, **payload)
            elif action == "assembly":
                result = self._operator.inspect_assembly(raw)
            elif action in ("git-patch", "private-stage"):
                result = self._operator.publish(raw, **payload)
            else:
                raise NativeCampaignOperatorHold("unknown operator campaign action")
            text = json.dumps(
                result, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False,
            )
            if len(text) > MAX_VISIBLE_RESULT:
                raise NativeCampaignOperatorHold("public receipt exceeds local display bound")
            self._queue.put((epoch, action, "success", text))
        except (Exception, KeyboardInterrupt):
            # The model might have committed to canonical SQLite. Do not
            # expose source/paths/stack traces to Tk status or re-arm run.
            self._queue.put((epoch, action, "held", ""))

    def _pump(self):
        if self._closing:
            return
        try:
            while True:
                epoch, action, kind, payload = self._queue.get_nowait()
                if epoch != self._epoch:
                    continue
                self._busy = False
                self.original_json.configure(state="normal")
                self._controls()
                if kind == "success":
                    self.output.configure(state="normal")
                    self.output.delete("1.0", "end")
                    self.output.insert("end", payload)
                    self.output.configure(state="disabled")
                    if action == "inspect":
                        self.status.set(
                            "READ-ONLY campaign reviewed. Type the exact manifest SHA, "
                            "check all separate grants and approve any native run manually.",
                        )
                    elif action == "assembly":
                        self.status.set(
                            "Multi-task source reviewed. Type ALL THREE combined SHA "
                            "values to publish one NEW private stage or inert patch.",
                        )
                    else:
                        self.status.set(
                            action + " finished. Read the exact status receipt: "
                            "no code executed, no implicit retry or release approval.",
                        )
                else:
                    self.status.set(
                        action + " HELD. Private native SQLite or source publication MAY "
                        "be uncertain; inspect journal/SQLite manually. No automatic retry.",
                    )
        except Empty:
            pass
        self.after(100, self._pump)

    def _close(self):
        if self._composer is not None and getattr(self._composer, "_busy", False):
            messagebox.showwarning(
                "Original source task composition active",
                "The private source snapshot is in progress. It cannot be "
                "silently adopted or discarded as a native approval.",
                parent=self,
            )
            return
        if self._busy:
            messagebox.showwarning(
                "Native work still in progress",
                "An original SQLite native request may have committed. "
                "Keep this window open to view its bounded receipt; "
                "do not reissue the same campaign.",
                parent=self,
            )
            return
        if self._composer is not None:
            self._composer._close()
        self._closing = True
        self._epoch += 1
        self._operator.reset()
        if getattr(self._owner, "_native_campaign_window", None) is self:
            self._owner._native_campaign_window = None
        self.destroy()


__all__ = ["NativeCampaignWindow"]
