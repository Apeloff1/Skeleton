"""Explicit source discovery and bounded excerpt attachment for Jeeves.

The model cannot access this search UI, select source files or gain filesystem
tools. A human chooses a trusted project root, runs a finite descriptor-based
search, reviews exact UTF-8 snippets and explicitly attaches selected bytes to
one local prompt. The search runs off the Tk event loop.
"""
from __future__ import annotations

from hashlib import sha256
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_attachments import (
    DesktopAttachment, DesktopAttachmentHold,
    MAX_ATTACHMENT_COUNT, MAX_ALL_ATTACHMENT_BYTES,
)
from .desktop_workspace_index import (
    DesktopSearchHold, SearchLimits, SearchReport, search_workspace,
)


class SourceSearchWindow(tk.Toplevel):
    """Read-only, operator-selected code excerpts. Never a tool grant."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Jeeves — Private Local Source Search")
        self.geometry("1040x760")
        self.minsize(800, 610)
        self.parent_ui = parent
        self.protocol("WM_DELETE_WINDOW", self._exit)
        self.root_path = tk.StringVar(value="")
        self.query = tk.StringVar(value="")
        self.status = tk.StringVar(value="No project source has been scanned")
        self._queue: Queue = Queue()
        self._epoch = 0
        self._closed = False
        self._busy = False
        self._report: SearchReport | None = None
        self._build()
        self.after(75, self._poll)

    def _build(self):
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=2)
        frame.rowconfigure(4, weight=3)

        controls = ttk.LabelFrame(frame, text="Explicit local search — no model access", padding=8)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Trusted project directory").grid(
            row=0, column=0, sticky="w",
        )
        ttk.Entry(controls, textvariable=self.root_path).grid(
            row=0, column=1, sticky="ew", padx=6, pady=4,
        )
        ttk.Button(controls, text="Browse", command=self._browse).grid(
            row=0, column=2,
        )
        ttk.Label(controls, text="Search source terms").grid(
            row=1, column=0, sticky="w",
        )
        query = ttk.Entry(controls, textvariable=self.query)
        query.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        query.bind("<Return>", self._search_key)
        self.search_button = ttk.Button(
            controls, text="Search read-only", command=self._search,
        )
        self.search_button.grid(row=1, column=2, sticky="ew")
        ttk.Label(
            controls,
            text=(
                "Search is bounded to 96 directories, 1,024 eligible files, "
                "16 MiB of content, 6 levels, 30 results and 15 seconds. "
                "Partial results are identified. No symlinks or hidden "
                "credential/control directories are followed."
            ), wraplength=900,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        ttk.Label(
            frame, text="Source matches — select a hit to inspect exact hashed bytes",
        ).grid(row=1, column=0, sticky="w")
        results = ttk.Frame(frame)
        results.grid(row=2, column=0, sticky="nsew", pady=(5, 8))
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        self.matches = ttk.Treeview(
            results,
            columns=("source", "lines", "score", "digest"),
            show="headings", selectmode="browse",
        )
        for key, label, width in (
            ("source", "Project-relative source", 420),
            ("lines", "Lines", 90),
            ("score", "Rank", 70),
            ("digest", "File SHA-256", 330),
        ):
            self.matches.heading(key, text=label)
            self.matches.column(key, width=width, stretch=key == "source")
        self.matches.grid(row=0, column=0, sticky="nsew")
        self.matches.configure(yscrollcommand=lambda *args: scrollbar.set(*args))
        scrollbar = ttk.Scrollbar(
            results, orient="vertical", command=self.matches.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.matches.bind("<<TreeviewSelect>>", self._show_selection)

        ttk.Label(
            frame, text="Source-exact preview — read-only, never executed",
        ).grid(row=3, column=0, sticky="w")
        self.preview = ScrolledText(
            frame, wrap="none", height=12, state="disabled",
            font=("TkFixedFont", 10),
        )
        self.preview.grid(row=4, column=0, sticky="nsew", pady=(5, 8))

        bottom = ttk.Frame(frame)
        bottom.grid(row=5, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(
            bottom, textvariable=self.status, wraplength=820,
        ).grid(row=0, column=0, sticky="w")
        self.attach_button = ttk.Button(
            bottom, text="Attach selected exact snippet to next prompt",
            command=self._attach,
        )
        self.attach_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self._set_buttons()

    def _browse(self):
        if self._busy:
            return
        selected = filedialog.askdirectory(
            parent=self, title="Choose the trusted source project root",
        )
        if selected:
            self.root_path.set(selected)
            self._invalidate()

    def _invalidate(self):
        self._epoch += 1
        self._report = None
        for key in self.matches.get_children():
            self.matches.delete(key)
        self._preview("")
        self._set_buttons()

    def _preview(self, text: str):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _set_buttons(self):
        self.search_button.configure(
            state="disabled" if self._busy else "normal",
        )
        self.attach_button.configure(
            state="normal" if (
                not self._busy and self._report is not None
                and bool(self.matches.selection())
            ) else "disabled",
        )

    def _search_key(self, event=None):
        self._search()
        return "break"

    def _search(self):
        if self._busy:
            return
        root = self.root_path.get()
        terms = self.query.get()
        self._invalidate()
        epoch = self._epoch
        self._busy = True
        self.status.set("Searching pinned local source descriptors…")
        self.progress.start(75)
        self._set_buttons()

        def work():
            try:
                report = search_workspace(root, terms, limits=SearchLimits())
                self._queue.put(("report", epoch, root, terms, report))
            except BaseException as exc:
                # The canonical source guard can expose private paths in
                # messages, so only the exception *class* reaches the GUI.
                self._queue.put((
                    "held", epoch, root, terms, type(exc).__name__,
                ))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, epoch, root, query, data = self._queue.get_nowait()
                if (
                    epoch != self._epoch
                    or root != self.root_path.get()
                    or query != self.query.get()
                ):
                    # A result from changed inputs has no attachment authority.
                    self._busy = False
                    self._report = None
                    self.status.set(
                        "Search inputs changed; search again before attaching",
                    )
                    self.progress.stop()
                    self._set_buttons()
                    continue
                self._busy = False
                self.progress.stop()
                if kind != "report":
                    self._report = None
                    self.status.set(
                        "Local source search held: " + str(data)
                        + " — no files attached",
                    )
                    self._set_buttons()
                    continue
                self._report = data
                for index, hit in enumerate(data.hits):
                    self.matches.insert(
                        "", "end", iid=str(index),
                        values=(
                            hit.relative_path,
                            str(hit.line_start) + "–" + str(hit.line_end),
                            hit.score,
                            hit.file_sha256,
                        ),
                    )
                self.status.set(
                    data.status + " · scanned "
                    + str(data.scanned_files) + " source files / "
                    + str(data.scanned_bytes) + " bytes / "
                    + str(data.scanned_directories) + " directories · "
                    + str(len(data.hits)) + " matching excerpts · denied "
                    + str(data.denied_entries)
                )
                self._set_buttons()
        except Empty:
            pass
        self.after(75, self._poll)

    def _selection(self):
        if self._busy or self._report is None:
            raise DesktopSearchHold("run an authorized source search first")
        selected = self.matches.selection()
        if len(selected) != 1:
            raise DesktopSearchHold("explicitly choose one source match")
        index = int(selected[0])
        if not 0 <= index < len(self._report.hits):
            raise DesktopSearchHold("unrecognized source excerpt identity")
        return self._report.hits[index]

    def _show_selection(self, event=None):
        try:
            hit = self._selection()
        except (DesktopSearchHold, ValueError):
            self._set_buttons()
            return
        self._preview(
            "SOURCE: " + hit.relative_path
            + "\nBYTES: " + str(hit.start_byte) + "–" + str(hit.end_byte)
            + " · LINES: " + str(hit.line_start) + "–" + str(hit.line_end)
            + "\nFILE SHA-256: " + hit.file_sha256
            + "\nEXCERPT SHA-256: " + hit.excerpt_sha256
            + "\n\n" + hit.excerpt,
        )
        self._set_buttons()

    def _attach(self):
        try:
            hit = self._selection()
            target = self.parent_ui
            if len(target._attachments) >= MAX_ATTACHMENT_COUNT:
                raise DesktopAttachmentHold("maximum local source snapshots reached")
            existing = sum(x.byte_count for x in target._attachments)
            raw = hit.excerpt.encode("utf-8", "strict")
            if existing + len(raw) > MAX_ALL_ATTACHMENT_BYTES:
                raise DesktopAttachmentHold("bounded local prompt source budget exceeded")
            if sha256(raw).hexdigest() != hit.excerpt_sha256:
                raise DesktopSearchHold("excerpt changed since descriptor read")
            # DesktopAttachment names are only a display identity, never a
            # physical filename or implicit permission to reopen a path.
            # A bounded hash label avoids long/Unicode basenames becoming
            # unsafe filenames; the UI separately shows source-relative path.
            path_hash = sha256(hit.relative_path.encode("utf-8", "strict")).hexdigest()
            label = (
                "source_" + path_hash[:12] + "_"
                + hit.excerpt_sha256[:16] + ".txt"
            )
            attachment = DesktopAttachment(
                name=label, sha256=hit.excerpt_sha256,
                byte_count=len(raw), content=hit.excerpt,
            )
            if any(
                x.sha256 == attachment.sha256 and x.name == attachment.name
                for x in target._attachments
            ):
                raise DesktopAttachmentHold("source excerpt already attached")
            target._attachments.append(attachment)
            target.attachment_text.set(
                str(len(target._attachments)) + " exact source snapshot(s) · "
                + ", ".join(x.name for x in target._attachments)
            )
            target._show(
                "Explicit project source attached",
                hit.relative_path + " · lines " + str(hit.line_start)
                + "–" + str(hit.line_end)
                + " · SHA-256 " + hit.excerpt_sha256[:16],
            )
            self.status.set(
                "Selected bytes attached to local prompt memory; "
                "not sent to the native model until you explicitly press Send",
            )
        except (DesktopSearchHold, DesktopAttachmentHold, ValueError) as exc:
            self.status.set("Source attachment held: " + type(exc).__name__)

    def _exit(self):
        self._epoch += 1
        self._closed = True
        self.destroy()


__all__ = ["SourceSearchWindow"]
