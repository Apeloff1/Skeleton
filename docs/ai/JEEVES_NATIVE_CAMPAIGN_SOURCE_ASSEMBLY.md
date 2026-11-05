# Jeeves campaign source assembly — multi-task source output

## Operational improvement

A completed local GGUF coding campaign is no longer just a collection of
separate private model proposals. This stage turns actual **separately
committed canonical SQLite task outputs** into **one source-reviewed,
cross-file graph-checked, conflict-free original-code patch**.

The existing original tasks do not automatically share generated source
context or write the original project. Campaign dependencies prove
ordering only. The new assembly inspects all saved original model outputs,
not invented code, and requires each task's exact original source, target
SHA, private file SHA, model SHA and prior journal closure.

## Actual flow

1. Review each native task using the real native source inspector.
2. Run a 1–12 task operator-approved campaign with private escrow,
   durable intent-before-model journal, and independent escrow cold checks.
3. Run the campaign **cold verify** action. Failed, interrupted and
   uncertain attempts are not eligible for source assembly.
4. Run **assembly inspect** on the exact completed campaign. It reads
   each saved private `*.source.json` through pinned O_NOFOLLOW
   descriptors and recomputes source review against the current original
   project. It binds the original model, root inode and current source hashes
   for every task, and refuses cross-task output path collisions.
5. All distinct generated new/edit source entries are merged into a
   single canonical `PortablePatchPlan`, with a new full
   source-manifest SHA, Git patch SHA, original campaign audit event SHA,
   and **aggregate** Python import graph SHA. Imports across two tasks
   that were previously unverified can now be observed as actually
   linked source files. Unknown external imports remain unverified.
6. The operator must separately review the exact full three approval hashes
   (assembly, combined source manifest, combined Git patch) and choose
   exactly one manual output type:
   - `git-patch`: one inert no-clobber 0600 combined Git patch outside
     the original checkout, with a second independent cold byte verification
   - `private-stage`: one new 0700 owner-private tree holding the exact
     final changed/new source, with completion seal last and cold tree verify

The original project remains **read-only**, and Git is never invoked.
The model is never called during the assembly. The output is not
automatically installed, executed, merged or released.

## CLI

```bash
python scripts/jeeves_campaign_delivery.py < inspect.json
python scripts/jeeves_campaign_delivery.py --approve-git-patch < patch.json
python scripts/jeeves_campaign_delivery.py --approve-private-stage < stage.json
```

The strict JSON-stdin request has EXACTLY these fields:

```json
{
  "schema": "jeeves.desktop.native-campaign-source-delivery-cli.v1",
  "action": "inspect",
  "campaign": {
    "schema": "jeeves.desktop.native-source-campaign.v1",
    "action": "verify",
    "project_root": "/absolute/original-project",
    "journal_file": "/absolute/private/work.jeeves-campaign.jsonl",
    "manifest_sha256": "FULL_ORIGINAL_CAMPAIGN_SHA256",
    "recheck_original_source": true,
    "tasks": []
  },
  "output_kind": null,
  "destination": null,
  "assembly_sha256": null,
  "source_manifest_sha256": null,
  "patch_sha256": null
}
```

The `tasks` array above is a placeholder: the actual completed, original
1–12 task records and their native request SHA-256 values are REQUIRED.
Reuse the original unchanged campaign request from the execution stage,
set its action to `verify`, keep its approved manifest and set
`recheck_original_source` to true. Never edit task goals or source
contexts to impersonate earlier SQLite model calls.

For publication change outer `action` to `publish`, fill
`output_kind` with `git-patch` or `private-stage`,
`destination` with an absolute new private output (under an existing
owner-private 0700 directory), and the three full source approval SHA
values from the actual **assembly inspect**. Pass the corresponding,
mutually exclusive approval flag; inspection forbids both.

## Security and scope

- A campaign without a real complete source audit is **held**.
- A saved model source whose bytes, original source, SHA, owner/model
  or parser results changed is **held**.
- Overlapping source paths across tasks are **held** even if the
  generated contents are identical; no last-writer-wins model policy.
- A changed original project inode or source edit SHA is **held**.
- At most 24 distinct reviewed changes, one MiB of final replacement
  source, and the existing 786,432-byte bounded Git patch.
- Cross-task imports are re-analyzed by the existing canonical AST-only
  graph. Syntax errors or impossible relative import levels hold.
- Output uses existing source-owner private staging/patch publishers and
  separate independent cold validation, never model path permissions.
- No private task goal, model source content, absolute file path, prompt,
  generated source, secret or code-body is emitted into normal stdout.
- This does not prove generated code compiles/runs, that every external
  import is installed, that Git can apply the patch to every consumer
  device, that the model has valid rights, that a physical laptop passed
  native GGUF inference, or that a release is safe.

## Source qualification

```bash
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_campaign_delivery.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_native_campaign.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_*.py' -v
python -m compileall -q skeleton/ai/runtime/operational_ai/laptop_runtime
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Keep all draft, dependency, device, security and release holds until exact
final-head evidence is independently successful.
