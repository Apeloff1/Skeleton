# Cinder Ridge: consumer play, persistent saves, restart and export

The consumer game uses the existing source-bound rescue engine, the original
two-chapter campaign and canonical journal/replay contracts. It is not a new
engine or a static demonstration. Every selected action is a real game turn.

From a source checkout with Python 3.11+ on PATH:

    python -m skeleton.game.gameplay.ridge_rescue consumer play

The game displays the map, stamina, health, inventory and legal numbered actions.
Enter an action number to play, q to save/quit, or e to export a replay-verifiable
portable JSON campaign bundle. The first play creates the "adventure" save slot.
Subsequent launches resume it. All accepted actions are committed before the
next prompt in a local SQLite transaction, using exact-head optimistic CAS.

    python -m skeleton.game.gameplay.ridge_rescue consumer status
    python -m skeleton.game.gameplay.ridge_rescue consumer audit
    python -m skeleton.game.gameplay.ridge_rescue consumer export
    python -m skeleton.game.gameplay.ridge_rescue consumer acceptance

For Windows, double-click scripts/windows/cinder-ridge.cmd from the repository
checkout with Python installed. This script is a source-checkout entry point,
NOT a signed installer or a Windows-tested consumer release.

Data is stored in %LOCALAPPDATA%\CinderRidge\Rescue on Windows, or
$XDG_DATA_HOME/cinder-ridge/rescue (falling back to ~/.local/share) on POSIX.
The CLI does not accept arbitrary database paths. A SQLite BEGIN IMMEDIATE
transaction serializes every turn and CAS head, while replay verification
rejects malformed or modified campaign state. Exports use exclusive-create
files in the application's exports directory and never overwrite an old save.
The local digest is integrity checking, not a signature or anti-cheat proof.

The source-checkout launcher requires the Python package to be importable from
the checkout root. On Windows, Python launcher py -3 is attempted before
python. The game is console-based, not a graphical installer. Platform
permissions, symlink/reparse races, hostile same-user processes, Windows ACLs,
database recovery, antivirus interactions and real laptop installation remain
unqualified. Do not claim device, installer, security or release certification
without running acceptance on a representative Windows laptop and exact-head CI.
