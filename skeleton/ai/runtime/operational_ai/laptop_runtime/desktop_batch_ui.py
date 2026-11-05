"""Explicit operator-approved serial durable work from the Jeeves desktop.

This window runs ONLY when the operator selects Start. It does not schedule
background jobs, spawn virtual workers, hold a second SQLite database or
resume uncertain model effects. Each item has an original visible run ID and
uses the already installed, source-bound GGUF child exactly once.
"""
from __future__ import annotations

from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_batch_work import (
    BatchHold, DurableBatchPlan,
    SerialDurableBatchRunner, parse_durable_batch,
)


_TEMPLATE = '''{
  "schema": "jeeves.desktop.durable-work-batch.v1",
  "items": [
    {
      "title": "Implement original offline feature",
      "task": "Build a concrete bounded original feature. Explain any unverified gaps.",
      "maximum_steps": 8,
      "maximum_model_calls": 8,
      "maximum_wall_seconds": 180
    }
  ]
}'''


class DurableBatchWindow(tk.Toplevel):
    """One operator-controlled foreground session and immutable source plan."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_ui = parent
        self.title("Jeeves — Serial Native Work Batches")
        self.geometry("1060x780")
        self.minsize(870, 640)
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self._runner: SerialDurableBatchRunner | None = None
        self._plan: DurableBatchPlan | None = None
        self._plan_bytes: str | None = None
        self._worker = None
        self._queue: Queue = Queue()
        self._busy = False
        self._closed = False
        self.manifest_sha = tk.StringVar()
        self.status = tk.StringVar(
            value="No native work approved. Source tasks are never stored here.",
        )
        self._build()
        self.proposal.insert("1.0", _TEMPLATE)
        self.proposal.edit_modified(False)
        self.after(75, self._poll)

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=2)
        root.rowconfigure(4, weight=2)

        ttk.Label(
            root, text=(
                "Operator-approved sequential work, not an autonomous queue. "
                "Original task text is private, finite and only sent to the "
                "single already-connected native GGUF. One SQLite work order "
                "is created per task; no automatic resume or tool grants."
            ), wraplength=1000,
        ).grid(row=0, column=0, sticky="w", pady=(0, 9))

        buttons = ttk.Frame(root)
        buttons.grid(row=1, column=0, sticky="ew")
        self.review_button = ttk.Button(
            buttons, text="Review entire source work batch",
            command=self._review,
        )
        self.review_button.pack(side="left")
        self.invalidate_button = ttk.Button(
            buttons, text="Invalidate review",
            command=self._invalidate,
        )
        self.invalidate_button.pack(side="left", padx=6)

        self.proposal = ScrolledText(root, height=12, undo=True, wrap="none")
        self.proposal.grid(row=2, column=0, sticky="nsew", pady=(6, 10))
        self.proposal.bind("<<Modified>>", self._edited)

        ttk.Label(
            root, text="Reviewed immutable tasks — preserve each run ID for cold recovery",
        ).grid(row=3, column=0, sticky="w")
        self.items = ttk.Treeview(
            root,
            columns=("index", "title", "run_id", "model_calls", "wall"),
            show="headings", height=11,
        )
        for field, title, width in (
            ("index", "#", 45),
            ("title", "Operator task", 290),
            ("run_id", "Canonical SQLite run ID", 300),
            ("model_calls", "Max native calls", 125),
            ("wall", "Wall budget (s)", 130),
        ):
            self.items.heading(field, text=title)
            self.items.column(field, width=width, stretch=field == "title")
        self.items.grid(row=4, column=0, sticky="nsew", pady=(5, 10))

        approval = ttk.Frame(root)
        approval.grid(row=5, column=0, sticky="ew")
        approval.columnconfigure(1, weight=1)
        ttk.Label(
            approval, text="Confirm FULL reviewed batch SHA-256",
        ).grid(row=0, column=0, sticky="w", padx=(0, 7))
        ttk.Entry(
            approval, textvariable=self.manifest_sha,
        ).grid(row=0, column=1, sticky="ew")
        self.start_button = ttk.Button(
            approval, text="Execute approved tasks SERIALLY",
            command=self._start,
        )
        self.start_button.grid(row=0, column=2, padx=(7, 0))
        self.stop_button = ttk.Button(
            approval, text="Stop AFTER current task",
            command=self._stop,
        )
        self.stop_button.grid(row=0, column=3, padx=(7, 0))

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.grid(row=6, column=0, sticky="ew", pady=(10, 5))
        ttk.Label(
            root, textvariable=self.status, wraplength=990,
        ).grid(row=7, column=0, sticky="w")
        ttk.Label(
            root, wraplength=990,
            text=(
                "When any native request fails or is uncertain, the queue stops "
                "and preserves its ID. Do not reissue it: use manual durable "
                "SQLite inspection/replay with the exact original task/budget."
            ),
        ).grid(row=8, column=0, sticky="w", pady=(5, 0))
        self._buttons()

    def _edited(self, event=None):
        if self.proposal.edit_modified():
            self.proposal.edit_modified(False)
            if self._plan is not None:
                self._invalidate()

    def _invalidate(self):
        if self._busy:
            return
        self._plan = None
        self._plan_bytes = None
        self._worker = None
        self._runner = None
        self.manifest_sha.set("")
        for row in self.items.get_children():
            self.items.delete(row)
        self.status.set(
            "Review invalidated; enter a new plan and re-approve all immutable run IDs",
        )
        self._buttons()

    def _buttons(self):
        self.review_button.configure(
            state="disabled" if self._busy else "normal",
        )
        self.invalidate_button.configure(
            state="disabled" if self._busy else "normal",
        )
        eligible = (
            self._plan is not None
            and self._worker is not None
            and self._worker.connected
            and not self._busy
        )
        self.start_button.configure(state="normal" if eligible else "disabled")
        self.stop_button.configure(
            state="normal" if self._busy and self._runner is not None
            else "disabled",
        )

    def _review(self):
        if self._busy:
            return
        bridge = self.parent_ui._bridge
        if bridge is None or not bridge.connected:
            self.status.set("Connect the real source-bound native GGUF first")
            return
        original = self.proposal.get("1.0", "end-1c")
        try:
            plan = parse_durable_batch(original)
        except (BatchHold, ValueError, UnicodeError) as exc:
            self._invalidate()
            self.status.set(
                "Finite work batch held: " + type(exc).__name__
                + ". No model, tools or SQLite sessions created.",
            )
            return
        self._plan = plan
        self._plan_bytes = original
        self._worker = bridge
        self.manifest_sha.set("")
        for row in self.items.get_children():
            self.items.delete(row)
        for seq, item in enumerate(plan.items, 1):
            self.items.insert(
                "", "end", iid=str(seq),
                values=(
                    seq, item.title, item.run_id,
                    item.maximum_model_calls,
                    item.maximum_wall_seconds,
                ),
            )
        self.status.set(
            str(len(plan.items)) + " real native work orders reviewed; "
            "total model-call ceiling " + str(plan.aggregate_model_calls)
            + "; total wall ceiling "
            + str(plan.aggregate_wall_seconds)
            + "s; SHA-256 " + plan.manifest_sha256,
        )
        self._buttons()

    def _start(self):
        if self._busy or self._plan is None or self._worker is None:
            return
        if self._worker is not self.parent_ui._bridge or not self._worker.connected:
            self.status.set("The exact reviewed installed native worker changed")
            return
        if self._plan_bytes != self.proposal.get("1.0", "end-1c"):
            self.status.set("Source task bytes changed; review and approve again")
            return
        if self.manifest_sha.get() != self._plan.manifest_sha256:
            self.status.set("Enter the entire exact reviewed batch SHA-256")
            return
        try:
            runner = SerialDurableBatchRunner(
                self._worker, self._plan,
                expected_manifest_sha256=self.manifest_sha.get(),
                approved=True,
                progress=lambda receipt: self._queue.put(
                    ("progress", receipt)
                ),
            )
        except BatchHold as exc:
            self.status.set("Batch admission held: " + type(exc).__name__)
            return

        self._runner = runner
        self._busy = True
        self.progress.start(100)
        self.status.set("Executing approved SQLite-native tasks sequentially…")
        self._buttons()

        def work():
            try:
                result = runner.execute()
                self._queue.put(("complete", result))
            except BaseException as exc:
                self._queue.put(("held", type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _stop(self):
        runner = self._runner
        if runner is None or not self._busy:
            return
        runner.stop_after_current()
        self.status.set(
            "Stop requested; current native/SQLite effect remains in flight. "
            "Queue will end before another task is submitted.",
        )

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, data = self._queue.get_nowait()
                if kind == "progress":
                    key = str(data.sequence)
                    if self.items.exists(key):
                        self.items.item(
                            key,
                            tags=("committed",)
                            if data.status == "durable-work-committed"
                            else ("held",),
                        )
                    self.status.set(
                        "Work " + str(data.sequence) + ": "
                        + data.status + " · " + data.run_id
                        + " · no automatic reissue",
                    )
                else:
                    self.progress.stop()
                    self._busy = False
                    self._runner = None
                    if kind == "complete":
                        receipt = data.public_receipt()
                        self.status.set(
                            "Batch " + receipt["status"] + " · "
                            + str(receipt["items_committed"])
                            + " committed, "
                            + str(receipt["items_started"])
                            + " started · manifest "
                            + str(receipt["manifest_sha256"])
                            + " · restart requires manual SQLite inspection",
                        )
                    else:
                        self.status.set(
                            "Serial native work held: " + str(data)
                            + ". Preserve all reviewed run IDs; no retries.",
                        )
                    self._buttons()
        except Empty:
            pass
        self.after(75, self._poll)

    def _exit(self):
        if self._busy:
            self.status.set(
                "A native work order is active. Stop after current task; "
                "closing cannot cancel an uncertain SQLite effect safely.",
            )
            return
        self._closed = True
        self.destroy()


__all__ = ["DurableBatchWindow"]
