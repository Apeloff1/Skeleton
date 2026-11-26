# Pinned source material and embedded texture audit

Run on the exact original GLB:
```sh
python scripts/audit_emerald_materials.py /trusted/emerald_continuum.glb > material-audit.json
```
The audit verifies the whole model digest, checks embedded PNG/JPEG header dimensions and end markers, streams each image into a SHA-256 identity, records material color/linear interpretation, core PBR factor values, texture-coordinate bindings, sampler values and texture reuse. It reports core-material role conflicts rather than assuming shared bytes are incorrectly authored. Extension names are inventoried but extension-specific shading is not certified. Header fixtures are deliberately not full decoded images. Unsupported formats require separate review.

No upscaling, texture synthesis, conversion or substitution occurs. The byte audit cannot establish native painting provenance, final decoded appearance, handcrafted artistic fidelity or real GPU ray tracing. Those remain independently reviewed on actual assets and devices.
