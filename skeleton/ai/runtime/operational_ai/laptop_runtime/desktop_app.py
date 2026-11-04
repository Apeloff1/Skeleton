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
        self._last_request: str | None = None
        self._last_answer: str | None = None  # RAM-only, never an automatic tool grant.
        self._attachments = []  # Explicit immutable source snapshots, never tool grants.
        self.attachment_text = tk.StringVar(value="No local source attached")
        self.context_enabled = tk.BooleanVar(value=True)

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

        ttk.Button(
            settings, text="Prepare / install approved local model",
            command=self._setup,
        ).grid(row=6, column=0, columnspan=4, sticky="e", pady=(5, 0))

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
        self.send_button = ttk.Button(compose, text="Send locally", command=self._send)
        self.send_button.grid(row=0, column=1, sticky="se")
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
        for button in (self.new_button, self.resume_button):
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
        )
        for key in fields:
            form[key] = int(form[key])
        form["capacity_root"] = form["capacity_root"] or None
        return DesktopConfig(**form)

    def _setup(self):
        from .desktop_setup_ui import SetupWindow
        SetupWindow(self)

    def _workspace(self):
        from .desktop_workspace_ui import WorkspaceWindow
        WorkspaceWindow(self, source_text=self._last_answer or "")

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
                self._events.put(("result", action, result))
            except BaseException as exc:
                # Never display private exception messages, prompts or paths.
                self._events.put(("result-error", action, type(exc).__name__))

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
                    self.connection_text.set(
                        "Real local model active — rights/source lease verified at startup",
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
                elif event == "result":
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
                    if name == "turn":
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
                    elif name == "history":
                        records = result.get("messages", [])
                        for row in records:
                            role = str(row.get("role", "message"))
                            self._show(role.title(), str(row.get("content", "")),
                                       "you" if role == "user" else "jeeves")
                    else:
                        self._show("Jeeves session", status)
                        if name == "close":
                            self.session_text.set("No active session; create or resume")
                elif event == "result-error":
                    self._busy = False
                    self.connection_text.set("Native request held — disconnect required")
                    self._show(
                        "Native operation held",
                        name + " (" + str(payload) + "). Outcome may be uncertain. "
                        "No automatic retry. Preserve the displayed request ID.",
                        "warning",
                    )
                    if self._bridge is not None:
                        self._bridge.abort()
                self._controls()
        except Empty:
            pass
        self.after(75, self._pump)

    def _exit(self):
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
