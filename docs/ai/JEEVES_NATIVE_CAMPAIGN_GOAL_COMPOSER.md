# Compose real local Jeeves coding campaigns from original task goals

The Jeeves advanced desktop now supports a **goal-to-native campaign composer**
above the existing canonical GGUF/SQLite and source-custody pipeline. This is
a local, read-only **build tool** for assembling 1–12 operator-written coding
goals into exact original-source SHA-bound native jobs. It does not call a
generative provider, generate source, import any produced code, or write the
project. The actual model remains the independently installed GGUF runtime
and all real effects remain separately approved.

## Owner flow

1. Open **Jeeves → Advanced native coding campaign → Compose tasks from
   original goals**. The composer prefills current visible *installed model*
   settings and budgets from the parent desktop workbench. The private
   project/source paths are **blank** rather than guessed.
2. Specify the original project root, existing owner-private 0700 output
   directory, journal name, original coding goals, ordered task IDs,
   dependency IDs, output name for each task and optional original source
   filenames. Do not enter token secrets.
3. Press **BUILD & INSPECT PRIVATE NATIVE CAMPAIGN (NO MODEL)**. Jeeves reads
   selected original source through the canonical descriptor-anchored
   source reader, computes each exact source snapshot SHA, then calls the
   existing **read-only** native source inspector to derive the job SHA.
   After a second original source recheck, it constructs the strict native
   `generate` request with those exact digests—without executing it.
4. The composer revalidates the **whole** campaign with the existing native
   parser: current model/SQLite/project principal, task dependency DAG
   order, cumulative tokens/time/attempts, all output target names and
   an existing private 0700 parent. No directory or journal is created.
5. The full result is inserted into the private campaign editor in the
   parent window. The generated task goals and original paths are shown
   only in that owner-controlled editor, **not** in public stdout, status,
   telemetry or GitHub CI. Any previous *RAM-only* preliminary approval is
   discarded.
6. Press **Inspect ORIGINAL campaign** in the parent window, review the
   manifest and source inventory, independently type the full campaign SHA
   and provide the three distinct explicit native/storage approvals.
7. When ready, run the existing real native campaign. Interruptions and
   missing privately saved source after a native attempt are **uncertain**.
   Never auto-retry. Use the source-audit and canonical SQLite owner to
   investigate before creating a newly approved campaign.

## Composer JSON schema

The local editor accepts exactly:

```json
{
  "schema": "jeeves.desktop.native-source-campaign-composer.v1",
  "project_root": "/home/owner/original",
  "private_dir": "/home/owner/private-campaign",
  "journal_name": "original-work.jeeves-campaign.jsonl",
  "model_root": "/home/owner/installed-gguf",
  "state_dir": "/home/owner/private-sqlite",
  "tenant": "local",
  "subject": "owner",
  "context_tokens": 4096,
  "max_output_tokens": 1024,
  "threads": 4,
  "gpu_layers": 0,
  "inference_ms": 90000,
  "capacity_budget_bytes": 8000000000,
  "tasks": [
    {
      "task_id": "first",
      "depends_on": [],
      "goal": "Build an original bounded Python module",
      "format": "new-files",
      "maximum_attempts": 2,
      "source_paths": [],
      "target_name": "first.source.json"
    }
  ]
}
```

These sample paths are illustrative. The private output folder must already
exist with owner-only permissions, outside the original project, GGUF
installation and SQLite state trees. The original project must pass
the canonical trusted-source path checks. Source filenames are relative
to the original project and must be explicitly selected.

Supported task output formats use the existing native `FORMATS` registry.
`format`, `source_paths`, native GPU, token budgets, attempt count and
time limits are validated by the actual headless native parser; the
composer has **no alternate relaxed limit**. The campaign additionally
bounds its total native attempts, tokens, time, output paths and job count.

## Security characteristics

- No native inference during composition or preview.
- Strict canonical JSON, duplicate-key rejection, nonfinite rejection,
  bounded text, path and aggregate goal sizes.
- Two independent source snapshot checks before generating exact native
  job identities, followed by whole campaign source re-inspection.
- Fail-closed output collisions, traversal, malicious relative names,
  unauthorized task graph cycles, missing source, no-clobber destination,
  owner conflicts and resource oversubscription.
- Composer does not grant an instruction-writing model new FS/Git/process
  tools; real model/native/storage authorization remains a later step.
- No automatic continuous task generation, autonomous code application,
  source-code execution, release or hardware acceptance.

## Validation

```bash
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_campaign_composer.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_campaign_operator.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_*.py' -v
python -m compileall -q skeleton/ai/runtime/operational_ai/laptop_runtime
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Live GGUF model rights, physical device, Windows 11 native paths, WSL2
integration, end-to-end source code execution and full application release
remain separately unverified. Preserve mandatory exact-head CI/secret,
software supply-chain, merge and release holds.
