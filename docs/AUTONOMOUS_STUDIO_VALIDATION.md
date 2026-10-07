# Autonomous Studio validation

Autonomous Studio has two separate validation layers: a deterministic offline smoke gate for control-plane changes and the credential-free validation phase inside each scheduled night shift.

## Pull-request smoke gate

`.github/workflows/autonomous-studio-smoke.yml` runs when Studio control-plane code or Studio tests change. It intentionally receives no OpenAI or GitHub mutation credentials.

The gate verifies:

- the Studio registry still contains exactly 1,000 stable logical workers;
- the Studio CLI imports and exposes its command surface;
- the automation package compiles under the pinned Python runtime;
- planner output can be parsed into a bounded registered-division task;
- a scripted builder proposal remains inside its planned path boundary;
- the selected builder and senior reviewer are independent worker identities;
- explicit reviewer rejection fails closed;
- the existing registry, director, and report regression suites remain green.

The scripted reasoner returns local `ReasoningResult` objects and never performs a network request. This makes the smoke gate safe to run on pull requests without exposing `OPENAI_API_KEY`.

## Scheduled-shift validation

A real scheduled or manually dispatched night shift may use `OPENAI_API_KEY` only during bounded proposal generation. If a patch is accepted by the model-side reviewer, the exact patch is sealed and then executed through repository validation with `OPENAI_API_KEY`, `GH_TOKEN`, and `GITHUB_TOKEN` blanked. The working tree is reset after generated-code execution, the sealed hash is verified, and only that exact reviewed patch is restored before publication.

## What the smoke gate does not prove

The offline gate does not claim that an external model endpoint is reachable or that a particular generated engineering patch is correct. Those properties are intentionally separated: API availability is fail-closed at proposal time, and generated patches still require the normal repository CI/security checks before merge.
