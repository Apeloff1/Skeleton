# Game Studio build/release source lifecycle — post milestone DX-84

The source build path now has three distinct, traceable layers:

1. **Generate actual original game assets:** use installed Game Studio
   editor schemas, strict advanced scene contracts, original source
   compiler, Godot and offline-browser source output, multi-seed portfolios,
   the installed typed Universal Forge, or canonical original story source
   authoring. The original-game simulator can produce actual winning proofs.
2. **Sign, review and accept:** all source candidates become canonical
   GameWorkspace proposals under current selected original project.
   Human review includes untruncated diffs and separate SHA-256 authorizations
   per source. Existing \`GameWorkspace.commit\` alone publishes approved
   source changes. Forge and story validators rerun before acceptance.
3. **Verify and deliver source:** accepted original release members must
   all match the exact original dual-runtime manifest, individual source
   acceptance records and originating source-proposal SHA-256 hashes.
   Actual accepted sources can be deterministically recompiled and their
   Python winning gameplay replay re-executed. Byte-identical new HTML/Godot
   source output is compared against committed source, then an exact-hash,
   user-authorized ZIP is generated in memory, downloaded, and hash-verified
   in the browser.

The source ZIP is a **portable Godot project and standalone browser source
bundle**. It is not an executable installer, hardware-certified native app,
OS/platform store approval, or commercial rights acceptance.

The existing \`JeevesAppwideRuntime\` properly passes \`project\` as a
separate selected authority selector to \`dispatch_app_action\`, not as
one of the canonical exact typed action arguments. This restores ordinary
runtime actions including \`forge.kinds\`, \`forge.graph\`,
\`game.compile.native\`, \`companion.simulate\`, \`tool.fabric\`
and more without broadening permissions.

No tests executed during the requested build-only milestone workpass.
