# Hardware-aware local studio preview batch admission

Previously the preview exporter refused any request with more than 256
projects despite indexing 512. That arbitrary count cap has been removed.
Every requested project must still be a registered, unique catalog ID.

The exporter now measures the target filesystem's available disk bytes,
reserves the greater of 4 MiB or 5% of initial free capacity, and derives its
effective total output budget from the **actual** remaining space. Operators
may supply a smaller `--max-artifact-bytes` for a stricter run.

Before each output directory is written, the exporter remeasures free disk
capacity; it rejects writes that would eat into the reserve. Existing
no-overwrite directories, operator authorization, winning offline HTML5
prototype replay and receipt-digest checks are not weakened.

This adjusts **disk admission only**. It does not claim GPU VRAM allocation,
virtual memory modification, M-chip firmware changes, native genre
qualification or release certification.
