# Dragon audiovisual intelligence and MMO data explorer

## Implemented
- Native Expo document picker with explicitly acknowledged local media retention, private cache-copy cleanup, whole-file SHA-256, exact per-block acknowledgements and a resumable same-operation upload. Native intake is presently bounded to 32 MiB to limit whole-file hashing allocation; browser intake retains its 64 MiB bound. Backend manifests remain independently bounded.
- Caption tracks: strict UTF-8 VTT/SRT, 4 MiB backend track limit, 20,000 time-coded cues, 64 tracks per media object, language tags, exact track and media digest binding, owner-scoped FTS5, ordered cue pagination, explicit track revocation, no active HTML. Media revocation/expiry removes derived caption postings under the catalogue transaction. Imported captions do not prove correspondence to the media or allow training.
- Timestamp seeking from caption search into verified web audio/video and native video. Browser and native device decoder behavior remains separately qualified. No automatic transcription, optical recognition, DRM bypass, live remote audiovisual capture, or unapproved model downloads.
- Sharded structured data explorer: exact sealed entity records, bounded bidirectional graph windows (maximum 256 nodes, 512 edges, depth six), explicit unresolved references, cycle suppression, index-backed same-source version merge and exact record before/after field changes. The cockpit exposes source-qualified raw values as unreviewed imported data and clears visible material after at most 30 seconds. No live market transactions or game-client actions.

## Qualification
Run from the repository with the established backend environment/PYTHONPATH:
```
python -m pytest backend/tests/test_dragon_media_captions.py backend/tests/test_dragon_dataset_explorer.py
```

Also require frontend full typecheck/export, native Android/iOS file picker and local video playback/seek, browser audio/video playback, actual media range authorization and revocation tests, physical-volume and retention lifecycle qualification, and exact-head security and integration CI. Parent draft #5439 is actively developing; reconcile stacked changes with its final head. Never report mock, skipped, ancestor or queued checks as passes. This extension is review-only; no merge, release, deployment, physical capacity claim, or completed worldwide crawl is authorized.
