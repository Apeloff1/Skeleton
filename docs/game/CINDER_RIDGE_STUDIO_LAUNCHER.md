# Cinder Ridge — integrated offline game studio launcher

All original game production and playability systems are reachable through
one installed Python module, without dynamically importing user-supplied
module paths:

```bash
python -m skeleton.game.gameplay.ridge_rescue list
python -m skeleton.game.gameplay.ridge_rescue rescue demo
python -m skeleton.game.gameplay.ridge_rescue campaign demo
python -m skeleton.game.gameplay.ridge_rescue routebook run --track protect-route
python -m skeleton.game.gameplay.ridge_rescue tactics suggest
python -m skeleton.game.gameplay.ridge_rescue workbench interactive
python -m skeleton.game.gameplay.ridge_rescue league-demo
python -m skeleton.game.gameplay.ridge_rescue acceptance
```

The closed launcher also exposes mission objectives, replay journals,
offline packages and the earned offline league. Each subsystem delegates
to its own existing source-bound CLI. All saved output uses that subsystem's
create-only file policy. The launcher does not bypass CAS, replay checks,
source limits, original-game rights checks or required CI gates. Running
the acceptance command reports real outcomes and returns nonzero on
failure; authoring this launcher is not proof that the acceptance passed.
