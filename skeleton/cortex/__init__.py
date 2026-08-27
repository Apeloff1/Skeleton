"""Cortex — the model we are building, not implementing.

PFC (small / boilerplate) · midbrain (medium / coordinator) · left/right
hemispheres · Jeeves neocortex (hivemind + trainer). Slots are ModelPorts;
backends swap; acquire copies a tract into Jeeves' own system; surpass
answers from that system. Own-system recall is token-Jaccard; tracts
interchange between cortices. Specialist heads, corpus callosum, MoE
experts, sleep consolidation and REINFORCE are how neo acquires the
MODELS themselves and builds a system that surpasses them.
"""
from .port import (
    SLOTS,
    SCALES,
    CallableBackend,
    EchoBackend,
    ModelPort,
    Thought,
    fingerprint,
    jaccard,
    tokens,
)
from .pfc import TEMPLATES, PrefrontalCortex
from .midbrain import Midbrain
from .hemispheres import LeftHemisphere, RightHemisphere, ttk_oracle
from .distill import Ability, AbilityLedger, ability_from
from .own import MIN_JACCARD, OwnSystem, RecallHit, Tract, shadow_eval
from .curriculum import CORE_PAIRS, WALK_PAIRS, default_curriculum, train
from .neocortex import CortexTrace, JeevesCortex, local_slots
from .live import live_cortex, live_jeeves, persist, reset_live
from .lm import NGramLM, LanguageModelBackend, gameforge_corpus, gameforge_vocab
from .neural import NeuralLM, NeuralBackend
from .transformer import TinyTransformer, TransformerBackend
from .learned import LearnedWeights
from .device import probe, resolve, attach_lm
from .heads import BiasHead, NumericHead, PolicyHead, RouteHead, VetoHead
from .callosum import CorpusCallosum
from .moe import ExpertBank
from .sleep import SleepCycle
from .rl import ReinforceState, reinforce_mix

__all__ = [
    "SLOTS",
    "SCALES",
    "MIN_JACCARD",
    "CallableBackend",
    "EchoBackend",
    "ModelPort",
    "Thought",
    "fingerprint",
    "jaccard",
    "tokens",
    "TEMPLATES",
    "PrefrontalCortex",
    "Midbrain",
    "LeftHemisphere",
    "RightHemisphere",
    "ttk_oracle",
    "Ability",
    "AbilityLedger",
    "ability_from",
    "OwnSystem",
    "RecallHit",
    "Tract",
    "shadow_eval",
    "CORE_PAIRS",
    "WALK_PAIRS",
    "default_curriculum",
    "train",
    "CortexTrace",
    "JeevesCortex",
    "local_slots",
    "live_cortex",
    "live_jeeves",
    "persist",
    "reset_live",
    "NGramLM",
    "LanguageModelBackend",
    "gameforge_corpus",
    "gameforge_vocab",
    "NeuralLM",
    "NeuralBackend",
    "TinyTransformer",
    "TransformerBackend",
    "LearnedWeights",
    "probe",
    "resolve",
    "attach_lm",
    "NumericHead",
    "BiasHead",
    "RouteHead",
    "VetoHead",
    "PolicyHead",
    "CorpusCallosum",
    "ExpertBank",
    "SleepCycle",
    "ReinforceState",
    "reinforce_mix",
]
