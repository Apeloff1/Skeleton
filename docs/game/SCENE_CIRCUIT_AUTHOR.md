# Scene Circuit Author — atomic offline puzzle editing

This builder-facing CLI edits switch/gate sources without mutating originals
or partially publishing invalid state. Operations: add/remove switch, set
initial state, add/remove gate, and replace gate switch requirements.

    python -m skeleton scene-circuit-author demo
    python -m skeleton scene-circuit-author patch --source-json SOURCE --edits-json EDITS
    python -m skeleton scene-circuit-author verify --report-json REPORT

After all edits, the entire source is validated against real scene topology,
then the bounded circuit solver previews end-user victory reachability. A
truncated search is explicitly inconclusive. The report contains the original
source, edits, normalized result, preview, source digests and replay receipt.

No scripts, network, arbitrary filesystem writes or trusted authority grants.
Malformed edits fail atomically. Maximum 32 edits and 2 MiB report.

    python -m pytest skeleton/testing/test_scene_circuit_author.py -q

Reports are integrity evidence, not signatures or device certification.
