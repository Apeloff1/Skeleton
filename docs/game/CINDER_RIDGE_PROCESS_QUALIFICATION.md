# Cinder Ridge canonical acceptance matrix: real consumer process

The product qualification matrix includes a source-checkout consumer acceptance
and a separate **cross-process source + standalone zipapp** contract. The latter
opens a new game, plays real canonical actions, quits halfway, restarts in a new
process, earns both authored endings, exports a replay-verifiable bundle,
restores it into a new save slot, audits every reconstructed action, and
rejects duplicate or corrupted restoration without damaging the earned save.

The canonical acceptance matrix reports failures rather than substituting
structural fixture success for gameplay. Its focused regression assertions now
track all ten named contracts instead of stale eight/six-check expectations.
A successful run is evidence for the host where it ran, not Windows device
certification or consumer release approval.

Run the suite from a supported POSIX checkout with Python 3.11+:

    python -m pytest -q skeleton/testing/test_ridge_rescue_qualification.py
    python -m skeleton.game.gameplay.ridge_rescue acceptance

Run the dedicated Windows consumer process and standalone smoke script on an
actual target laptop; the complete matrix includes POSIX-only descriptor IO
and is not a substitute for that Windows-specific acceptance.
