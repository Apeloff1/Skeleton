"""Private goal-to-native-campaign composer for the existing Jeeves desktop.

The owner enters original task goals, source selections, dependency order and
output names. Read-only source snapshot and native-job hashing run in a
separate thread without GGUF inference, Git changes or project writes.
The finished PRIVATE campaign request is inserted only into the owning
workbench's editable operator field, never stdout or network telemetry.
"""
from __future__ import annotations

import json
from queue import Queue, Empty
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_campaign_composer import compose_campaign
from .desktop_workspace import _canonical

MAX_COMPOSER_DISPLAY_BYTES = 131072


def default_composer_template(parent) -> str:
    """Populate harmless initial model bounds, never guess private paths."""
    fields = parent.fields
    def numeric(name: str, default: int) -> int:
        try:
            return int(fields[name].get().strip())
        except (KeyError, ValueError, AttributeError):
            return default

    def field(name: str, default: str) -> str:
        try:
            return fields[name].get().strip()
        except (KeyError, AttributeError):
            return default

    request = {
        "schema": "jeeves.desktop.native-source-campaign-composer.v1",
        "project_root": "",
        "private_dir": "",
        "journal_name": "original-work.jeeves-campaign.jsonl",
        "model_root": field("model_root", ""),
        "state_dir": field("state_dir", ""),
        "tenant": field("tenant", "local"),
        "subject": field("subject", "owner"),
        "context_tokens": numeric("context", 4096),
        "max_output_tokens": numeric("max_output_tokens", 1024),
        "threads": numeric("threads", 4),
        "gpu_layers": numeric("gpu_layers", 0),
        "inference_ms": numeric("inference_ms", 90000),
        "capacity_budget_bytes": numeric("capacity_budget_bytes", 8000000000),
        "tasks": [{
            "task_id": "module-one",
            "depends_on": [],
            "goal": "Author one original, complete Python source module for this project",
            "format": "new-files",
            "maximum_attempts": 2,
            "source_paths": [],
            "target_name": "module-one.source.json",
        }],
    }
    return json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True)


class NativeCampaignComposerWindow(tk.Toplevel):
    """Separate local task-planning surface; no new model or state authority."""

    def __init__(self, parent):
        super().__init__(parent)
        self._campaign = parent
        self._queue = Queue()
        self._epoch = 0
        self._busy = False
        self._closing = False
        self.status = tk.StringVar(
            value="Edit task goals, source files and owner-private paths. No model runs.",
        )
        self.title("Jeeves — Compose Original Native Coding Tasks")
        self.geometry("940x760")
        self.minsize(680, 520)
        self.protocol("WM_DELETE_WINDOW", self._close)
        container = ttk.Frame(self, padding=10)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)
        ttk.Label(
            container,
            text="Source-bound task planning · inspect original file SHA, no model",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text=(
                "Enter an EXISTING 0700 private output directory outside "
                "the project/model/SQLite tree. Keep original task text private."
            ),
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", pady=(3, 8))
        self.input = ScrolledText(
            container, wrap="none", font=("TkFixedFont", 10),
            height=20, undo=True,
        )
        self.input.grid(row=2, column=0, sticky="nsew")
        self.input.insert("1.0", default_composer_template(parent._owner))
        controls = ttk.Frame(container)
        controls.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.inspect_button = ttk.Button(
            controls, text="BUILD & INSPECT PRIVATE NATIVE CAMPAIGN (NO MODEL)",
            command=self._inspect,
        )
        self.inspect_button.pack(side="left", padx=(0, 8))
        self.close_button = ttk.Button(
            controls, text="Cancel without model work", command=self._close,
        )
        self.close_button.pack(side="right")
        ttk.Label(container, textvariable=self.status, wraplength=890).grid(
            row=4, column=0, sticky="w", pady=(9, 0),
        )
        self.after(100, self._pump)

    def _inspect(self):
        if self._busy or self._closing or self._campaign._busy:
            return
        if self._campaign._operator.native_launch_consumed:
            self.status.set(
                "A real native request already occurred. Open a NEW campaign "
                "window; this operator cannot rearm uncertain SQLite work.",
            )
            return
        try:
            raw = self.input.get("1.0", "end-1c").encode("utf-8", "strict")
        except UnicodeError:
            self.status.set("Task input contains invalid Unicode; no source read.")
            return
        self._busy = True
        self._epoch += 1
        epoch = self._epoch
        self.input.configure(state="disabled")
        self.inspect_button.configure(state="disabled")
        self.status.set("Cold source snapshot and exact native task SHA inspection…")
        threading.Thread(
            target=self._worker, args=(epoch, raw), daemon=True,
        ).start()

    def _worker(self, epoch, raw):
        try:
            private, public = compose_campaign(raw)
            content = json.dumps(
                private, ensure_ascii=False, sort_keys=True, indent=2,
            )
            if len(content.encode("utf-8", "strict")) > MAX_COMPOSER_DISPLAY_BYTES:
                raise ValueError("private full campaign UI exceeded byte budget")
            self._queue.put((epoch, True, content, public))
        except (Exception, KeyboardInterrupt):
            self._queue.put((epoch, False, "", None))

    def _pump(self):
        if self._closing:
            return
        try:
            while True:
                epoch, ok, full_private, receipt = self._queue.get_nowait()
                if epoch != self._epoch:
                    continue
                self._busy = False
                self.inspect_button.configure(state="normal")
                self.input.configure(state="normal")
                if not ok:
                    self.status.set(
                        "Composing source job HELD. Check original source SHA, "
                        "private 0700 parent, file names and total budgets. "
                        "No model or source file write occurred.",
                    )
                    continue
                if self._campaign._busy or self._campaign._operator.native_launch_consumed:
                    self.status.set(
                        "Parent campaign state changed. Private composed goals "
                        "were NOT installed into another operator session.",
                    )
                    continue
                # The original JSON is human-owned, and remains editable.
                # Never echo generated private task/source paths to Tk status.
                editor = self._campaign.original_json
                editor.delete("1.0", "end")
                editor.insert("1.0", full_private)
                self._campaign.typed_manifest.set("")
                self._campaign._operator.reset()
                self._campaign.status.set(
                    "Private task composer succeeded. Inspect this original "
                    "campaign in the parent workbench, independently check "
                    "the SHA, and separately authorize any real native run.",
                )
                self.status.set(
                    "Read-only source task manifest built: "
                    + str(receipt["task_count"])
                    + " tasks. Return to parent and INSPECT. No model started.",
                )
                self.lift()
        except Empty:
            pass
        self.after(100, self._pump)

    def _close(self):
        if self._busy:
            self.status.set(
                "Original source snapshot is active; no cancellation or silent "
                "partial result adoption. This view remains open.",
            )
            return
        self._closing = True
        self._epoch += 1
        if getattr(self._campaign, "_composer", None) is self:
            self._campaign._composer = None
        self.destroy()


__all__ = [
    "NativeCampaignComposerWindow", "default_composer_template",
]
