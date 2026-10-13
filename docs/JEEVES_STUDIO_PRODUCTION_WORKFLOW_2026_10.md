# Jeeves original Game Studio source production operator workflow

1. Select a current writable game project and scan Jeeves' appwide inventory.
2. Optionally describe desired systems via **Prompt-to-Working-Engine
   Authoring**; choose specific installed editor settings where appropriate.
3. Use **Multi-Engine Game Production** to generate typed system
   configurations, or (after human commitment of the systems) their actual
   original advanced scenes.
4. Use **Original Playable Browser & Godot Source Builder** to compile a
   deterministic, source-rendered playable game with proof. Use **Original
   Game Variants** for up to four distinct variants with separate world and
   manifest digests.
5. Review actual generated source proposals under **Durable Source Proposal
   Queue**. Open **Publish Reviewed Game Sources**, inspect whole untruncated
   unified diffs, then individually approve each candidate source by SHA.
6. Execute the explicitly authorized source commit, which delegates every
   file to existing \`GameWorkspace.commit\`. Files become actual original
   project contents. Interrupted multi-file commits return their committed
   prefix and require a fresh review for remaining sources.

No arbitrary code execution, model training, self-improvement or additional
provider authority is granted by any of these adapters. Gameplay proofs are
compiler-internal simulations and **do not certify real Godot execution,
installer behavior, cross-platform release or shipped product readiness**.

No tests were run in this build-only authoring workpass.
