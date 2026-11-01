# Offline source-leased quest structural editor

Studio A's original quest structural editor is a working, browser-offline
authoring surface for the typed structural edit compiler. It is not a static
mockup: it exports a bounded JSON edit batch with project and baseline source
leases, and the CLI imports that export, recompiles the **entire quest graph**,
replays the candidate, and can persist a new immutable private compilation.

Render HTML from a source-verified baseline:

`python -m scripts.studio_quest_structural_editor_cli --baseline-dir OLD
--expected-baseline DIGEST --render-html`

Or publish it exclusively into an existing private directory using
`--publish-editor DIRECTORY`. The editor embeds a SHA-256 CSP hash for its
single script, blocks network connections, external scripts, forms, frames,
objects and other active content, and escapes the original authored prompt.
It does not silently execute or save model output. The operator edits a typed
JSON batch and clicks **Export typed edits**.

Move the browser-exported JSON into a private directory and set file mode 0600
before importing (the browser's Downloads directory is not assumed private).
Use `--import-export PATH --publish-candidate NEW_PRIVATE_DIRECTORY` with
the same baseline lease. Import refuses symlinks, hardlinks, non-private files,
changed-in-flight files, duplicate JSON keys, nonfinite numbers, stale or forged
source leases, unauthorized requests, invalid edit schemas, and broken quest
graphs. The original baseline remains immutable.

After the new private compilation is written, run the Studio A
`studio_quest_regression_matrix` review against the old and new compilations,
then the prompt quest playtest for sandbox ending witness handoff. This is not
a native engine, originality/rights or release certificate.
