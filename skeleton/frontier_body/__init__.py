"""Playable bindings for shoreline liquid, atmosphere audio, skin/fascia, and instruments.

The package calls the existing Jeeves reference solvers. It does not start a
second physics runtime, and it does not read operating-system sensors.
"""

from .atmosphere_audio import (
    BUS_NAMES,
    AudioMixError,
    AudioParameterSample,
    AtmosphereAudioFrame,
    BlockerSegment,
    blocker_occlusion,
    parameter_stream,
    render_pcm_preview,
)
from .instrument_journal import (
    SIMULATED_LABEL,
    CalibrationEpoch,
    InstrumentJournal,
    InstrumentJournalError,
    SimulatedReading,
    append_reading,
    dump_instrument_journal,
    load_instrument_journal,
    open_instrument_journal,
    replay_instrument_journal,
)
from .integration import (
    AnatomicalSkinIntegrator,
    ReferenceAnatomicalSkinIntegrator,
    SkinIntegrationError,
    SkinIntegrationRequest,
    SkinIntegrationResult,
)
from .shoreline import (
    VOLUME_CONSERVATION_EPSILON_M3,
    CollisionBox,
    CoastalJournal,
    CoastalLiquidStep,
    CoastalTerrain,
    ShorelineError,
    commit_coastal_terrain,
    dump_coastal_journal,
    load_coastal_journal,
    step_coastal_liquid,
)

__all__ = (
    "BUS_NAMES",
    "SIMULATED_LABEL",
    "VOLUME_CONSERVATION_EPSILON_M3",
    "AnatomicalSkinIntegrator",
    "AudioMixError",
    "AudioParameterSample",
    "AtmosphereAudioFrame",
    "BlockerSegment",
    "CalibrationEpoch",
    "CollisionBox",
    "CoastalJournal",
    "CoastalLiquidStep",
    "CoastalTerrain",
    "InstrumentJournal",
    "InstrumentJournalError",
    "ReferenceAnatomicalSkinIntegrator",
    "ShorelineError",
    "SimulatedReading",
    "SkinIntegrationError",
    "SkinIntegrationRequest",
    "SkinIntegrationResult",
    "append_reading",
    "blocker_occlusion",
    "commit_coastal_terrain",
    "dump_coastal_journal",
    "dump_instrument_journal",
    "load_coastal_journal",
    "load_instrument_journal",
    "open_instrument_journal",
    "parameter_stream",
    "render_pcm_preview",
    "replay_instrument_journal",
    "step_coastal_liquid",
)
