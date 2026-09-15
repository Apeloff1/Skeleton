# Secret hygiene and credential rotation

Skeleton treats any credential committed to Git history, copied into an issue, or emitted into a build artifact as compromised. Deleting the visible line is not enough: the credential must be revoked or rotated at its provider.

## Preventive gates

The repository uses two complementary scanners:

1. `backend/scripts/check_secret_hygiene.py` scans repository text for high-confidence credential shapes without echoing secret values.
2. Gitleaks scans Git history with the repository policy in `.gitleaks.toml`. CI pins Gitleaks `8.24.3` and checks out full history.

Run the complete local gate before security-sensitive merges:

```bash
bash scripts/security/run-secret-scan.sh
```

The same full-history command is exposed as a manual pre-commit stage:

```bash
pre-commit run --hook-stage manual gitleaks-history --all-files
```

Normal commits continue to run the lightweight repository-native scanner so the developer loop does not depend on a locally installed Gitleaks binary.

## Confirmed exposure procedure

Do not paste the credential value into an issue, pull request, chat, CI log, commit message, or incident note.

1. **Revoke first.** Disable the exposed credential at the provider. If immediate revocation would break production, create a replacement, deploy it through the approved secret store, verify service health, then revoke the exposed value.
2. **Scope the exposure.** Identify the credential type, repository paths, commits, branches/tags, CI artifacts, packages, logs, and environments that may contain it. Record identifiers and timestamps, never the secret itself.
3. **Rotate dependent material.** Replace derived or paired credentials where compromise could allow reuse, including database passwords, signing keys, deploy tokens, webhook secrets, or refresh tokens.
4. **Remove the source.** Delete the credential from tracked files and replace it with an environment lookup or documented placeholder.
5. **Purge history when required.** If a real credential reached Git history, rewrite affected history with an approved history-rewrite tool, force-update only the required refs, and coordinate with collaborators before they resume pushes. Revocation remains mandatory even after a purge.
6. **Invalidate artifacts.** Delete or expire CI artifacts, generated bundles, caches, container layers, release archives, or package versions that embedded the credential.
7. **Audit provider activity.** Review provider access logs from the earliest possible exposure time through revocation. Escalate unexpected use as a security incident.
8. **Re-scan.** Run the repository-native scanner and the full-history Gitleaks gate. CI must pass before the remediation is considered complete.
9. **Document the remediation.** Record what type of credential was exposed, where it appeared, when it was revoked, what was rotated, what history/artifacts were cleaned, and the validation result. Keep actual credential values out of the record.

## Allowlist policy

Secret-scanner suppressions must be narrow, reviewable, and tied to a verified non-secret fixture. Prefer changing a synthetic fixture so that it is obviously fake rather than suppressing a detector.

A suppression is acceptable only when all of the following are true:

- the matched value cannot authenticate to any real service;
- the exception is scoped to the smallest possible path, rule, or fingerprint;
- the reason is documented beside the suppression;
- a regression test proves the exception does not suppress a second real credential on the same line or file;
- reviewers can understand the exception without seeing any private credential material.

Repository-wide regex exemptions, broad directory exclusions, and comments such as `# example` are not acceptable ways to silence a real finding.

## Storage rules

Real secrets belong in the deployment platform's secret store or an approved local environment file that is ignored by Git. Examples and documentation must use clearly synthetic placeholders. Application code should read credentials from environment/configuration boundaries and must not provide production-looking fallback values.
