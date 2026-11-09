# Combat career roadmap — replayed multi-season coaching

The `combat-career-roadmap` command evaluates bounded candidate training and
rest decisions over the real canonical combat-league season simulator. It
returns a sequence of choices, predicted champion, terminal replayed save and
portable career export. No wins, currency or training tokens are trusted from
client reports; the complete sequence is replayed from the input checkpoint.

Use `python -m skeleton combat-career-roadmap demo --beam-width 2` for the
original coaching career. Use `plan --session-json JSON --target-id ENTRANT`
for an authored saved career. `verify --session-json JSON --report-json JSON`
replays the search and rejects forged even-rechecksummed advice.

The beam width is limited to 1–8 and expansion budget to 1–128. Exhaustion
returns an explicit **inconclusive** report without a winner or portable
session. Successful reports are **advisory**, not claims of global optimality.
All candidate seasons, standings, combat turns, save ancestry and export
lineage use existing canonical production contracts. Checksums are not
authentication signatures. Device qualification and exact-head CI remain
separate release gates.
