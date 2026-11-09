# document_vision vol155 batch 640

packet: DV-640
parent: #80
plane: skeleton/document_vision/vol155
stored_prose: 0
coin: 0
network: 0

Double of VID-320 (320 organs, 94631 lines). This plane was one file
on main (fusion.py, VOL-155) and is absent from open heads 3535-3552.

fusion.py is not forked. Span text is a digest, not a stored sentence.

Implement:
1. Copy skeleton/document_vision/vol155 onto a branch cut from main.
2. Do not replace fusion.py.
3. python -m unittest tests.document_vision.test_vol155_batch640
4. Draft PR. Do not merge over occupied heads.
