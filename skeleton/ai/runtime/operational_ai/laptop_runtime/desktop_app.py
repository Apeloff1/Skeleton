"""Jeeves first-laptop offline desktop workbench.

Real chats use one independently checked installed GGUF process and the
canonical principal-bound SQLite ExecutionSpine. Tk is only an operator UI.
No hosted provider, browser, files-to-model grant or extra transcript database.
"""
from __future__ import annotations

import json
from queue import Empty, Queue
import secrets
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter.scrolledtext import ScrolledText

from .desktop_client import DesktopBridge, DesktopBridgeHold, DesktopConfig
from .desktop_protocol import DesktopProtocolHold, MAX_PROMPT
from .desktop_attachments import (
    DesktopAttachmentHold, selected_text, compose_prompt, MAX_ATTACHMENT_COUNT,
)

# The UI is an in-memory viewport, not another conversation state store.
# Authoritative history is always fetched explicitly from native SQLite.
MAX_VIEWPORT_CHARS = 1000000


class JeevesWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Jeeves — Private Offline AI")
        self.minsize(850, 680)
        self.geometry("1140x840")
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self._bridge: DesktopBridge | None = None
        self._connecting: DesktopBridge | None = None
        self._events: Queue = Queue()
        self._busy = False
        self._closing = False
        # Worker/telemetry results belong to one source epoch, never a later
        # reconnected SQLite conversation.
        self._epoch = 0
        self._last_request: str | None = None
        self._last_answer: str | None = None  # RAM-only, never an automatic tool grant.
        self._attachments = []  # Explicit immutable source snapshots, never tool grants.
        self.attachment_text = tk.StringVar(value="No local source attached")
        self.context_enabled = tk.BooleanVar(value=True)
        self.agent_steps = tk.StringVar(value="8")
        self.agent_calls = tk.StringVar(value="8")
        self.agent_wall = tk.StringVar(value="180")
        self.reasoning_profile = tk.StringVar(value="advanced")
        self.durable_run_id = tk.StringVar(value="")
        self.enable_signed_source_tool = tk.BooleanVar(value=False)
        self.enable_pressure_guard = tk.BooleanVar(value=True)
        self._pressure_notified = False

        self.fields: dict[str, tk.StringVar] = {
            "model_root": tk.StringVar(value=""),
            "state_dir": tk.StringVar(value=""),
            "capacity_root": tk.StringVar(value=""),
            "tenant": tk.StringVar(value="local"),
            "subject": tk.StringVar(value="owner"),
            "context": tk.StringVar(value="4096"),
            "max_output_tokens": tk.StringVar(value="1024"),
            "threads": tk.StringVar(value="4"),
            "gpu_layers": tk.StringVar(value="0"),
            "inference_ms": tk.StringVar(value="90000"),
            "capacity_budget_bytes": tk.StringVar(value="8000000000"),
            "signed_source_root": tk.StringVar(value=""),
            "signed_source_manifest": tk.StringVar(value=""),
            "max_signed_sources": tk.StringVar(value="4"),
            "max_signed_tool_calls": tk.StringVar(value="3"),
            "minimum_free_ram_bytes": tk.StringVar(value="536870912"),
            "minimum_free_disk_bytes": tk.StringVar(value="268435456"),
            "pressure_interval_ms": tk.StringVar(value="500"),
        }
        self.resume_id = tk.StringVar(value="")
        self.session_text = tk.StringVar(value="No native session")
        self.connection_text = tk.StringVar(value="Disconnected — no model loaded")
        self.request_text = tk.StringVar(value="No native request issued")
        self._build()
        self.after(75, self._pump)

    def _build(self):
        main = ttk.Frame(self, padding=14)
        main.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        settings = ttk.LabelFrame(main, text="Installed local GGUF and private state", padding=10)
        settings.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        for col in range(4):
            settings.columnconfigure(col, weight=1 if col % 2 else 0)
        rows = [
            ("Model root", "model_root", "State directory", "state_dir"),
            ("Capacity root (optional)", "capacity_root", "Owner", "subject"),
            ("Tenant", "tenant", "Context tokens", "context"),
            ("Max output tokens", "max_output_tokens", "CPU threads", "threads"),
            ("GPU layers", "gpu_layers", "Inference deadline (ms)", "inference_ms"),
            ("Capacity reservation (bytes)", "capacity_budget_bytes", None, None),
            ("Approved source root (optional)", "signed_source_root",
             "Signed source manifest", "signed_source_manifest"),
            ("Signed sources", "max_signed_sources",
             "Read-only lookup calls", "max_signed_tool_calls"),
            ("Minimum RAM headroom (bytes)", "minimum_free_ram_bytes",
             "Minimum state disk free (bytes)", "minimum_free_disk_bytes"),
            ("Pressure sampling interval (ms)", "pressure_interval_ms", None, None),
        ]
        for row_idx, (label_a, key_a, label_b, key_b) in enumerate(rows):
            ttk.Label(settings, text=label_a).grid(
                row=row_idx, column=0, sticky="w", padx=4, pady=4,
            )
            ttk.Entry(settings, textvariable=self.fields[key_a]).grid(
                row=row_idx, column=1, sticky="ew", padx=4, pady=4,
            )
            if label_b and key_b:
                ttk.Label(settings, text=label_b).grid(
                    row=row_idx, column=2, sticky="w", padx=4, pady=4,
                )
                ttk.Entry(settings, textvariable=self.fields[key_b]).grid(
                    row=row_idx, column=3, sticky="ew", padx=4, pady=4,
                )

        ttk.Checkbutton(
            settings,
            text="I explicitly authorize bounded read-only lookup of operator-signed sources",
            variable=self.enable_signed_source_tool,
        ).grid(row=10, column=0, columnspan=4, sticky="w", pady=(4, 2))
        ttk.Checkbutton(
            settings,
            text="Protect active native GGUF child against observed host/cgroup/disk pressure",
            variable=self.enable_pressure_guard,
        ).grid(row=11, column=0, columnspan=4, sticky="w", pady=(4, 2))
        ttk.Button(
            settings, text="Host pressure status", command=self._pressure_status,
        ).grid(row=12, column=0, sticky="w", pady=(4, 0))
        self.profile_button = ttk.Button(
            settings, text="Suggest measured CPU/RAM profile",
            command=self._suggest_profile,
        )
        self.profile_button.grid(
            row=12, column=1, columnspan=2, sticky="e", pady=(5, 0),
        )
        ttk.Button(
            settings, text="Prepare / install approved local model",
            command=self._setup,
        ).grid(row=12, column=3, sticky="e", pady=(5, 0))

        bar = ttk.Frame(main)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Resume existing ID").grid(row=0, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.resume_id, width=29).grid(
            row=0, column=1, sticky="ew", padx=(6, 10),
        )
        self.connect_button = ttk.Button(bar, text="Connect native", command=self._connect)
        self.connect_button.grid(row=0, column=2, padx=3)
        self.disconnect_button = ttk.Button(bar, text="Disconnect", command=self._disconnect)
        self.disconnect_button.grid(row=0, column=3, padx=3)
        self.new_button = ttk.Button(bar, text="New session", command=lambda: self._action("new"))
        self.new_button.grid(row=0, column=4, padx=3)
        self.resume_button = ttk.Button(bar, text="Resume", command=self._resume)
        self.resume_button.grid(row=0, column=5, padx=3)
        self.history_button = ttk.Button(
            bar, text="SQLite history", command=lambda: self._action("history"),
        )
        self.history_button.grid(row=0, column=6, padx=3)
        self.close_button = ttk.Button(
            bar, text="Close session", command=lambda: self._action("close"),
        )
        self.close_button.grid(row=0, column=7, padx=3)
        self.telemetry_button = ttk.Button(
            bar, text="Live capacity", command=lambda: self._action("telemetry"),
        )
        self.telemetry_button.grid(row=0, column=8, padx=3)
        self.source_status_button = ttk.Button(
            bar, text="Signed source status",
            command=lambda: self._action("source-status"),
        )
        self.source_status_button.grid(row=0, column=9, padx=3)

        console_frame = ttk.LabelFrame(main, text="Private local conversation", padding=6)
        console_frame.grid(row=2, column=0, sticky="nsew")
        console_frame.rowconfigure(0, weight=1)
        console_frame.columnconfigure(0, weight=1)
        self.console = ScrolledText(
            console_frame, wrap="word", height=18, font=("TkFixedFont", 10),
            state="disabled", undo=False,
        )
        self.console.grid(row=0, column=0, sticky="nsew")
        self.console.tag_configure("you", foreground="#205d95")
        self.console.tag_configure("jeeves", foreground="#286e43")
        self.console.tag_configure("note", foreground="#6d6480")
        self.console.tag_configure("warning", foreground="#ad5417")

        compose = ttk.LabelFrame(main, text="Prompt — exact Unicode and multiline code", padding=7)
        compose.grid(row=3, column=0, sticky="ew", pady=(8, 4))
        compose.columnconfigure(0, weight=1)
        self.prompt = ScrolledText(compose, wrap="word", height=6, undo=True)
        self.prompt.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.prompt.bind("<Control-Return>", self._keyboard_send)
        send_actions = ttk.Frame(compose)
        send_actions.grid(row=0, column=1, sticky="se")
        self.send_button = ttk.Button(send_actions, text="Send local chat", command=self._send)
        self.send_button.pack(fill="x", pady=(0, 5))
        self.agent_button = ttk.Button(
            send_actions, text="Run native Jeeves agent",
            command=self._run_agent,
        )
        self.agent_button.pack(fill="x")
        attachment_bar = ttk.Frame(compose)
        attachment_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        attachment_bar.columnconfigure(0, weight=1)
        ttk.Label(attachment_bar, textvariable=self.attachment_text).grid(
            row=0, column=0, sticky="w",
        )
        ttk.Button(
            attachment_bar, text="Attach text/code file", command=self._attach,
        ).grid(row=0, column=1, padx=4)
        ttk.Button(
            attachment_bar, text="Search project sources",
            command=self._search_sources,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Button(
            attachment_bar, text="Insert existing-edit format",
            command=self._existing_edit_format,
        ).grid(row=2, column=1, sticky="e", padx=4, pady=(4, 0))
        ttk.Button(
            attachment_bar, text="Review existing-file edits",
            command=self._existing_edits,
        ).grid(row=2, column=2, sticky="e", pady=(4, 0))
        ttk.Button(
            attachment_bar, text="Build reviewed Git patch",
            command=self._patch_delivery,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(
            attachment_bar, text="Generate source with bounded repair",
            command=self._guided_source_repair,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(
            attachment_bar, text="Clear attached files", command=self._clear_attachments,
        ).grid(row=0, column=2, padx=4)
        ttk.Checkbutton(
            attachment_bar,
            text="Use recent committed SQLite turns as bounded context",
            variable=self.context_enabled,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(
            attachment_bar, text="Insert source proposal format",
            command=self._insert_proposal_format,
        ).grid(row=1, column=1, sticky="e", padx=4, pady=(4, 0))
        ttk.Button(
            attachment_bar, text="Review Jeeves file proposal",
            command=self._workspace,
        ).grid(row=1, column=2, sticky="e", pady=(4, 0))
        agent_budget = ttk.Frame(compose)
        agent_budget.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        for column, (label, variable) in enumerate((
            ("Agent steps", self.agent_steps),
            ("Native calls", self.agent_calls),
            ("Wall seconds", self.agent_wall),
        )):
            block = ttk.Frame(agent_budget)
            block.grid(row=0, column=column, sticky="w", padx=(0, 12))
            ttk.Label(block, text=label).pack(side="left", padx=(0, 5))
            ttk.Entry(block, textvariable=variable, width=7).pack(side="left")
        ttk.Label(
            agent_budget, text="Reasoning profile",
        ).grid(row=0, column=3, sticky="w", padx=(4, 6))
        ttk.Combobox(
            agent_budget,
            textvariable=self.reasoning_profile,
            values=("advanced", "guarded"),
            state="readonly", width=11,
        ).grid(row=0, column=4, sticky="w")
        ttk.Label(
            agent_budget,
            text="Host-bounded reasoning; no hidden provider/memory permissions",
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(3, 0))

        durable = ttk.LabelFrame(
            compose, text="Restart-safe native work orders · exact task/budgets required",
            padding=5,
        )
        durable.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        durable.columnconfigure(1, weight=1)
        ttk.Label(durable, text="Durable run ID").grid(row=0, column=0, padx=(0, 7))
        ttk.Entry(
            durable, textvariable=self.durable_run_id, width=30,
        ).grid(row=0, column=1, sticky="ew")
        self.durable_buttons = []
        for column, (label, work_action) in enumerate((
            ("New durable work", "start"),
            ("Inspect", "inspect"),
            ("Resume explicitly", "resume"),
            ("Replay terminal", "replay"),
        ), start=2):
            button = ttk.Button(
                durable, text=label,
                command=lambda action=work_action: self._durable(action),
            )
            button.grid(row=0, column=column, padx=3)
            self.durable_buttons.append(button)
        self.batch_button = ttk.Button(
            durable, text="Run serial work batch", command=self._batch_work,
        )
        self.batch_button.grid(row=1, column=1, columnspan=3, sticky="e", pady=(6, 0))

        footer = ttk.Frame(main)
        footer.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.connection_text).grid(
            row=0, column=0, sticky="w",
        )
        ttk.Label(footer, textvariable=self.session_text).grid(
            row=1, column=0, sticky="w",
        )
        ttk.Label(footer, textvariable=self.request_text).grid(
            row=2, column=0, sticky="w",
        )
        ttk.Button(footer, text="Copy session ID", command=self._copy_session).grid(
            row=1, column=1, padx=4,
        )
        ttk.Label(
            footer,
            text="Local GGUF only · SQLite is authoritative · no automatic retry · not release-certified",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._controls()

    def _show(self, label: str, value: str, tag: str = "note"):
        self.console.configure(state="normal")
        self.console.insert("end", label + "\n", tag)
        self.console.insert("end", value + "\n\n", tag)
        total = self.console.count("1.0", "end-1c", "chars")
        if total and total[0] > MAX_VIEWPORT_CHARS:
            # Trim only this in-memory viewport, never canonical SQLite.
            excess = total[0] - MAX_VIEWPORT_CHARS // 2
            self.console.delete("1.0", "1.0+" + str(excess) + "c")
        self.console.configure(state="disabled")
        self.console.see("end")

    def _controls(self):
        connected = self._bridge is not None and self._bridge.connected
        active = connected and not self._busy
        self.connect_button.configure(
            state="normal" if not connected and not self._busy else "disabled",
        )
        self.disconnect_button.configure(
            state="normal" if connected or self._connecting is not None else "disabled",
        )
        self.profile_button.configure(
            state="normal" if not connected and not self._busy else "disabled",
        )
        for button in (
            self.new_button, self.resume_button,
            self.telemetry_button, self.source_status_button, self.agent_button,
            self.batch_button, *self.durable_buttons,
        ):
            button.configure(state="normal" if active else "disabled")
        has_session = (
            active and self._bridge is not None
            and self._bridge.session_id is not None
        )
        for button in (self.history_button, self.close_button, self.send_button):
            button.configure(state="normal" if has_session else "disabled")

    def _configuration(self) -> DesktopConfig:
        form = {key: var.get() for key, var in self.fields.items()}
        fields = (
            "context", "max_output_tokens", "threads", "gpu_layers",
            "inference_ms", "capacity_budget_bytes",
            "max_signed_sources", "max_signed_tool_calls",
            "minimum_free_ram_bytes", "minimum_free_disk_bytes",
            "pressure_interval_ms",
        )
        for key in fields:
            form[key] = int(form[key])
        for optional in (
            "capacity_root", "signed_source_root", "signed_source_manifest",
        ):
            form[optional] = form[optional] or None
        form["enable_signed_source_tool"] = self.enable_signed_source_tool.get()
        form["enable_pressure_guard"] = self.enable_pressure_guard.get()
        return DesktopConfig(**form)

    def _setup(self):
        from .desktop_setup_ui import SetupWindow
        SetupWindow(self)

    def _pressure_status(self):
        bridge = self._bridge or self._connecting
        if bridge is None:
            self._show("Native pressure", "No active local child to observe")
            return
        self._show(
            "Measured native resource pressure",
            json.dumps(bridge.pressure_status, ensure_ascii=False, sort_keys=True),
        )

    def _suggest_profile(self):
        # Read-only model source inspection and host/cgroup measurements can
        # take time; never block Tk or modify a running native worker.
        if self._busy or (self._bridge is not None and self._bridge.connected):
            return
        model = self.fields["model_root"].get()
        state = self.fields["state_dir"].get()
        epoch = self._epoch
        self._busy = True
        self.connection_text.set("Inspecting installed source and effective CPU/RAM…")
        self._controls()

        def work():
            try:
                from .desktop_capacity_plan import plan_existing_model
                result = plan_existing_model(model, state)
                self._events.put(("capacity-profile", epoch, result))
            except BaseException as exc:
                # Kernel paths, model roots and exception strings are private.
                self._events.put(("capacity-error", epoch, type(exc).__name__))

        threading.Thread(target=work, daemon=True).start()

    def _workspace(self):
        from .desktop_workspace_ui import WorkspaceWindow
        WorkspaceWindow(self, source_text=self._last_answer or "")

    def _batch_work(self):
        if self._bridge is None or not self._bridge.connected or self._busy:
            self._show(
                "Serial work held",
                "Connect a real installed GGUF before approving durable work",
                "warning",
            )
            return
        from .desktop_batch_ui import DurableBatchWindow
        DurableBatchWindow(self)

    def _search_sources(self):
        from .desktop_source_search_ui import SourceSearchWindow
        SourceSearchWindow(self)

    def _existing_edits(self):
        from .desktop_existing_edit_ui import ExistingEditWindow
        ExistingEditWindow(self, source_text=self._last_answer or "")

    def _patch_delivery(self):
        # A real local GGUF may author suggestions; only an operator may
        # inspect exact original file bytes and export an inert reviewed
        # patch outside the project. No model tool or Git write is granted.
        from .desktop_patch_ui import PortablePatchWindow
        PortablePatchWindow(self, source_text=self._last_answer or "")

    def _guided_source_repair(self):
        # Same existing installed GGUF + committed SQLite native chat.
        # This explicit operator workflow only proposes source text; no Git,
        # shell, project writes, or automatic reruns of uncertain effects.
        bridge = self._bridge
        if (
            self._busy or bridge is None or not bridge.connected
            or bridge.session_id is None
        ):
            self._show(
                "Native source repair held",
                "Connect an approved local GGUF and open a durable SQLite session",
                "warning",
            )
            return
        from .desktop_source_repair_ui import SourceRepairWindow
        SourceRepairWindow(self, initial_goal=self.prompt.get("1.0", "end-1c"))

    def _existing_edit_format(self):
        self.prompt.insert(
            "end",
            "\n\nReturn only a strict JSON object with schema "
            "'jeeves.workspace.existing-file-edits.v1' and files: "
            "an array of objects containing path, expected_sha256, "
            "and replacement. Each path must name an EXISTING regular "
            "project file, expected_sha256 must be its current full "
            "SHA-256 from the operator's source inventory, and replacement "
            "must contain the COMPLETE proposed source text. No markdown "
            "fences or other fields. You have no permission to execute, "
            "overwrite, delete, rename, deploy or write source files. "
            "Your output will be inspected as untrusted proposal data; "
            "a human may separately approve an INERT sibling candidate.",
        )
        self.prompt.focus_set()

    def _insert_proposal_format(self):
        self.prompt.insert(
            "end",
            "\n\nReturn only a JSON object with schema "
            "'jeeves.workspace.new-files.v1' and files: an array of "
            "objects with path (relative UTF-8 source filename) and content "
            "(exact complete source UTF-8 text). Propose only NEW files "
            "under already-existing project directories. Do not include "
            "Markdown fences, shell commands, binary files, unknown fields "
            "or an instruction to overwrite existing files. "
            "An operator will separately review exact hashes and approve "
            "one publication at a time.",
        )
        self.prompt.focus_set()

    def _connect(self):
        if self._busy or (self._bridge is not None and self._bridge.connected):
            return
        try:
            config = self._configuration()
            session = self.resume_id.get().strip() or None
            bridge = DesktopBridge(config, resume_session=session)
        except (ValueError, DesktopBridgeHold) as exc:
            self._show("Connection held", type(exc).__name__, "warning")
            return
        self._epoch += 1
        self._pressure_notified = False
        self._busy = True
        self._connecting = bridge
        self.connection_text.set("Loading independently installed native GGUF…")
        self._controls()

        def run():
            try:
                witness = bridge.open()
                self._events.put(("connect", bridge, witness))
            except BaseException as exc:
                bridge.abort()
                self._events.put(("connect-error", bridge, type(exc).__name__))

        threading.Thread(target=run, daemon=True).start()

    def _disconnect(self):
        self._epoch += 1
        self._pressure_notified = False
        current = self._bridge or self._connecting
        if current is not None:
            current.abort()
        self._bridge = None
        self._connecting = None
        self._busy = False
        self.connection_text.set("Disconnected — previous SQLite session preserved")
        self._controls()

    def _action(self, action: str, **values):
        bridge = self._bridge
        if bridge is None or not bridge.connected or self._busy:
            return
        self._busy = True
        self._controls()

        def run():
            try:
                result = bridge.request(action, **values)
                self._events.put(("result", (bridge, action), result))
            except BaseException as exc:
                # Never display private exception messages, prompts or paths.
                self._events.put(("result-error", (bridge, action), type(exc).__name__))

        threading.Thread(target=run, daemon=True).start()

    def _resume(self):
        session = self.resume_id.get().strip()
        if not session:
            self._show("Resume held", "Enter an existing durable session ID", "warning")
            return
        self._action("resume", session_id=session)

    def _attach(self):
        if len(self._attachments) >= MAX_ATTACHMENT_COUNT:
            self._show("Source held", "Maximum four explicit text snapshots", "warning")
            return
        selection = filedialog.askopenfilename(
            parent=self, title="Choose one local text/code reference file",
        )
        if not selection:
            return
        try:
            source = selected_text(selection)
            if any(
                x.name == source.name and x.sha256 == source.sha256
                for x in self._attachments
            ):
                raise DesktopAttachmentHold("duplicate source snapshot")
            self._attachments.append(source)
            self.attachment_text.set(
                str(len(self._attachments)) + " source snapshot(s) · "
                + ", ".join(x.name for x in self._attachments)
            )
            self._show("Local source selected", source.display)
        except (DesktopAttachmentHold, OSError, UnicodeError) as exc:
            self._show("Source held", type(exc).__name__, "warning")

    def _clear_attachments(self):
        self._attachments.clear()
        self.attachment_text.set("No local source attached")

    def _send(self):
        message = self.prompt.get("1.0", "end-1c")
        if not message.strip():
            self._show("Prompt held", "Enter a nonempty local task", "warning")
            return
        try:
            combined = compose_prompt(message, tuple(self._attachments))
        except (DesktopAttachmentHold, UnicodeError, ValueError) as exc:
            self._show("Source or prompt held", type(exc).__name__, "warning")
            return
        if len(combined.encode("utf-8", "strict")) > MAX_PROMPT:
            self._show("Prompt held", "Native input exceeds 32768 UTF-8 bytes", "warning")
            return
        if (self._busy or self._bridge is None or not self._bridge.connected
                or self._bridge.session_id is None):
            return
        request_id = "r_" + secrets.token_hex(16)
        self._last_request = request_id
        self.request_text.set("Native request: " + request_id)
        # Intentional private UI disclosure, no file/clipboard/network write.
        annotation = (
            "\n\n[" + str(len(self._attachments)) + " selected local reference files]"
            if self._attachments else ""
        )
        self._show("You", message + annotation, "you")
        self._action(
            "turn", prompt=combined, request_id=request_id,
            context=self.context_enabled.get(),
        )

    def _run_agent(self):
        # The strict Jeeves planner runs through the same installed/source
        # checked native child, with no extra memory store or tool grants.
        bridge = self._bridge
        if self._busy or bridge is None or not bridge.connected:
            return
        message = self.prompt.get("1.0", "end-1c")
        try:
            prompt = compose_prompt(message, tuple(self._attachments))
            steps = int(self.agent_steps.get())
            calls = int(self.agent_calls.get())
            wall = int(self.agent_wall.get())
            profile = self.reasoning_profile.get()
            if profile not in ("guarded", "advanced"):
                raise ValueError("unapproved native planner profile")
            if profile == "advanced" and (steps < 4 or calls < 6):
                raise ValueError("advanced planner needs at least 4 steps and 6 model calls")
            if (
                not 1 <= steps <= 64 or not 1 <= calls <= 64
                or not 1 <= wall <= 600
            ):
                raise ValueError("invalid finite Jeeves agent budget")
        except (ValueError, DesktopAttachmentHold, UnicodeError) as exc:
            self._show("Agent task held", type(exc).__name__, "warning")
            return
        run_id = "jrun_" + secrets.token_hex(16)
        self._last_request = run_id
        self.request_text.set("Native agent run: " + run_id)
        self._show(
            "You · bounded Jeeves agent",
            message + (
                "\n\n[" + str(len(self._attachments)) + " read-only source files]"
                if self._attachments else ""
            ), "you",
        )
        self._action(
            "agent", prompt=prompt, run_id=run_id,
            maximum_steps=steps, maximum_model_calls=calls,
            maximum_wall_seconds=wall,
            profile=profile,
        )

    def _durable(self, action: str):
        # The operator must use the original task/limits on cold reopen.
        # No stored credentials, hidden run resume or model-granted tools.
        bridge = self._bridge
        if self._busy or bridge is None or not bridge.connected:
            return
        if action == "start":
            run_id = "wrun_" + secrets.token_hex(16)
            self.durable_run_id.set(run_id)
        else:
            run_id = self.durable_run_id.get().strip()
            if not run_id:
                self._show(
                    "Durable work held", "Enter the original durable run ID",
                    "warning",
                )
                return
        message = self.prompt.get("1.0", "end-1c")
        try:
            original = compose_prompt(message, tuple(self._attachments))
            steps = int(self.agent_steps.get())
            calls = int(self.agent_calls.get())
            wall = int(self.agent_wall.get())
            if not (1 <= steps <= 64 and 1 <= calls <= 64 and 1 <= wall <= 600):
                raise ValueError("invalid durable wall and step budget")
        except (ValueError, DesktopAttachmentHold, UnicodeError) as exc:
            self._show("Durable work held", type(exc).__name__, "warning")
            return
        self._last_request = run_id
        self.request_text.set("Durable native " + action + ": " + run_id)
        self._show(
            "Durable operator " + action,
            "Source-bound task and budget submitted under " + run_id
            + ". No automatic recovery or tool grants.",
        )
        self._action(
            "durable", action=action, run_id=run_id, prompt=original,
            maximum_steps=steps, maximum_model_calls=calls,
            maximum_wall_seconds=wall,
        )

    def _keyboard_send(self, event):
        self._send()
        return "break"

    def _copy_session(self):
        if self._bridge is None or self._bridge.session_id is None:
            return
        self.clipboard_clear()
        self.clipboard_append(self._bridge.session_id)

    def _pump(self):
        if self._closing:
            return
        try:
            while True:
                event, name, payload = self._events.get_nowait()
                if event == "connect":
                    if self._connecting is not name or not name.connected:
                        name.abort()
                        continue
                    self._bridge = name
                    self._connecting = None
                    self._busy = False
                    signed = bool(
                        payload.get("signed_source_tool_active", False)
                    )
                    self.connection_text.set(
                        "Real installed GGUF source checked"
                        + (" · signed read-only evidence enabled" if signed
                           else " · no model tools enabled"),
                    )
                    self.session_text.set("SQLite session: " + str(name.session_id))
                    self.resume_id.set(str(name.session_id))
                    self._show(
                        "Jeeves native ready",
                        "Installed GGUF is running in a local isolated child. "
                        "Use Send to perform a real native turn.",
                    )
                elif event == "connect-error":
                    if self._connecting is not name:
                        continue
                    self._connecting = None
                    self._bridge = None
                    self._busy = False
                    self.connection_text.set("Native startup held; no fallback provider")
                    self._show("Native startup held", payload, "warning")
                elif event == "capacity-profile":
                    if name != self._epoch:
                        continue
                    self._busy = False
                    if self._bridge is not None and self._bridge.connected:
                        continue
                    recommendation = payload.get("recommendation", {})
                    for key in (
                        "context", "max_output_tokens", "threads", "gpu_layers",
                        "inference_ms", "capacity_budget_bytes",
                    ):
                        if type(recommendation.get(key)) is int and key in self.fields:
                            self.fields[key].set(str(recommendation[key]))
                    self.connection_text.set(
                        "Conservative observed profile selected; no model started",
                    )
                    self._show(
                        "Measured device (advisory, not native qualification)",
                        "Effective memory: "
                        + str(payload.get("effective_available_bytes", "?"))
                        + " bytes; model estimate: "
                        + str(payload.get("estimated_requirement_bytes", "?"))
                        + " bytes; CPU cores: "
                        + str(payload.get("effective_cpu_cores", "?"))
                        + "; cgroup: " + str(payload.get("cgroup_source", "?"))
                        + ". GPU layers remain zero until independently verified.",
                    )
                elif event == "capacity-error":
                    if name != self._epoch:
                        continue
                    self._busy = False
                    self.connection_text.set("Resource profile held — no automatic escalation")
                    self._show("Device observation held", str(payload), "warning")
                elif event == "result":
                    origin, action = name
                    if origin is not self._bridge or not origin.connected:
                        continue
                    self._busy = False
                    result = payload
                    status = result.get("status", "")
                    bridge = self._bridge
                    if bridge is not None:
                        self.session_text.set(
                            "SQLite session: " + str(bridge.session_id),
                        )
                        if bridge.session_id is not None:
                            self.resume_id.set(bridge.session_id)
                    if action == "source-status":
                        self._show(
                            "Operator-signed source status",
                            json.dumps(
                                {
                                    "source_tool_active": result.get(
                                        "signed_source_tool_active", False,
                                    ),
                                    "signed_source": result.get("signed_source"),
                                },
                                ensure_ascii=False, sort_keys=True,
                            ),
                        )
                    elif action == "telemetry":
                        self._show(
                            "Native supervised capacity (observation only)",
                            json.dumps(
                                result.get("observed", {}),
                                ensure_ascii=False, sort_keys=True,
                            ),
                        )
                    elif action == "durable":
                        report = result.get("durable", {})
                        self.durable_run_id.set(str(report.get("run_id", "")))
                        if report.get("status") == "inspected":
                            self._show(
                                "Canonical SQLite durable checkpoint",
                                json.dumps(
                                    report.get("snapshot", {}),
                                    ensure_ascii=False, sort_keys=True,
                                ),
                            )
                        else:
                            answer = report.get("answer", "")
                            self._last_answer = answer if type(answer) is str else None
                            self._show(
                                "Jeeves durable native result",
                                str(answer), "jeeves",
                            )
                        self.request_text.set(
                            "Durable " + str(report.get("action", ""))
                            + ": " + str(report.get("run_id", ""))
                            + " · original task/budgets needed for cold recovery",
                        )
                    elif action == "agent":
                        report = result.get("agent", {})
                        answer = report.get("answer", "")
                        self._last_answer = answer if type(answer) is str else None
                        self._show(
                            "Jeeves strict agent · verified native output",
                            str(answer), "jeeves",
                        )
                        self.prompt.delete("1.0", "end")
                        self._clear_attachments()
                        usage = report.get("usage", {})
                        self.request_text.set(
                            "Verified agent: " + str(report.get("run_id", ""))
                            + " · native model calls: "
                            + str(usage.get("model_calls", "?"))
                            + " · source tool: "
                            + ("signed read-only"
                               if report.get("signed_source_tool_active") is True
                               else "disabled")
                            + " · lookups: "
                            + str(usage.get("tool_calls", "?"))
                            + " · reasoning: "
                            + str(report.get("reasoning_profile", "guarded")),
                        )
                    elif action == "turn":
                        record = result.get("turn", {})
                        answer = record.get("answer", "")
                        self._last_answer = answer if type(answer) is str else None
                        self._show("Jeeves (committed SQLite receipt)", str(answer), "jeeves")
                        self.prompt.delete("1.0", "end")
                        self._clear_attachments()
                        self.request_text.set(
                            "Committed native request: " + str(result.get("request_id", ""))
                            + " · SQLite context: "
                            + str(result.get("context_messages", 0)) + " messages",
                        )
                    elif action == "history":
                        records = result.get("messages", [])
                        for row in records:
                            role = str(row.get("role", "message"))
                            self._show(role.title(), str(row.get("content", "")),
                                       "you" if role == "user" else "jeeves")
                    else:
                        self._show("Jeeves session", status)
                        if action == "close":
                            self.session_text.set("No active session; create or resume")
                elif event == "result-error":
                    origin, action = name
                    if origin is not self._bridge:
                        continue
                    self._busy = False
                    self.connection_text.set("Native request held — disconnect required")
                    self._show(
                        "Native operation held",
                        action + " (" + str(payload) + "). Outcome may be uncertain. "
                        "No automatic retry. Preserve the displayed request ID.",
                        "warning",
                    )
                    if self._bridge is not None:
                        self._bridge.abort()
                self._controls()
        except Empty:
            pass
        bridge = self._bridge
        if (
            bridge is not None and not bridge.connected
            and not self._pressure_notified
            and bridge.pressure_status.get("pressure_hold") is not None
        ):
            self._pressure_notified = True
            self.connection_text.set(
                "Native source held by pressure guard — manually inspect before reopening",
            )
            self._show(
                "Native child revoked under measured pressure",
                str(bridge.pressure_status.get("pressure_hold"))
                + ". No automatic replay/retry; preserve any SQLite request IDs.",
                "warning",
            )
            self._controls()
        self.after(75, self._pump)

    def _exit(self):
        self._epoch += 1
        self._closing = True
        for bridge in (self._bridge, self._connecting):
            if bridge is not None:
                bridge.abort()
        self.destroy()


def main(argv=None) -> int:
    if argv:
        raise SystemExit("Jeeves desktop accepts no prompt or secret arguments")
    app = JeevesWindow()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
