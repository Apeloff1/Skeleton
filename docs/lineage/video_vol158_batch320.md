# video vol158 batch 320

packet: VID-320
parent: #80
plane: skeleton/video/vol158
stored_prose: 0
coin: 0
network: 0

Double of SC-160 (160 organs, 50158 lines). This plane was one file
on main (pipeline.py, VOL-158) and is absent from open heads
3535-3551.

pipeline.py is not forked.

Implement:
1. Copy skeleton/video/vol158 onto a branch cut from main.
2. Do not replace pipeline.py.
3. python -m unittest tests.video.test_vol158_batch320
4. Draft PR. Do not merge over occupied heads.
