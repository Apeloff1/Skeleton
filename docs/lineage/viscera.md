# Viscera 2.5 + 2.4 (GB-22 / GB-23)

Parent #80. Wave 3 adapter. Facade only. GB-23 extends the GB-22 package.

## Artifact not copied

- `artifacts/Viscera/` is not in git.
- torch is not imported.

## Public card (GB-22)

- QK-norm RMS on q/k.
- Specdec accept-until-mismatch.
- Steer h <- h + alpha u-hat.
- Absmax int8 SNR finite.
- Remat second forward == first.

## Public card (GB-23)

- Reverse-mode tape (add/mul/relu).
- Muon Newton-Schulz on 2x2.
- Logit lens through unembed.
- GQA: n_q % n_kv == 0.
- Checkgrad on 2-layer toy vs finite difference.

## Accept

`python -m unittest tests.test_gb22_viscera tests.test_gb23_viscera -v`

`python scripts/check_viscera.py` exits 0.

`python scripts/check_viscera24.py` exits 0.
