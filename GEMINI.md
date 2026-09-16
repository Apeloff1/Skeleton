# Gemini repository instructions

Use `AGENTS.md` as the authoritative repository contract.

For build-affecting work: run `make repo-intel`, read current build/gap/security notes, select explicit IDs from `repo-intel/batches.json`, preserve canonical contracts, and add/update a `repo-intel/notes/` handoff note with validation plus security/quality/dependency effects. Run `make repo-intel-check` before handoff.

CI enforces the note requirement independently of model behavior. Treat capability discovery as structural evidence only; readiness and SOTA claims require explicit benchmark/eval evidence.
