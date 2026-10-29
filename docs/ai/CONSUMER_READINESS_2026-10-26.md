# Installed application qualification — 2026-10-26

The application was installed on a Linux verification VM. Service health, chat,
public capture and a bounded original-world training workflow were observed.
AI-generated HTML games failed browser execution, and a later AI repair was
rejected. Consumer release, dependency security and enterprise qualification
remain open.

The observations below describe the candidate on
`codex/consumer-runtime-readiness-2026-10-25` and
[PR #4283](https://github.com/Apeloff1/Skeleton/pull/4283). The
[October 23 report](CONSUMER_READINESS_2026-10-23.md) remains historical.

## Installed services and model

The VM had two CPU cores, an 8-GiB memory limit and a 32-GiB filesystem. The
production frontend, backend, canonical AI engine and authenticated MongoDB
7.0.41 used existing accounts, private configuration and data volumes. The
engine and backend ran read-only as UID 10001; the frontend ran as UID 101.

The final engine and backend source was commit
`99a75ea8f0eab60c44f89cbfdfab7f33a71d163c`. The frontend image was built at
`704fd3594d75fa99c872d358d7f1123eb314aab6`, with its tracked source equivalent
at the later installed head.

| Service | Installed image SHA-256 |
| --- | --- |
| Engine | `49dc9c19f5abd5b0e242611e4519584b293082ba4e6200a84f55ac41158b3431` |
| Backend | `904911fb177ac84097ba45c85820d28493430944b599ffe6db4c8c383c8c75a2` |
| Frontend | `fb3b4b49a7681ac2692d84ba40ac7842050cd88eca2ff3cd9c2a74361d153fc9` |

Source-to-image checks matched 102 engine files, 242 backend files and the
production Nginx configuration. All services were healthy. The supported
ten-second idle doctor exited successfully, with critical routes ready, no
missing modules and no suggested next steps. A separate three-second observation
during model startup timed out and was not counted as a pass. At the final idle
observation, model admission had no active or queued work, no native model process
was running, approximately 2.96 GiB of disk remained and no OOM event was observed
in the session. These are finite observations on one VM, not an SLA.

The installation explicitly selected the optional official
`Qwen2.5-Coder-1.5B-Instruct-Q4_K_M` profile as its sole local primary. Its
1,117,320,768 bytes matched SHA-256
`cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046`.
The pinned llama.cpp b11429 runtime was reused, and the old chat model directory
was preserved. Sequential use of two models does not establish automatic routing
or independent reviewers. See the [coding profile guide](LOCAL_CODING_PROFILE.md)
and [first-install setup](FIRST_INSTALL_AI_AND_CRAWLER.md).

## Observed workflows

- Chromium completed application entry and owner login. A real local-model chat
  turn survived reload. Model inventory, setup, chat, crawler consent and project
  forms were usable at a 390-pixel viewport.
- Normal and four-stage reviewed conversations survived container replacement.
  Exact replay preserved operation, execution and provider receipt identities
  without creating messages or advancing the conversation version. Another
  account was denied access. These stages do not prove independent model weights.
- An original saved maze produced a rendered frame and positive transitions under
  human controls and its retained AI policy. A bounded training run completed two
  episodes, 32 Q-value updates and 32 held-out evaluation transitions. Source
  export matched its recorded digest; an incompatible policy was rejected.
- The CLI compiled an original Godot project and ran Godot 4.6.3 with a required
  headless playtest. It reported `CORE_LOOP_OK` for one top-down shooter round.
  The deterministic compiler made no model call; commercial assets, complete
  input-driven play, multiplayer and store packaging remain unqualified.
- An authorized public capture retained one document and its provenance using two
  requests and 1,154 bytes. The owner could inspect the source; another account
  received 404 and an anonymous request received 401. The capture remained
  unreviewed and did not authorize publication or model-weight training.
- The installed Nginx image passed missing-backend DNS startup and recovery,
  forwarding and backend replacement at another IP without a frontend restart.
  Private HTML previews used authenticated bounded fetches and isolated scripts
  from application credentials.

## Installation and inference repairs

Authenticated private generation initially failed before inference because
middleware classified it as legacy traffic. Audited private route prefixes now
use the existing studio domain, preserving public and unknown-route limits. A
separate result-contract defect rejected 4,487 bytes of generated content at a
2,048-character reference limit. Generated output now has a bounded four-MiB
outer limit; identifiers and smaller aggregate, storage and transport limits
remain in place. Runtime regressions cover finalization, SQLite reopen and exact
replay. Rollback must retain a decoder compatible with stored long results.

The local CLI adapter previously flattened instructions and conversation history
into text which native conversation mode wrapped as one user message. For the
two exact pinned profiles, the corrected adapter supplies real system, history
and user roles with one assistant prefix. Validated structured-output schemas and
tool protocol are visible in the system frame. Reserved role-control tokens are
rejected before dispatch. Custom and raw profiles retain their previous behavior.
The corrected profile uses binary-file input to preserve the prefix newline and
disables the second conversation wrapper. Its prompt-format version enters the
existing execution-profile digest, preventing reuse of incompatible cached output.

An installed, model-free probe confirmed the coding profile's role and schema
framing. The focused native, deployment and provisioning batch passed 112 tests.
A separate 20-test provisioning batch, which overlaps that batch, included a real
`python -S` help invocation to verify that bootstrap help does not require installed
application dependencies. These checks do not establish creative quality.

The previous finite poll count could expire before a 414-second repair completed.
Poll cadence now spans the configured execution deadline. The UI retains an
acknowledged generation or repair job, pauses observation on reload and resumes
that same job without another generation submission. Private preview fetches clear
on account changes and remain scoped to the owner.

Runtime repair requests bounded inert literal edit proposals. The server binds the
source digest, limits the response and edit sizes, validates anchors and applies
the complete plan only after owner, lifecycle, source and version checks. The
observed request allowed one model turn and 1,024 output tokens. AI review scores
and `ship` verdicts remain advisory: a changed source invalidates old reviews and
a model score cannot establish runtime verification or release qualification.

## Actual generated-game outcomes

Before the prompt correction, a coding-model document repair removed needed
definitions. A fresh coding generation reached private preview but had missing
Play controls, reassignment errors, no animation frames and broken input. Static
HTML closure and the model's score did not establish playability. No manually
edited game was substituted as AI output.

An earlier literal repair returned eight identical no-op edits. The application
rejected `literal_patch_no_change`, preserving the original source. After the
prompt correction was installed, job `eb7ce6397aa844e7a4dd65641121b454` completed
one model turn with one provider receipt and a 777-byte JSON proposal. The
application rejected `literal_patch_duplicate_edit`; `repaired` remained false
and the original source was preserved. Its starting SHA-256 was
`7ddefe34b5f5a131b9fd3075acaba3a2f2535fcde0b4cc33e5735db845b6279e`.
The native process drained. No accepted post-fix candidate was available for a
new browser gameplay observation, so generated-game playback remains unverified.

## Verification and release gates

Architecture, construction, capability-interface, provider-bootstrap, enterprise
contract consistency, dossier and file-tree ownership checks passed for the
prompt-fix runtime. The governed file tree reported 182 mappings. Focused backend,
UI, local inference, storage and native-control batches also passed during this
installation pass. Overlapping batches are not a unique aggregate.

The broader historical campaign recorded 52,149 passes, 2,674 failures, 269 errors
and 215 skips across 4,442 files. It is not an all-green result and does not
qualify the final head as a complete repository pass.

The reviewed `http-cache-semantics@4.3.0` compensating-control verifier passes, but
the separate published-version advisory gate remains failed. Official metadata
observed on October 26 listed `node-forge@1.4.0` as latest and
[GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv) as an
active high-severity advisory with no published patched version observed. The old
braces advisory was withdrawn while the offline snapshot remained stale. See the
[dependency status report](../qa/DEPENDENCY_STATUS_2026-10-25.md) for exposure and
evidence limits.

The legacy GameForge governed-export adapter returns an explicit 503 because its
remote artifact-delivery RPC is undeclared. The separately observed Studio source
export does not certify that path. The VM had no approved native console core;
cores, content, firmware and toolchains remain separate prerequisites. Windows and
macOS native builds, arbitrary-ROM understanding and universal console compatibility
were not qualified on this VM.

Bounded numeric learning and retained lessons do not demonstrate automatic
transformer weight training, model promotion or improvement over commercial games.
This record advances no consumer-release, enterprise, security, production or
universal-console signoff.

Operator evidence under the October 26 scratch directory retains source parity,
test results, model lineage and browser observations. Private configuration,
credentials, raw requests and game source are not included in this report. Failed
observations remain evidence even if a later attempt succeeds.
