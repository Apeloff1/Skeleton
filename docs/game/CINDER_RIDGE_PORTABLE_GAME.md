# Portable Cinder Ridge game zipapp

Build a self-contained original Python game archive from the canonical checkout:

    python -m skeleton.game.gameplay.ridge_rescue consumer bundle

The command creates a deterministic, bounded cinder-ridge-<digest>.pyz in
the application's user-local exports folder. It contains the actual original
game Python modules and authored JSON source, without vendored packages or
generated filler. Publication is create-only and refuses to overwrite a prior
archive. The bundle is verified for expected entrypoint, source inventory,
size bounds and CRC before publication.

Copy the .pyz to a Windows machine with Python 3.11+ installed, then run:

    py -3 cinder-ridge-<digest>.pyz play

The game will save under %LOCALAPPDATA%\CinderRidge\Rescue. The portable
archive is not a native .exe, MSI, signed installer or Windows-qualified
release. Running the bundled acceptance command exercises the canonical
two-chapter game, transactional save/restart and replay-verified export:

    py -3 cinder-ridge-<digest>.pyz acceptance

Python 3.11+, Windows ACL behavior, real device launch, Windows defender,
reparse/TOCTOU resistance and release signing must be independently tested.
