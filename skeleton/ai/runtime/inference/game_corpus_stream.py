"""Original game-creation corpus, streamed up to a byte budget.

The lines are written for this tree. They are not excerpts from commercial
games, manuals, or soundtracks. Held-out lines, including the English and
A-to-Z measurement sentences, are a filter and never a training target.
"""
from __future__ import annotations

import string
from collections.abc import Iterator, Mapping

BUDGET_BYTES = 199 * 1024 * 1024
WINDOW = 40
HOLDOUT_SERIAL = 10**12
# Rotating pass-id widths. Thirteen digits is the holdout width; those two ids stay reserved.
SERIAL_WIDTHS = (4, 7, 10, 13, 16)
HOLDOUT_GAP = 10_000

# Measurement sentences from the English and A-to-Z packs. Training text that
# shares a 40-character window with any of these is discarded.
DENYLIST: tuple[str, ...] = (
    "When two scripts both subtract health, pick a single writer, route the other through an event, and replay the last fixed tick to prove the total matches the rule.",
    "A puzzle saved during an animation stores the rule state rather than a decorative frame, and the loaded collision pose must agree with that state.",
    "If the display rate falls from sixty to twenty, travel distance per simulated second stays put because the tick, not the picture rate, advances movement.",
    "A replay stores the seed and the per-tick input words. Rebuilding the match from that file must match positions at the sampled ticks.",
    "Choosing a 32k source and a 16k target is a divisor of 2 on the ladder, and the planner returns that divisor without building either bitmap.",
    "Use nearest upscale when the palette must stay intact. Use a box average only when a mixed channel value is an accepted authoring choice.",
    "If a winter scene adds a scarf, record the accessory on the sheet and leave skin, eyes, and hair untouched unless the scene states a reason.",
    "A close portrait and a distant sprite of the same person use one sheet. The distant sprite may use fewer pixels and must not rename the eye colour.",
    "A mended hem uses the trim colour for the repair mark and keeps the primary cloth colour on the rest of the garment.",
    "Faded wear may darken an edge toward the outline colour in the micro pattern while the stored primary colour stays the same token.",
    "Swapping a copper lantern for a gold lantern changes item colour only. The hand region, the light rule, and the rest of the character sheet stay.",
    "A charm on the torso combines an accessory with an item kind. Clearing the charm clears those two fields and leaves eye colour and cloth alone.",
    "The vertical slice is done when the core verb, its feedback, and one fair failure can be played from a fresh start without the deferred feature list.",
    "A new biome is lower priority than a broken retry. Repair the retry, then decide whether the biome changes a real decision.",
    "If players fail before they can see the tell, lengthen the telegraph or move the camera. Do not start by raising health.",
    "A boss with two readable phases is enough for the slice. A third phase waits until both earlier phases have a fair counter.",
    "A pitch that cannot name the repeated verb is still a theme, and the next writing task is that verb.",
    "Session length is a design constraint. It decides how much tutorial, travel, and failure recovery the slice may contain.",
    "If the loop needs a designer sitting beside the player, the state log is missing and the slice is not ready for content.",
    "Success and failure both need a visible cause. A flag that flips offscreen is not yet a finished loop.",
    "A second read of the device mid-tick can disagree with the first and make a jump depend on call order.",
    "Controller and keyboard should enter the same action table. Scattering device names through collision code breaks ports.",
    "A crowd variant copies the sheet and changes one named field. It does not repaint the face with an unnamed dye.",
    "Dialogue portraits and the doll in the world read one sheet so eye colour cannot drift between scenes.",
    "Landmarks should be nameable by a player who has walked the space once. If they cannot, the layout is not readable yet.",
    "Streaming a room must not drop the door flag. The room can arrive late. The state cannot.",
    "If players fail before the tell is visible, lengthen the tell or move the camera before changing health totals.",
    "Two readable boss phases are enough for a slice. A third phase waits until each earlier phase has a fair counter.",
    "An exploit that turns a craft into free money is audited at the source and the sink before any price table is rewritten.",
    "Item colour is presentation. The economy rule keys on item kind so a recolor cannot mint a new resource.",
    "A character does not repeat a secret they never witnessed. Knowledge boundaries are data, not a tone of voice.",
    "When two endings disagree on a shared fact, fix the ledger before writing more epilogue lines.",
    "A coarser raster keeps the sheet names for skin, eyes, hair, cloth, and items. Pixel count is not the identity.",
    "Scale2x and nearest are palette tools. They are not a certificate that the picture is native console hardware.",
    "Melody timing is an absolute beat from the index and the tempo. It is not a chain of equal gaps that drift.",
    "Voice lines reference the ledger id of the speaker. A swapped portrait does not silently take another person's line.",
    "If a player cannot tell which object accepts the verb, the interface failed before the difficulty did.",
    "Text that will be translated keeps a stable id and room to grow. The logic reads the id, not the English width.",
    "Display rate can fall from sixty to twenty without changing travel per simulated second, because the tick advances movement.",
    "A replay stores the seed and the per-tick inputs. Rebuilding the match must match positions at the sampled ticks.",
    "An editor action that depends on click timing is not ready. The same data edit must serialize to the same bytes.",
    "Migrations keep the old file. They write a new version beside it and refuse to guess missing fields.",
    "If every tester misses the same door, the door's read is the defect. Adding a hint line is the second option, not the first.",
    "Difficulty complaints after an unread telegraph are camera and timing work. They are not an invitation to inflate health.",
    "A folder of loose files is not a release. The receipt has to point at one hash and the commands that produced it.",
    "Cutting a feature to meet the frame budget is recorded. Hiding the miss by skipping input is not an acceptable cut.",
)

SLOTS: dict[str, tuple[str, ...]] = {
    "role": ("designer", "programmer", "animator", "writer", "composer", "tester", "rigger", "lighter"),
    "asset": ("sprite sheet", "portrait plate", "prop mesh", "cloth card", "icon atlas", "cinematic plate"),
    "field": ("health", "position", "inventory", "item kind", "door flag", "tick index"),
    "eye": ("amber", "grey", "green", "hazel", "violet", "brown"),
    "hair": ("braid", "crop", "coils", "bun", "waves", "side part"),
    "hair_color": ("black", "copper", "ash", "gold", "white", "auburn"),
    "skin": ("warm sand", "cool olive", "deep brown", "fair rose", "golden tan", "ebony"),
    "cloth": ("linen", "wool", "silk", "canvas", "felt", "denim"),
    "wear": ("fresh", "worn", "mended", "faded", "weathered"),
    "item": ("lantern", "satchel", "map", "key", "charm", "compass"),
    "item_color": ("copper", "gold", "field green", "dusk blue", "hearth red", "harbor grey"),
    "place": ("winter court", "harbor lane", "hearth hall", "field gate", "dusk stair", "pine mill"),
    "shot": ("wide", "close", "over-shoulder", "insert", "tracking", "low-angle"),
    "beat": ("approach", "threat", "choice", "revelation", "rest", "button"),
    "move": ("holds", "pushes in", "racks focus", "pans", "tilts", "settles"),
    "garment": ("coat", "hem", "cloak", "sleeve", "collar", "sash"),
    "light": ("rim light", "practical lantern", "dusk bounce", "hearth glow", "overcast", "moon edge"),
    "rate": ("sixty", "thirty", "twenty", "fifteen"),
    "tier": ("65536", "32768", "16384", "8192", "4096"),
    "verb": ("jump", "strike", "speak", "open", "craft", "sneak"),
    "failure": ("missed tell", "late press", "empty resource", "blocked route"),
    "grant": ("author grant", "studio grant", "work-for-hire record", "public-domain dedication"),
    "screen": ("inventory", "map", "settings", "dialogue", "shop", "pause"),
    "region": ("hand", "torso", "head", "back"),
    "pattern": ("plain", "stripe", "check", "hem", "speck"),
    "note": ("pickup", "footstep", "hit", "failure sting", "discovery"),
    "fault": ("off-by-one index", "unset field", "stale tick", "wrong owner", "mixed units"),
    "check": ("type", "name", "unused import", "unreachable branch", "format"),
    "symptom": ("hard stop", "soft lock", "desync", "black frame", "stuck pose"),
    "copy": ("button label", "quest line", "legal notice", "error line", "subtitle"),
}

# Tracks the adaptive ratchet watches. Every name is also a corpus domain.
TRACKS: dict[str, tuple[str, ...]] = {
    "visual": ("sprites", "assets", "character", "clothing", "hair", "eyes", "items", "facial", "palette"),
    "narrative": (
        "story",
        "cinematics",
        "cutscenes",
        "cinematic_playwright",
        "playwright",
        "dialogue",
        "quests",
        "voice",
    ),
    "systems": ("legal", "coding", "world", "combat", "economy", "physics", "save_state", "input", "build"),
    "review": ("proofreading", "syntax", "errors", "crash", "lint"),
    "practice": (
        "tutorial",
        "achievement",
        "navigation",
        "moderation",
        "analytics",
        "subtitles",
        "photo_mode",
    ),
    "rights": (
        "copyright",
        "license",
        "trademark",
        "attribution",
        "age_rating",
        "likeness",
        "music_rights",
        "asset_rights",
    ),
    "sound": ("audio", "music", "haptics"),
    "stage": ("animation", "camera", "lighting", "vfx", "particles", "color_script", "weather"),
    "craft": ("materials", "shader", "rigging", "props", "crowd", "trailer"),
    "play": (
        "accessibility",
        "behavior",
        "interface",
        "inventory",
        "level_design",
        "localization",
        "netcode",
        "performance",
    ),
}

TEMPLATES: dict[str, tuple[str, ...]] = {
    "legal": (
        "Pass {n}. The {role} files a {grant} for the {asset}. The record names the author and the revision, and a missing grant keeps that file out of the shipping build.",
        "Pass {n}. A collaborator may replace the {asset} for the {place} only after the change is written down. The previous revision stays addressable so the cut can be restored.",
        "Pass {n}. Age-rating notes for the {place} list the {verb} and the {failure}. They describe the authored scene. They do not copy a commercial rating form.",
        "Pass {n}. A license note for the {asset} names the grant and the author. Shipping without that note keeps the file out of the build.",
        "Pass {n}. The {role} records who may use the {item} likeness. A missing consent line blocks the {place} scene that shows it.",
    ),
    "coding": (
        "Pass {n}. The {role} steps {field} on a fixed interval. Render may interpolate. A long frame runs several ticks or slows, and it does not take one giant step.",
        "Pass {n}. One owner writes {field}. The {verb} emits an event that owner applies. A second writer of {field} is a defect, logged with the rule id.",
        "Pass {n}. Input for {verb} is sampled once at the start of tick {n}. Menus and play share the action table, so a rebound does not fork the rule.",
        "Pass {n}. The lint and the syntax pass both run before the {verb} change can merge. A red check names the line and the owner.",
        "Pass {n}. An error path for {failure} returns one result type. The caller does not parse a crash string to decide the rule.",
    ),
    "sprites": (
        "Pass {n}. The {asset} for the {item} names its palette, its pixel size, and its author. Nearest growth repeats pixels. A box step may mix a channel and stays an authoring choice.",
        "Pass {n}. A {tier} plan for the {place} sprite names the divisor and allocates no full-tier bitmap. The sheet still stores the {item_color} {item}.",
        "Pass {n}. Silhouette for the {verb} pose reads at play distance. The {role} checks the shape in the {light}, with a cue besides hue.",
    ),
    "assets": (
        "Pass {n}. The registry row for the {asset} stores source, hash, resolution, and target limits. A second export from the same inputs matches or explains the difference.",
        "Pass {n}. The {role} refuses an {asset} whose source file is missing. The build copies from the registry, not from a loose folder.",
        "Pass {n}. Wear on the {asset} is {wear}. That mark changes the micro pattern and leaves the {cloth} token in the record.",
    ),
    "character": (
        "Pass {n}. The person at the {place} is written once: skin {skin}, eyes {eye}, hair {hair_color} {hair}. Portraits and the doll copy that sheet.",
        "Pass {n}. A scarf at the {place} is an accessory on the sheet. Skin, eyes, and hair change only when the ledger names a cause. Pass id {n}.",
        "Pass {n}. Coherence is the variables, not the pixel count. A coarser view of this person keeps skin {skin} and eye {eye}.",
    ),
    "world": (
        "Pass {n}. The {place} has a landmark a player can name, a {failure} risk, and a route back. Empty space is not yet a level.",
        "Pass {n}. The door at the {place} is a flag. Art shows closed and open. The flag, not the picture, decides whether {verb} may pass.",
        "Pass {n}. Streaming the {place} may arrive late. The {field} for that room is already in the authoritative record.",
    ),
    "story": (
        "Pass {n}. The ledger for the {place} records who knows the {item}, which promise stands, and which fact is shared by every branch.",
        "Pass {n}. A branch may add a fact about the {item}. It may not silently rewrite a shared fact. Repair the smallest set of later lines. Pass {n}.",
        "Pass {n}. The {role} withholds a fact the speaker did not see at the {place}. The ledger stores that boundary. Tone is not the record.",
    ),
    "cinematics": (
        "Pass {n}. Shot {n} is a {shot} on the {place}. The camera {move} during the {beat}. Gameplay state does not advance inside the shot.",
        "Pass {n}. The {light} motivates the {shot}. Exposure may change for the picture. Health and inventory stay on the simulation clock.",
        "Pass {n}. An in-engine cinematic at the {place} uses the same sheet: eyes {eye}, hair {hair}. A rendered plate may not invent a new face.",
    ),
    "cutscenes": (
        "Pass {n}. The cutscene at the {place} is skippable after the first view, and the skip lands on the same {field} as playing it through.",
        "Pass {n}. Dialogue in the cutscene references the speaker id. A swapped portrait does not take another person's line. Pass {n}.",
        "Pass {n}. The {beat} in this cutscene has a readable cause. If the player can {verb} afterward, the exit state lists that verb.",
    ),
    "cinematic_playwright": (
        "Pass {n}. The playwright marks beat {beat} for the {place}: who wants what, what blocks them, and the {shot} that shows the turn.",
        "Pass {n}. Lines stay in the speaker's vocabulary. The {item} is named the same way in the wide shot and the {shot} insert. Pass {n}.",
        "Pass {n}. A button line ends the scene on a decision. The playwright writes the payoff and one path that skips it, both legal in the ledger.",
    ),
    "playwright": (
        "Pass {n}. The interface test opens the {screen} screen, chooses {verb}, and expects {field} in the state line. It does not assert on a pixel colour.",
        "Pass {n}. The test for the {screen} screen runs from a fresh save at the {place}. A failure names the missing affordance, not a flaky wait.",
        "Pass {n}. Keyboard, pad, and pointer walk the same {screen} actions. The test script shares that table with the game. Pass {n}.",
    ),
    "items": (
        "Pass {n}. The {item_color} {item} changes item colour only. Kind, the {region} mount, and the use rule stay on their tokens.",
        "Pass {n}. Inventory keys on item kind. The picture reads {item_color}. Losing the picture still leaves the {item} kind in the state record.",
        "Pass {n}. A {item} on the {region} does not overwrite hair {hair} or eye {eye}. Those factors have their own fields. Pass {n}.",
    ),
    "clothing": (
        "Pass {n}. The {garment} is {cloth}, {wear}, pattern {pattern}. Wear edits the micro pattern and does not retint skin {skin}.",
        "Pass {n}. Trim on the {garment} is a named colour. A repair mark may use the trim. The primary {cloth} token stays put. Pass {n}.",
        "Pass {n}. Outline of the {garment} is its own token. A coarser raster may blend pixels and must still store the outline name.",
    ),
    "hair": (
        "Pass {n}. Hair is {hair_color} {hair}, placed on a stable region of the head. A coarser grid keeps the hair token even when strands merge.",
        "Pass {n}. The {role} does not let a hat replace the hair record. The hat is an accessory. Hair {hair} remains underneath. Pass {n}.",
        "Pass {n}. A crowd extra at the {place} copies the hair sheet and changes one field. It does not invent an unnamed dye. Pass {n}.",
    ),
    "eyes": (
        "Pass {n}. Eye colour is {eye} on every portrait and on the doll. A {shot} may show fewer pixels and may not rename the eye.",
        "Pass {n}. The catchlight is {light}. It is a render choice. The stored eye token remains {eye}. Pass {n}.",
        "Pass {n}. A blink is animation. It does not write a new eye colour. The sheet at pass {n} still says {eye}.",
    ),
    "facial": (
        "Pass {n}. Brow, lips, and eyes {eye} are separate tokens on the face. A expression pose blends shapes and leaves the tokens stored.",
        "Pass {n}. Skin {skin} and lips share no channel by accident. The {role} checks the face under {light} at the {place}.",
    ),
    "palette": (
        "Pass {n}. The palette groups {item_color} with {cloth} and eye {eye}. Swapping the palette recolors inside closed names.",
        "Pass {n}. An unknown colour name fails the sheet. Layout does not invent a channel to hide a typo. Pass {n}.",
    ),
    "audio": (
        "Pass {n}. The {note} is a short synthesized envelope tied to one state change. Tempo is a quarter from the beats, not a chain of equal gaps.",
        "Pass {n}. A picture running at {rate} does not skip the accent the simulation already marked. The tick is the clock. Pass {n}.",
    ),
    "music": (
        "Pass {n}. The cue for the {place} uses a scale, a seed, and a tempo. Notes are frequency steps written for this project.",
        "Pass {n}. Music, effects, and voice sit on separate buses. A muted bus still lets the {verb} simulation advance. Pass {n}.",
    ),
    "voice": (
        "Pass {n}. The voice line stores the speaker id and the ledger fact it is allowed to say. Pass {n} does not borrow another face.",
        "Pass {n}. A {shot} reaction at the {place} waits for the line to end or for a skip that lands on the same dialogue flag.",
    ),
    "animation": (
        "Pass {n}. Clips are named idle, move, {verb}, hurt, and recover. The state flag is authoritative. The frame is a sample.",
        "Pass {n}. Cancelling {verb} on this tick clears the hurtbox even if the picture holds the old pose for one interpolated frame.",
    ),
    "camera": (
        "Pass {n}. The gameplay camera shows the {failure} before the hit frame. A {shot} cinematic camera does not fight that read.",
        "Pass {n}. Shake is cosmetic. At {rate} frames it may drop. Damage from {verb} may not. Pass {n}.",
    ),
    "lighting": (
        "Pass {n}. The {light} at the {place} is motivated by a source the player can name. Gameplay readability outranks a darker mood.",
        "Pass {n}. A night variant keeps eye {eye} and cloth {cloth} tokens. Only the {light} rig changes. Pass {n}.",
    ),
    "combat": (
        "Pass {n}. The {beat} gives time to answer with {verb}. A late answer gets a recovery. Difficulty changes counts, not a hidden hitbox.",
        "Pass {n}. Two readable phases at the {place} are enough until each has a counter and a rest. Pass {n} does not add a third blindly.",
    ),
    "economy": (
        "Pass {n}. The {item} has a source, a sink, and a capacity. Craft shows the recipe and a use. The check reads item kind.",
        "Pass {n}. A vendor price for the {item_color} {item} has a driver. Buying and selling the same stack at a profit is a defect. Pass {n}.",
    ),
    "interface": (
        "Pass {n}. The {screen} screen shows the next legal {verb}, the resource that limits it, and the {failure} if the verb is refused.",
        "Pass {n}. Colour is not the only channel on the {screen} screen. A word or a shape names the {item}. Pass {n}.",
    ),
    "accessibility": (
        "Pass {n}. The first settings page offers remaps, captions, contrast, and a way to reduce shake. Pass {n} does not hide those behind a clear.",
        "Pass {n}. Focus order on the {screen} screen is data. Pad and pointer move through the same {verb} actions.",
    ),
    "localization": (
        "Pass {n}. The {screen} string keeps a stable id and room to grow. Logic reads the id, not the English width. Pass {n}.",
        "Pass {n}. The speaker's name and the {item} name are separate ids so a translation can reorder them.",
    ),
    "physics": (
        "Pass {n}. Motion, cooldown, and the {verb} arc read the fixed interval. They do not read the {rate} display frame time.",
        "Pass {n}. The {item} on the {region} collides on its layer. Cloth {cloth} does not become a second collider. Pass {n}.",
    ),
    "behavior": (
        "Pass {n}. The opponent at the {place} telegraphs {beat}, then commits, then rests. The counter is a {verb} the player already owns.",
        "Pass {n}. The same seed and inputs reproduce the encounter. The {role} tunes the data, not a one-off outcome. Pass {n}.",
    ),
    "level_design": (
        "Pass {n}. Traversal at the {place} teaches {verb} in a safe pocket, then with one {failure}, then with a second verb already owned.",
        "Pass {n}. A shortcut at the {place} still respects the door flag. A skip that voids a required {field} is a defect.",
    ),
    "save_state": (
        "Pass {n}. The save stores the tick index, the random stream, and {field}. Load rejects a record that fails its checks.",
        "Pass {n}. A save during the {shot} stores the rule state. The decorative frame is not the resume pose. Pass {n}.",
    ),
    "input": (
        "Pass {n}. The {verb} buffer is captured at the tick edge, consumed in order, and can be replayed to the same {field}.",
        "Pass {n}. Remap lives in one table. The {screen} screen and the {place} fight both read it. Pass {n}.",
    ),
    "vfx": (
        "Pass {n}. The {note} burst and the {light} flash are listeners. They may drop on a slow machine. The {field} write may not.",
        "Pass {n}. Particles for the {item} use the item colour token {item_color}. They do not recolor hair {hair_color}.",
    ),
    "materials": (
        "Pass {n}. {cloth} and metal stay named factors. The shader for the {garment} reads those tokens under the {light}.",
        "Pass {n}. A wet variant at the {place} is a material flag. It does not change eye {eye} or skin {skin}. Pass {n}.",
    ),
    "shader": (
        "Pass {n}. The shader for the {asset} fails closed when a texture is missing. It does not sample an unnamed colour.",
        "Pass {n}. Outline of the {garment} is redrawn from the stored token after the {tier} downsample. Pass {n}.",
    ),
    "particles": (
        "Pass {n}. Particle count for the {verb} scales down before the simulation tick does. Pass {n} keeps the hit authoritative.",
        "Pass {n}. Dust at the {place} is local to the {light}. It is not a collision volume.",
    ),
    "rigging": (
        "Pass {n}. The {role} binds the {garment} to the body and the {item} to the {region}. Eyes {eye} stay on the face rig.",
        "Pass {n}. A cloth sim for {cloth} is cosmetic. The gameplay {region} mount is the item token, pass {n}.",
    ),
    "dialogue": (
        "Pass {n}. The line at the {place} names the {item} the way the ledger does. A {beat} may add a fact and may not erase a shared one.",
        "Pass {n}. Each speaker keeps a vocabulary. Pass {n} does not put another person's knowledge in this mouth.",
    ),
    "quests": (
        "Pass {n}. The quest at the {place} has a clue in the world, a {verb}, and a resolution on every reachable ending.",
        "Pass {n}. Turning in the {item} writes one flag. The {screen} log reads that flag, not the icon. Pass {n}.",
    ),
    "build": (
        "Pass {n}. The release names the revision, the {asset} registry digest, the commands, and the artifact hash.",
        "Pass {n}. A bad export of the {asset} rolls back by hash. The previous good build stays. Pass {n}.",
    ),
    "performance": (
        "Pass {n}. The frame budget at {rate} splits input, simulation, collision, audio, and the draw. Measure it on the slow target.",
        "Pass {n}. A {tier} plan does not allocate the full bitmap. The {role} crops first. Pass {n}.",
    ),
    "color_script": (
        "Pass {n}. The {place} script sets {light} against cloth {cloth} and eye {eye} so the actor separates from the ground.",
        "Pass {n}. A flash of {item_color} marks the {item} pickup. The face keeps skin {skin}. Pass {n}.",
    ),
    "weather": (
        "Pass {n}. Weather at the {place} changes the {light} and the footstep {note}. It does not rewrite the door flag.",
        "Pass {n}. Rain darkens the micro pattern of {wear} {cloth}. The stored cloth token is unchanged. Pass {n}.",
    ),
    "props": (
        "Pass {n}. The {item} prop at the {place} has a kind, a colour {item_color}, and a mount {region}. The mesh is not the rule.",
        "Pass {n}. A broken prop swaps to a {wear} state. Gameplay still reads the item kind. Pass {n}.",
    ),
    "haptics": (
        "Pass {n}. The {verb} pulse is tied to the tick, not to the {rate} display. A missing rumble motor still applies the rule.",
        "Pass {n}. The {failure} buzz is shorter than the success pulse so the {screen} screen can name which one fired. Pass {n}.",
    ),
    "trailer": (
        "Pass {n}. The trailer uses shots from the {place} that exist in the build. It does not invent a {verb} the slice cannot play.",
        "Pass {n}. Titles over the {shot} leave the character sheet readable: eyes {eye}, hair {hair_color}. Pass {n}.",
    ),
    "inventory": (
        "Pass {n}. The {screen} grid shows kind and {item_color} for the {item}. Capacity is data. A full bag refuses the add and says why.",
        "Pass {n}. Sorting the bag does not rewrite {field}. Order is a view. Pass {n}.",
    ),
    "netcode": (
        "Pass {n}. Peers exchange inputs for a tick and simulate only after the set is complete. Guessed motion is presentation until the inputs arrive.",
        "Pass {n}. The host does not silently rewrite a peer's {field}. Disagreement rolls back to the last agreed tick. Pass {n}.",
    ),
    "crowd": (
        "Pass {n}. A crowd member at the {place} copies the sheet and changes hair {hair} or cloth {cloth}, one field only.",
        "Pass {n}. The crowd uses the same {verb} set as the lead. A cheaper lod drops particles, not the collision layer. Pass {n}.",
    ),
    "proofreading": (
        "Pass {n}. The {role} reads the {copy} for the {screen} screen aloud. A doubled word or a swapped {item} name is a defect, logged with the line id.",
        "Pass {n}. Proofreading the {place} text checks tense and the {verb} name. It does not rewrite the rule. The ledger keeps the previous line.",
        "Pass {n}. The legal notice and the {copy} must name the same {item}. A mismatch is a proofreading fail, not a new grant. Pass {n}.",
    ),
    "syntax": (
        "Pass {n}. The script for {verb} must parse before play. A missing closer stops the build and names the line. The {role} does not ship the broken file.",
        "Pass {n}. A syntax pass on the {field} writer rejects an unknown token and leaves the last good revision in place. Pass {n}.",
        "Pass {n}. The {fault} in the {verb} script is a syntax block. Format may differ. The token that failed must be the one the message names.",
    ),
    "errors": (
        "Pass {n}. When {verb} fails for {failure}, the {screen} screen states the cause and the next legal action. A bare code number is not the message.",
        "Pass {n}. The {role} maps the {fault} to one error line. Two writers of that line are a defect. The player can retry without a restart.",
        "Pass {n}. The error line for the {item} uses the ledger name. It does not invent a cause the {failure} record does not hold. Pass {n}.",
    ),
    "crash": (
        "Pass {n}. A crash at the {place} stores the tick, the {verb}, and the {field} value. The report does not include a personal name. The last save stays readable.",
        "Pass {n}. The {symptom} after {failure} writes a receipt and returns to the {screen} screen. It does not roll the whole build back. Pass {n}.",
        "Pass {n}. The {role} can replay the crash from the stored tick and the {verb} input. A report that cannot be replayed is not closed.",
    ),
    "lint": (
        "Pass {n}. The lint for {check} runs on the {verb} script before review. A warning names the line. It does not change {field} by itself.",
        "Pass {n}. The {role} treats a lint hit on the {asset} path as a block for release. Suppressing the check requires a written reason. Pass {n}.",
        "Pass {n}. Lint for {check} and the syntax pass agree on the line number. If they disagree, the file is not ready to merge.",
    ),
    "tutorial": (
        "Pass {n}. The first {verb} at the {place} is shown once, then the prompt leaves. The {screen} screen does not repeat the lesson after a success.",
        "Pass {n}. A tutorial must be skippable from a fresh start and must not change {field}. The {role} checks both paths. Pass {n}.",
    ),
    "achievement": (
        "Pass {n}. The {verb} achievement unlocks from the ledger, not from a picture. Reloading the save does not grant it twice.",
        "Pass {n}. An achievement for the {place} names the rule that fired. It does not reveal a secret the player has not seen. Pass {n}.",
    ),
    "navigation": (
        "Pass {n}. The route through the {place} uses the door flag, not the art. A blocked {verb} path says why and offers the open route.",
        "Pass {n}. Navigation marks for the {item} stay on the {screen} map until the player arrives. They do not move {field}. Pass {n}.",
    ),
    "moderation": (
        "Pass {n}. Player text on the {screen} screen is checked before it is shown. A rejected line tells the sender and does not punish the room.",
        "Pass {n}. The {role} keeps a moderation note on the report id. The note is not a copy of a private message. Pass {n}.",
    ),
    "analytics": (
        "Pass {n}. A play of {verb} at the {place} records the tick and the outcome. It does not record a personal name. The {role} can delete the row.",
        "Pass {n}. Analytics for the {failure} count the event once per attempt. A replay of the same tick does not double the total. Pass {n}.",
    ),
    "subtitles": (
        "Pass {n}. The subtitle for the {place} line names the speaker id and stays readable over the {shot}. It does not replace the spoken ledger.",
        "Pass {n}. Subtitles for {verb} keep a stable id so a translation can grow. The logic reads the id, not the line width. Pass {n}.",
    ),
    "photo_mode": (
        "Pass {n}. Photo mode at the {place} may move the camera. It does not advance the tick or change {field}. The {role} checks the exit state.",
        "Pass {n}. A photo hides interface chrome and keeps the character sheet: eyes {eye}, hair {hair}. It is not a new canon portrait. Pass {n}.",
    ),
    "copyright": (
        "Pass {n}. The {role} records who owns the expression in the {asset} and the year it was made. A filename is not ownership, and the shipping build keeps the notice with the file.",
        "Pass {n}. A new cut of the {asset} for the {place} stays inside the granted scope. The {role} stores the source beside the notice.",
    ),
    "license": (
        "Pass {n}. The {grant} for the {asset} names what the {role} may ship, change, and pass on. An extra use that the grant does not name stays out of the build.",
        "Pass {n}. The {place} scene may show the {item} only while its {grant} is in force. When that grant ends, the file leaves the build.",
    ),
    "trademark": (
        "Pass {n}. The {role} checks the game title and the {item} name against the mark list before the {place} build. A plain descriptive word is not assumed to be a mark.",
        "Pass {n}. Writing in the {place} does not paint a third-party mark onto the {asset}. The {role} substitutes an original name and records the swap.",
    ),
    "attribution": (
        "Pass {n}. Credits for the {asset} name the {role} and the {grant}. Shipping the file without that credit line breaks the record.",
        "Pass {n}. The {place} trailer names the composer and the author of the {asset}. A shorter cut keeps those names in the ledger.",
    ),
    "age_rating": (
        "Pass {n}. The {role} writes an age note for the {verb} scene at the {place}. The note describes that authored {failure} and does not paste an outside form.",
        "Pass {n}. Intensity for the {verb} at the {place} is a content flag on the scene. The store page reads the flag and does not invent a rating badge.",
    ),
    "likeness": (
        "Pass {n}. A performer's face on the {asset} needs written consent that names the {place} scene. The {role} stores that consent beside the take.",
        "Pass {n}. The {item} likeness at the {place} is allowed only when the consent names that use. Silence from the subject is not a grant.",
    ),
    "music_rights": (
        "Pass {n}. The {note} cue separates the composition from the recorded take. The {role} ships only the take named by the {grant}.",
        "Pass {n}. A {place} scene that plays {note} keeps the music grant with the cue id. A new mix does not replace that grant.",
    ),
    "asset_rights": (
        "Pass {n}. The {asset} enters the {place} build only with a {grant} that covers the shipped revision. A preview file is not that grant.",
        "Pass {n}. The {role} traces the {item_color} {item} back to its author and its {grant}. A recolor does not create a new owner.",
    ),
}


def domains() -> tuple[str, ...]:
    return tuple(TEMPLATES)


def legal_source_groups() -> dict[str, tuple[str, ...]]:
    """Every original domain, once, grouped by the track that measures it.

    A domain that is not on a track is reported under ``adjacent``. An empty
    adjacent set is valid: the tracks then cover the corpus. Holdout lines
    are not a source.
    """
    tracked = {name for names in TRACKS.values() for name in names}
    groups = {track: tuple(names) for track, names in TRACKS.items()}
    adjacent = tuple(name for name in TEMPLATES if name not in tracked)
    if adjacent:
        groups["adjacent"] = adjacent
    covered = [name for names in groups.values() for name in names]
    if sorted(covered) != sorted(TEMPLATES) or len(covered) != len(set(covered)):
        raise RuntimeError("legal sources do not match the corpus domains")
    return groups


def focus_weights() -> dict[str, float]:
    """Legal, coding, and the review domains are sampled ahead of the rest."""
    weights = {domain: 1.0 for domain in TEMPLATES}
    for name in ("legal", "coding", *TRACKS["rights"]):
        weights[name] = 3.0
    for name in TRACKS["review"]:
        weights[name] = 2.5
    for name in TRACKS["practice"]:
        weights[name] = 1.5
    return weights


def _formatter_fields(template: str) -> tuple[str, ...]:
    fields = []
    for _literal, name, _spec, _conv in string.Formatter().parse(template):
        if name:
            fields.append(name)
    return tuple(fields)


def validate_templates() -> dict[str, int]:
    missing_tracks = [name for names in TRACKS.values() for name in names if name not in TEMPLATES]
    if missing_tracks:
        raise ValueError(f"track domain missing templates: {missing_tracks}")
    required = {
        "legal",
        "coding",
        "copyright",
        "license",
        "trademark",
        "attribution",
        "age_rating",
        "likeness",
        "music_rights",
        "asset_rights",
        "proofreading",
        "syntax",
        "errors",
        "crash",
        "lint",
        "sprites",
        "assets",
        "character",
        "world",
        "story",
        "cinematics",
        "cutscenes",
        "cinematic_playwright",
        "playwright",
        "items",
        "clothing",
        "hair",
        "eyes",
    }
    absent = required - set(TEMPLATES)
    if absent:
        raise ValueError(f"required domains missing: {sorted(absent)}")
    for domain, templates in TEMPLATES.items():
        if len(templates) < 2:
            raise ValueError(f"{domain} needs two templates")
        for template in templates:
            if "{n}" not in template or len(template) < 40:
                raise ValueError(f"{domain} template is thin")
            for field in _formatter_fields(template):
                if field != "n" and field not in SLOTS:
                    raise ValueError(f"{domain} uses unknown slot {field}")
    return {"domains": len(TEMPLATES), "templates": sum(len(v) for v in TEMPLATES.values())}


def byte_kinds(domain: str, serial: int) -> tuple[str, ...]:
    """Label each rendered byte as skeleton, digit, or slot.

    Skeleton bytes are the template wording shared by every serial. Digits are
    the pass id. Slots are the fields that change with that id.
    """
    templates = TEMPLATES[domain]
    template = templates[serial % len(templates)]
    values: dict[str, str] = {}
    mix = serial // len(templates)
    for _literal, name, _spec, _conv in string.Formatter().parse(template):
        if not name or name == "n":
            continue
        options = SLOTS[name]
        values[name] = options[mix % len(options)]
        mix //= len(options)
    kinds: list[str] = []
    for literal, name, _spec, _conv in string.Formatter().parse(template):
        if literal:
            kinds.extend(["skeleton"] * len(literal.encode("utf-8")))
        if name:
            piece = str(serial) if name == "n" else values[name]
            kinds.extend([("digit" if name == "n" else "slot")] * len(piece.encode("utf-8")))
    if len(kinds) != len(render(domain, serial).encode("utf-8")):
        raise RuntimeError(f"byte kinds drifted for {domain}")
    return tuple(kinds)


def render(domain: str, serial: int) -> str:
    templates = TEMPLATES[domain]
    template = templates[serial % len(templates)]
    values: dict[str, object] = {"n": serial}
    mix = serial // len(templates)
    for field in _formatter_fields(template):
        if field == "n":
            continue
        options = SLOTS[field]
        values[field] = options[mix % len(options)]
        mix //= len(options)
    return template.format(**values)


def training_serial(counter: int) -> int:
    """Map a training counter to a pass id of rotating width.

    The reserved holdout ids, and a gap around them, are never returned.
    Distant long ids teach the digit length the measurement lines use.
    """
    if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
        raise ValueError("counter must be a non-negative int")
    width = SERIAL_WIDTHS[counter % len(SERIAL_WIDTHS)]
    block = counter // len(SERIAL_WIDTHS)
    origin = 10 ** (width - 1)
    limit = origin * 10
    start = origin + 1
    # The 13-digit measurement ids stay a million away. Other widths wrap inside themselves.
    if origin <= HOLDOUT_SERIAL < limit:
        start = HOLDOUT_SERIAL + 10**6
    stride = 97
    room = max(1, (limit - start) // stride)
    serial = start + (block % room) * stride
    if serial in (HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1) or not origin <= serial < limit:
        raise RuntimeError("training serial collided with a holdout")
    if min(abs(serial - HOLDOUT_SERIAL), abs(serial - (HOLDOUT_SERIAL + 1))) < HOLDOUT_GAP:
        raise RuntimeError("training serial entered the holdout gap")
    return serial


def banned_windows(texts: tuple[str, ...] | list[str]) -> set[str]:
    found: set[str] = set()
    for text in texts:
        if len(text) <= WINDOW:
            found.add(text)
            continue
        found.update(text[index : index + WINDOW] for index in range(len(text) - WINDOW + 1))
    return found


def leaks(text: str, banned: set[str]) -> bool:
    if len(text) < WINDOW:
        return text in banned
    return any(text[index : index + WINDOW] in banned for index in range(len(text) - WINDOW + 1))


def holdout_documents() -> tuple[str, ...]:
    """Reserved serials. The training stream starts at zero and does not use these."""
    validate_templates()
    rows = [render(domain, HOLDOUT_SERIAL + offset) for domain in TEMPLATES for offset in (0, 1)]
    if len(rows) != len(set(rows)):
        raise RuntimeError("corpus holdout collided")
    return tuple(rows)


def track_holdouts() -> dict[str, tuple[str, ...]]:
    by_domain = {}
    for domain, offset in ((domain, offset) for domain in TEMPLATES for offset in (0, 1)):
        by_domain.setdefault(domain, []).append(render(domain, HOLDOUT_SERIAL + offset))
    return {
        track: tuple(text for domain in names for text in by_domain[domain])
        for track, names in TRACKS.items()
    }


class CorpusStream:
    """Weighted stream. Callers may raise a domain weight to review a weak area."""

    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        validate_templates()
        self.weights = {domain: 1.0 for domain in TEMPLATES}
        if weights:
            for domain, weight in weights.items():
                if domain not in self.weights:
                    raise ValueError(f"unknown domain {domain}")
                self.weights[domain] = float(weight)
        self.counts = {domain: 0 for domain in TEMPLATES}
        self.serial = {domain: 0 for domain in TEMPLATES}
        # Own holdouts are reserved by serial. The 40-character filter is for the
        # English and A-to-Z measurement lines, which use different wording.
        self.banned = banned_windows(DENYLIST)

    def next_from(self, domain: str) -> tuple[str, tuple[str, ...]]:
        """Next clean lesson from one legal source."""
        if domain not in self.weights:
            raise ValueError(f"unknown domain {domain}")
        for _ in range(10000):
            counter = self.serial[domain]
            self.serial[domain] = counter + 1
            serial = training_serial(counter)
            text = render(domain, serial)
            if len(text) < 40 or leaks(text, self.banned):
                continue
            self.counts[domain] += 1
            return text, byte_kinds(domain, serial)
        raise RuntimeError(f"corpus stream could not find a clean {domain} document")

    def next_document(self) -> tuple[str, str]:
        domain, text, _kinds = self.next_example()
        return domain, text

    def next_example(self) -> tuple[str, str, tuple[str, ...]]:
        """Next clean lesson, with one kind label per document byte."""
        for _ in range(10000):
            domain = max(
                self.weights,
                key=lambda name: (
                    self.weights[name] / (self.counts[name] + 1),
                    -self.serial[name],
                    name,
                ),
            )
            counter = self.serial[domain]
            self.serial[domain] = counter + 1
            serial = training_serial(counter)
            text = render(domain, serial)
            if len(text) < 40 or leaks(text, self.banned):
                continue
            self.counts[domain] += 1
            return domain, text, byte_kinds(domain, serial)
        raise RuntimeError("corpus stream could not find a clean document")


def iter_documents(budget_bytes: int, stream: CorpusStream | None = None) -> Iterator[tuple[str, str]]:
    if isinstance(budget_bytes, bool) or not isinstance(budget_bytes, int) or budget_bytes < 1:
        raise ValueError("budget_bytes must be a positive int")
    source = stream or CorpusStream()
    produced = 0
    while produced < budget_bytes:
        domain, text = source.next_document()
        produced += len(text.encode("utf-8"))
        yield domain, text
