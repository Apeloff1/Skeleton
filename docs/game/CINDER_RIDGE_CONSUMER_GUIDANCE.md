# Cinder Ridge — consumer gameplay guidance

This original two-chapter game is reached with `python -m skeleton.game.gameplay.ridge_rescue consumer play` or the Windows launcher `scripts/windows/cinder-ridge.cmd` from a source checkout. The portable `.pyz` launcher requires an installed Python 3 interpreter; it is not a native installer.

The screen displays the current chapter's required ending, rescue progress, health, stamina, turn budget and beacon status. Numbered actions are the only ordinary gameplay mutations. `h` displays a static route hint that is never guaranteed safe, `j` shows recent canonical events, `?` explains controls, `e` exports a replay-verified portable save and `q` quits after the last committed turn. A failed chapter can be retried with `r`, using the current save head.

Playability regression coverage must exercise a real interactive numbered-action sequence, save/quit/restart, legitimate earned endings, export verification, failed input without turn consumption, and replay-equivalent state. Windows device execution, installer compatibility, exact-head CI and release qualification are separate holds; these instructions do not certify them.

## Target-laptop smoke evidence

Run `scripts/windows/cinder-ridge-smoke.cmd` from a source checkout with Python 3 available, or run `py -3 -m skeleton.game.gameplay.ridge_rescue consumer smoke`. The command launches separate real Python processes, issues numbered game actions through standard input, saves and quits mid-campaign, reopens the saved slot, earns both declared endings, replays the SQLite audit chain and verifies a portable export. It uses a temporary app-data directory, never the user's normal save slot, and prints machine-readable host results.

A successful run is evidence for the specific host only. Preserve the command output, Python version, Windows version, target hardware and exact Git commit when evaluating a laptop. A source-checkout smoke pass is **not** a signed installer pass, native device qualification, security review, or release approval.
