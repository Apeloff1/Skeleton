# audio vol156 batch 1280

packet: AUD-1280
parent: #80
plane: skeleton/audio/vol156
stored_prose: 0
coin: 0
network: 0

Double of DV-640 (640 organs, 180079 lines). This plane was one file
on main (pipeline.py, VOL-156) and is absent from open heads 3535-3553.

pipeline.py is not forked.

Implement:
1. Copy skeleton/audio/vol156 onto a branch cut from main.
2. Do not replace pipeline.py.
3. python -m unittest tests.audio.test_vol156_batch1280
4. Draft PR. Do not merge over occupied heads.
