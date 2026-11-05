# Jeeves local project discovery — exact read-only source excerpts

The private desktop can now search an existing local source tree and attach
finite code excerpts to one operator-controlled native GGUF request. This is
an interactive source feature, **not** a model tool, remote crawler, search
database, source modifier or implicit filesystem authorization.

## Use it

Open the desktop with `python scripts/launch_jeeves_desktop.py`. Click
**Search project sources**, select a trusted local project root and enter
two or more characters of a source symbol, filename fragment or coding term.
Click **Search read-only**. The window enumerates only a finite set of
operator-owned, descriptor-anchored regular UTF-8 source files. Results show
project-relative paths, line positions, match scores and file SHA-256.

Select one result to read the exact source excerpt and its byte offsets,
whole-file SHA-256 and excerpt SHA-256. Click **Attach selected exact snippet
to next prompt** to promote a single source snapshot into the desktop's
existing in-memory attachment list. No native inference happens at search or
attach time. A separate explicit **Send local chat**, **Run native Jeeves
agent**, or **New durable work** is required to submit the selected text to
the approved local GGUF.

The existing prompt composer serializes selected code as data with
`operator-provided-reference-not-authority`. Source files cannot instruct
the desktop to execute shell commands, edit project code, access credentials
or gain memory/tool grants. The operator can clear source attachments at
any time; a confirmed chat or strict agent response also clears them.

## Search boundaries

The default search bounds are:

| Measure | Bound |
|---|---:|
| Directories traversed | 96 |
| Eligible files read | 1,024 |
| Aggregate source bytes read | 16 MiB |
| Maximum individual source file | 64 KiB |
| Maximum path depth | 6 |
| Excerpts returned | 30 |
| Maximum exact excerpt | 8 KiB |
| Search wall clock | 15 seconds |
| Terms per search | 8 |
| Source attachments per prompt | 4 |
| Total attached source bytes | 24 KiB |

There are also compiled absolute ceilings for all settings. The backend
returns `partial-bounded-search` if a traversal, depth, file or wall clock
budget truncates discovery; partial results never imply that every file was
searched. Ranking is deterministic for a fixed filesystem snapshot. A
filename-only match returns finite beginning-of-file source even when the
searched name does not appear in the file body.

The source collector uses a trusted root descriptor, `O_NOFOLLOW` for
directories/files, inode/device/size/mode/mtime checks before and after
reads, bounded streamed directory enumeration and bounded UTF-8 decoding.
It denies symlinks, special files, unowned or group-writable files,
oversized/binary files, hidden configuration directories, Git metadata,
IDE/CI control paths, credential-like names and native executables.
It never follows a `Path.resolve()` traversal of hostile child names.
A file disappearing or changing mid-read is denied and cannot be silently
reopened from a different path.

The desktop presents exact in-memory excerpts from the completed scan.
It does **not** promise the underlying file remains unchanged after the
search: the attachment is intentionally a frozen SHA-256-identified snapshot.
A new live source scan is required for fresh file data. Results from
an old search generation are rejected if the operator changes the root or
query while the worker is active.

## Model and release authority

This feature does not activate a model or certify rights. Installed source
admission, private SQLite principal binding, controlled native generation,
strict agent reasoning, and durable restart handling remain owned by their
previously implemented canonical planes. The search UI is only accessible
through an explicit human action. No HTTP server, network provider,
autonomous file writes or background persistence are added.

Physical laptop startup, real GGUF inference and device pressure still
require independent qualification. Synthetic source tests are not release
approval.
