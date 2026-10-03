# Incident Comms Runbook

Player-facing communication during incidents. Engineering owns the fix; Support + Live Ops own
what users hear and when.

## Severity

| Sev | Meaning | First post within | Update cadence |
| --- | --- | --- | --- |
| SEV1 | App unusable for most users (install fails, `app up` cannot start, data loss risk). | 15 min | every 30 min |
| SEV2 | Major feature broken or badly degraded for many users; workaround may exist. | 30 min | every 60 min |
| SEV3 | Minor feature broken or a small group affected. | same business day | on change |
| SEV4 | Cosmetic / docs. | none required | known-issues entry only |

Timings are the team's proposed targets, not a contractual SLA. Adjust with Live Ops.

## Roles

- **Incident lead (engineering):** owns diagnosis and fix; tells comms what is true.
- **Comms owner (Support/Live Ops):** writes and posts every user-facing update; never speculates past what the incident lead confirmed.
- **Scribe:** keeps a timestamped log in the incident issue.

## Flow

1. Open a GitHub issue titled `[SEVn] <short symptom>` and label it `incident` (create the label if missing).
2. Comms owner posts **Investigating** within the table target.
3. Move through **Identified -> Monitoring -> Resolved**, posting each.
4. Add or update the entry in [known-issues.md](known-issues.md).
5. Within 2 business days for SEV1/2, write a short user-facing postmortem (what happened, impact, what changed).

## Rules for wording

- Lead with impact in user terms ("installs fail on Windows"), not component names.
- Never promise a fix time unless the incident lead committed to it.
- Give a workaround in the first post if one is confirmed.
- Always end with when the next update will be.
- No blame, no internal agent or ticket names.

## Templates

**Investigating**
> We're looking into reports that <impact>. <Who is affected, if known>. Next update by <time, timezone>.

**Identified**
> We've found the cause of <impact> and are working on a fix. <Workaround: ... / No workaround yet.> Next update by <time>.

**Monitoring**
> A fix for <impact> is out. We're watching to confirm it holds. If you still see the problem, <action, e.g. update and rerun `python -m skeleton app check`>. Next update by <time>.

**Resolved**
> <Impact> is resolved as of <time>. Cause: <one plain sentence>. Thanks for your patience. If anything still looks wrong, reply to this thread or open a ticket.

**Postmortem (SEV1/2)**
> What happened / Who was affected and for how long / What we fixed / What we're changing so it doesn't repeat.
