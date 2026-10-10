# Player Support Kit

Owner: Player Support Lead (Nac), with Live Ops for incident comms.

This folder is the support-facing layer for the Skeleton standalone AI app. It does not change
runtime behaviour; it tells support staff and operators how to talk to users when something
breaks, and how to route problems to the right engineering owner.

| Doc | Use it when |
| --- | --- |
| [incident-comms.md](incident-comms.md) | Something user-visible is degraded or down and you need to post status. |
| [macros.md](macros.md) | Replying to a user ticket with a common problem. |
| [troubleshooting.md](troubleshooting.md) | Walking a user or operator through first-line diagnosis. |
| [known-issues.md](known-issues.md) | Checking whether a report is already tracked before filing a new issue. |

Source of truth for commands is the root [README](../../README.md) and
[APP_ASSEMBLY.md](../APP_ASSEMBLY.md). If a command here disagrees with those, they win;
fix this folder.
