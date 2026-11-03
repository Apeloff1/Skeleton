# Original NPC relationships

Studio A now supports reviewed, choice-earned NPC trust with deterministic
replay and bounded reachability proof. Trust cannot be granted by arbitrary
model text or a forged player session. Every relationship references a
canonical world, an authored cast actor, a real choice and a scene where
that actor is present. Score changes clamp to [-100,100]; reactions have
nonoverlapping score intervals and must each have a valid choice witness.

Workflow: create and approve world and cast; propose a relationship with
world-relationships propose; save the unapproved JSON source with --create;
inspect and review; approve with the exact expected digest and review note;
compile with the approved digest; independently verify the receipt and HTML.
The player command accepts only a replayable canonical choice trace.
The editor command writes a CSP-hashed offline JSON editing interface,
which can export unapproved source but cannot write or approve.

Jeeves exposes read-only world.relationships_preview and
world.relationships_propose_preview typed tools. The model cannot persist
or approve content. The browser player uses DOM textContent, blocks all
network access, and embeds escaped canonical JSON. The artifact receipt
binds the exact world, cast, relationships, proof and playable bytes.
No device or release certification is implied.

The verified playable embeds the approved original cast alongside trust rules, displays
cast dialogue only when its canonical earned flags are present, and overlays the
relationship reaction for the same actual scene and player choice trace.

The player-slot CLI command and read-only world.relationships_player Jeeves
tool load the canonical SessionStore slot, independently replay every stored
choice and verify the session source lease before deriving NPC trust. Forged
flags, endings, revisions or cross-world sessions fail closed. No model write.
