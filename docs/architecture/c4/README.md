# C4 views

These views describe the system as it is wired today, plus the Projects contract at `/api/v1/projects` (`skeleton.projects.v1` version `1.1.0`).

| View | Question it answers |
|------|---------------------|
| [Context](01-context.md) | Who uses Skeleton, and which systems sit outside it? |
| [Container](02-container.md) | Which deployable processes and stores exist? |
| [Component](03-component.md) | How do kernel, agents, memory, GameForge, and the API depend on each other? |

Decisions that produced the layer check and the Projects schema are [ADR-0002](../../adr/ADR-0002-logical-layers-and-route-custody.md) and [ADR-0003](../../adr/ADR-0003-subsystem-and-projects-contracts.md).
