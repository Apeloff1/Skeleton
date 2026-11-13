# Jeeves native mixed project-work source packages

A useful first-run coding assistant must often create a new supporting
module **and** change an existing entry point in one coherent task.
The previous native source-repair workflow required choosing either
`new-files` or `existing-edits` for a given SQLite-committed
answer. It could produce a pair of separate patches manually, but
could not demonstrate a single original reviewed project change.

The desktop now offers an explicit **`mixed-work`** source format.
It uses the same independently installed single local GGUF, same
principal-bound SQLite native chat session, same finite 1–3-turn
syntax-repair budget, same exact source-context SHA custody, and
same human-approved Git patch builder.

## One strict response, one project change set

The model is required to return one JSON object with this schema:

```json
{
  "schema": "jeeves.workspace.mixed-project-work.v1",
  "new_files": [
    {"path": "src/new_module.py", "content": "def answer():\n    return 42\n"}
  ],
  "existing_edits": [
    {
      "path": "src/app.py",
      "expected_sha256": "<64-char original SHA-256>",
      "replacement": "from .new_module import answer\n"
    }
  ]
}
```

The original `expected_sha256` MUST come from the operator's
independently reviewed exact source context, not a model guess.
The model is not permitted to inspect unselected project files.
One array may be empty, but both cannot be empty. The existing
source-specific guards still enforce up to 16 new files, up to 8
existing edits and up to 24 unique paths in an aggregate plan.
The actual native committed proposal stays under its 16 KiB
response ceiling.

## Operational workflow

1. Open **Generate source with bounded repair** in the desktop.
2. Select the trusted original project root, enter a concrete
   source-building goal and choose **`mixed-work`**.
3. To change existing files, enter exact relative paths in the
   optional source selection area and click **Review original SHA
   + full text**. The app descriptor-checks each file, showing
   actual bytes and SHA-256.
4. Approve up to three new model turns. The already-installed
   GGUF produces one strict mixed-work JSON response through
   the original private `turn` protocol and SQLite ledger.
5. The strict decoder rejects unknown fields, duplicate JSON
   keys, nonfinite tokens, unsupported source paths, executable
   or credential paths, oversize source, case-clashing new/edit
   destinations and contradictory original hash declarations.
6. Both parts of the model response are converted into the
   **existing independent reviewers**: new files must be absent,
   existing edits must match current pinned original inode and
   full SHA-256, and the original project root must be the same.
   The app does not trust a hash merely because the model wrote it.
7. The combined, deterministic `PortablePatchPlan` is checked
   with the existing non-executing Python/JSON/TOML structural
   gate. Unsupported formats remain `unverified` rather
   than silently passed.
8. On malformed source, the native repair loop can submit a
   **new** finite SQLite request with sanitized diagnostic codes.
   A native failure, changed original project file or uncertain
   SQLite outcome is held without automatically reissuing an
   earlier request ID.
9. On source-review success, the GUI offers **Open COMPLETE operator
   patch review**. Its mixed-work decoder separates the original
   new and existing subplans into the already built Git patch
   review panes. This does not approve them.
10. Read the full unified diff and enter **both complete source
    manifest and patch SHA-256** values before creating one NEW
    `0600` owner-private Git patch outside the project tree.
    Separate Git application, CI and release remain human-approved.

## What is not authorized

The model has no arbitrary filesystem reader, shell, network
endpoint, Git credentials, direct write grants or additional
providers. The typed mixed package is **inert text** before
review. No new checkout, commit, PR, branch or deployment is
created from the model response automatically. The source
manifest and final patch SHA-256 remain independent of the
model's own assertion.

The same offline source-only tests exercise real temporary
original file hashes, a successful mixed new+existing patch
in **one** native-commit receipt, a rejected fabricated old
SHA-256 followed by a separate approved repair, malformed
JSON and duplicate keys, security-path denials, syntax
rejection, and original source drift during an in-flight
native answer. Test-only model receipts cannot certify
actual GGUF hardware or quality.

Physical Windows 11/WSL2 installation, licensing, real
native inference and device pressure, full security gates
and release readiness remain separately held.
