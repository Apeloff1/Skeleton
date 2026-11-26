# Cinder Ridge terminal conflict and offline recovery behavior

The interactive consumer menu always uses canonical available actions and
commits a turn before drawing the next frame. If another local process advances
the same save between display and input, the stale action is rejected by the
existing exact-head compare-and-swap. The terminal now refreshes the current
authoritative save and asks the player to choose again; it never silently
replays the stale input or consumes a duplicate turn.

An export failure is displayed as a recoverable warning while the committed
save remains playable. A retry rejected by campaign policy likewise reloads
the authoritative slot. An unreadable or corrupt database still fails closed:
the UI cannot invent a valid save. The completed chapter counter is clamped
to the authored chapter count, and ASCII mode replaces all remaining Unicode
glyphs so the display works on conservative Windows console encodings.

Focused regression coverage includes a second process advancing a save during
the input prompt, export failure, a full earned ending and strict ASCII output.
These tests are source-authored, not a claim that a Windows laptop or CI has
executed them.
