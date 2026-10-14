# audio eras batch 5120

packet: ERA-5120
parent: #80
plane: skeleton/audio/eras
stored_prose: 0
sample_bank: 0

Double of CUE-2560. Sixteen game-audio eras, 320 organs each.
pipeline.py and vol156 are not forked. Open head #3554 owns vol156.

Eras: pong, psg, sid, fm, wave, tracker, cdda, stream, spatial,
stem, bus, voice, ambient, sting, occlude, export.

Implement:
1. Copy skeleton/audio/eras onto a branch cut from main.
2. Do not replace pipeline.py. Do not touch vol156.
3. python -m unittest tests.audio.test_eras_batch5120
4. Draft PR. Do not merge over occupied heads.
