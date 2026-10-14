# supply_chain vol178 batch 160

packet: SC-160
parent: #80
plane: skeleton/supply_chain/vol178
stored_prose: 0
coin: 0
network: 0
format: cyclonedx-json

Double of SPEECH-80 (80 organs). This plane was two files on main
(sbom.py, model_bom.py) and is absent from open heads 3535-3549.

sbom.py and model_bom.py are not forked.

Implement:
1. Copy skeleton/supply_chain/vol178 onto a branch cut from main.
2. Do not replace sbom.py or model_bom.py.
3. python -m unittest tests.supply_chain.test_vol178_batch160
4. Draft PR. Do not merge over occupied heads.
