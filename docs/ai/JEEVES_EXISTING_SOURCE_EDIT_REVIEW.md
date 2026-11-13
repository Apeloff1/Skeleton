# Jeeves existing-file change review — safe candidate delivery

The offline Jeeves desktop now supports proposals for **existing** source
files, in addition to new-file creation and read-only project search.

The model remains an untrusted proposer. It cannot invoke filesystem tools,
overwrite or truncate files, execute code, change Git metadata, run the shell,
delete previous versions, or grant itself new permissions. The existing-file
workflow writes only a **new inert sibling candidate** after explicit human
approval; applying it to the original source is intentionally a separate
human-controlled editor or version-control action.

## Use

1. In **Search project sources**, inspect the current project file and copy
   its whole-file SHA-256. Select/attach relevant source excerpts to a prompt.
2. Enter the required edit task and click **Insert existing-edit format**.
   Jeeves is instructed to return one strict JSON manifest describing each
   existing path, its exact expected SHA-256 and the **complete replacement
   UTF-8 content**. It is not authorized to perform the edit itself.
3. After an actual local model answer has committed, choose **Review
   existing-file edits**. The answer appears as untrusted, editable JSON.
4. Select the existing trusted workspace root. Click **Inspect checked
   source changes**. The desktop opens originals by descriptor, verifies
   owner, mode, inode, size and content SHA-256, then displays unified diffs
   and the original/replacement full hashes.
5. Select **one** change, read its diff and type/paste the full replacement
   SHA-256 into the approval field. Click **Stage NEW candidate only**.
6. The publisher checks the exact reviewed plan, root descriptor identity,
   original inode, original content and metadata again. It creates a random
   0600 staging file and atomically publishes a distinct inert sibling
   `.jeeves-edit-candidate-<digest>.txt` with Linux
   `renameat2(RENAME_NOREPLACE)`. It fsyncs the result and re-hashes the
   candidate before returning a single-file receipt.
7. Inspect the candidate and apply the approved content separately with
   your own editor/Git workflow. The original file remains untouched by
   this module.

### Example proposal

```json
{
  "schema": "jeeves.workspace.existing-file-edits.v1",
  "files": [
    {
      "path": "src/example.py",
      "expected_sha256": "a_full_64_character_sha256_of_the_original",
      "replacement": "def hello():\n    return 'private offline jeeves'\n"
    }
  ]
}
```

The digest above is explanatory placeholder text, not a valid expected
hash. Real proposals must include the actual full lowercase SHA-256; a
different source, changed task or missing current file is rejected.

## Source custody rules

- Up to 8 existing-file changes; 64 KiB per original and replacement;
  192 KiB aggregate replacement; finite 256 KiB proposal envelope.
- Only the existing source allowlist extensions and safe relative paths
  beneath operator-owned trusted directories are eligible. Git/CI/IDE,
  credentials and hidden control directories remain denied.
- Every original must be a regular, singly linked file owned by the local
  operator, without group/other writable permissions. All parent paths
  are descriptor-anchored and symlinks are denied.
- Read-only preview stores immutable original/replacement hashes and root
  device/inode. Changing UI source JSON, the selected root or an original
  file invalidates publication.
- One exact source candidate is atomically published into a NEW pathname
  in the same original directory. Existing source paths are not rename
  destinations. A preexisting candidate causes a hold, not an overwrite.
- An exhausted disk, short write, moved parent or changed source holds the
  operation. Only the operation's random staging file may be cleaned on
  failure; an uncertain committed candidate must be inspected manually,
  never silently retried.
- No multi-file atomic transaction and no automatic application to original
  sources are claimed. Each selected file needs its own full digest approval.

## Why a separate candidate?

Linux atomically replacing a pathname is not the same as conditionally
replacing it **only if its inode/content still matches** when unrelated,
non-cooperative programs may rename files concurrently. To avoid hiding
that race, this baseline creates new, non-executable, no-clobber proposals,
and leaves the final merge into an existing file under explicit operator
control.

The desktop's model/runtime rights, SQLite principal binding, native
source fence, agent budgeting and work-order journal are independent
preconditions to using a real local GGUF. Source-only tests are not device
qualification or release certification.
