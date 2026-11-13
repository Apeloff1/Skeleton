# Jeeves workspace source delivery — explicit approval, no overwrites

This is a **real local code-file delivery capability** for the offline native
desktop. The model generates a proposed *data manifest*. A human reviews it,
selects a trusted local project directory, confirms each exact SHA-256 and
chooses whether to publish one new source file. Model text has no filesystem
tool authority and cannot create or overwrite anything by itself.

## Generate a proposal from local Jeeves

In the desktop window, write the requested task, choose **Insert source
proposal format**, and send it through the already source-checked local GGUF.
The model may produce something like:

```json
{
  "schema": "jeeves.workspace.new-files.v1",
  "files": [
    {
      "path": "src/example.py",
      "content": "def hello():\n    return 'offline'\n"
    }
  ]
}
```

That output is **untrusted** until separately reviewed. Source code is never
executed when parsing, reviewing or publishing.

Choose **Review Jeeves file proposal**. The window loads the last committed
answer into an editable proposal panel, but does **not** parse, publish, or
apply it automatically. Select an existing trusted local workspace root and
press **Inspect proposed new files**.

The deterministic parser enforces a finite canonical schema, at most 16 new
source files, maximum 99 KB per file, roughly 192 KB aggregate and strict
UTF-8. It rejects duplicate JSON keys, case-colliding paths, dot/traversal
components, unsupported extensions and protected `.git` / workflow
destinations. Every proposed file is shown with path, size, SHA-256 and
`/dev/null` unified diff for review.

Only after selecting a particular file and entering its **full exact
SHA-256** does **Publish only selected NEW file** become eligible to invoke
the publisher. Each file needs its own explicit approval.

## Filesystem guarantees and limits

- A previously present destination is never overwritten, even if it appears
  after review. Publication uses Linux/WSL2 descriptor-anchored
  `renameat2(RENAME_NOREPLACE)`, not `os.replace` fallback.
- Every parent path is opened with `O_DIRECTORY | O_NOFOLLOW` beneath the
  reviewed workspace root. The root device/inode and owner/safe permissions
  are checked again immediately before publication.
- Source bytes are staged into a new random 0600 file in the **same parent
  directory**, fully written and fsynced, then atomically moved into the
  absent destination. Short writes and full disks are holds; only this
  operation's staging file is cleaned on failure.
- The new file is reopened and hashed before a single-file receipt is
  returned. If the post-write witness is uncertain, the operator must
  inspect the target manually rather than have Jeeves retry it.
- A proposal cannot create intermediate directories automatically; they must
  already exist and be trusted. The operator may review and publish multiple
  files separately, but **there is no multi-file atomic transaction** and no
  source execution or automatic Git commit.
- The selected workspace root and code content are never transmitted to
  hosted services or used as a model tool grant. Content is shown only in
  the local operator UI and staged locally on explicit approval.
- This module works on POSIX/WSL2 with the required no-follow descriptor and
  atomic no-clobber APIs. Native Windows filesystem publishing has not been
  qualified; the absence of safe primitives is a denial, not a fallback.

The code-generating native model still needs actual licensed installed weights,
clean Windows 11/WSL2 device qualification, native cancellation and full
release checks. A source delivery receipt proves **one exact local file
creation** only, not that generated code is correct, tested, secure or
release-ready.

## Never do this

Do not use a model output as authorization to overwrite old sources, execute
unknown scripts, create GitHub workflow files, inspect private credentials,
enable network fetching or merge unreviewed source changes. This workbench
does not provide those capabilities.

## Protected local control directories

Model-generated new-file proposals may not create paths in `.github`,
`.git`, `.ssh`, `.gnupg`, `.vscode`, `.idea`, or
`.devcontainer`, even if those files do not have executable extensions.
This prevents a source proposal from becoming a hidden future workflow,
editor or development-environment control instruction.
