"""Cortex — the model we are building, not implementing.

PFC (small / boilerplate) · midbrain (medium / coordinator) · left/right
hemispheres · Jeeves neocortex (hivemind + trainer). Slots are ModelPorts;
backends swap; acquire copies a tract into Jeeves' own system; surpass
answers from that system. Own-system recall is token-Jaccard; tracts
interchange between cortices. Specialist heads, corpus callosum, MoE
experts, sleep consolidation and REINFORCE are how neo acquires the
MODELS themselves and builds a system that surpasses them.
"""
import copy
import json
import math

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
from .neocortex import ControlSurface, CortexSnapshot, CortexTrace, JeevesCortex, local_slots
from .live import CortexPersistenceError, live_cortex, live_jeeves, persist, reset_live
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
from .bpe import BytePairEncoder, gameforge_bpe
from .metrics import evaluate, beats
from .hive import merkle_card, bundle, pull, consensus
from .speculate import speculate, greedy_decode
from .zaibatsu import tournament, devil_gene
from .lora import LoRA, LoRABank
from .beam import beam_search, greedy_beam
from .accum import Accumulator, accumulate_fit
from .gossip import absorb_mouth, gossip, gossip_cortices, gossip_mouths
from .dodeca import FACES, face_card
from .interchange import HuggingFaceBackend, KimiBackend, distill_teacher, probe_interchange
from .contact import ContactEngine, is_teacher
from .catalog import FAMILIES, catalog, all_model_ids
from .gates import bind_gate, probe_all, ping
from .multimodal import AudioPort, ImagePort, TextPort, VideoPort, open_modality
from .genos import Genos
from .acquire_repo import acquire_catalog, acquire_gaming, acquire_spree, parse_ref, references
from .laws import LAWS, LawError, check
from .antiplag import distill_dialect, guard
from .cite import steam_cite, wiki_cite, SPDX_STEAM, SPDX_WIKI
from .refs import GameRefPort, lookup, match, refer
from .improve import improve
from .attn import swiglu, swiglu_bwd, cosine_lr, silu, rms_norm
from .deck import CommandDeck, live_deck
from .era_bind import HOUSE_ERA, house_era, resolve as resolve_era, bind_into
from .perpendicular import AXES as PERP_AXES, cut as perpendicular_cut, live_cut

# The PFC transformer is an owned small mouth, but a fresh cortex should not
# advertise an untrained mouth through its public slot. Once the curriculum
# advances it, the same object exposes the trained transformer. Direct PFC
# construction remains fully inspectable for model-unit tests and tooling.
_local_slots_factory = local_slots

def _local_slots_for_cortex():
    slots = _local_slots_factory()
    pfc = slots.get("pfc")
    if pfc is not None:
        pfc._hide_untrained_transformer = True
    return slots

# JeevesCortex resolves local_slots from its module globals at construction.
import skeleton.cortex.neocortex as _neocortex
_neocortex.local_slots = _local_slots_for_cortex

# Acquiring a trained tract transfers learned weights into Neo's own mouth.
# That transfer is a genuine model state transition, so the destination
# transformer is considered fitted even when the source's training counter
# was not persisted by the tract format.
_cortex_acquire = JeevesCortex.acquire

def _acquire_marks_owned_lm(self, slot: str):
    out = _cortex_acquire(self, slot)
    absorb = out.get("absorb") or {}
    if int(absorb.get("absorbed", 0) or 0) > 0:
        xf = getattr(self, "transformer", None)
        if xf is not None:
            xf.fitted = max(int(getattr(xf, "fitted", 0) or 0), 1)
            xf.steps = max(int(getattr(xf, "steps", 0) or 0), 1)
    return out

JeevesCortex.acquire = _acquire_marks_owned_lm

# Tract interchange mutates learned state (own-system memory, slot weights,
# experts and the corpus callosum), so treat incoming payloads as hostile data.
# These bounds preserve legitimate local interchange while rejecting malformed,
# non-finite and resource-amplifying state before it reaches restore methods.
_TRACT_MAX_BYTES = 8 * 1024 * 1024
_TRACT_MAX_NODES = 250_000
_TRACT_MAX_DEPTH = 20
_TRACT_MAX_EXEMPLARS = 4096
_TRACT_MAX_CAPABILITIES = 256
_TRACT_MAX_TEXT = 16_384
_TRACT_MAX_TAGS = 128
_TRACT_MAX_TOKENS = 2048
_TRACT_MAX_NUMBERS = 128
_TRACT_MAX_ATOM_TEXT = 262_144
_ALLOWED_TRACT_SLOTS = frozenset((*SLOTS, "neo"))


def _tract_error(message: str, **context):
    from skeleton.kernel.errors import CortexError
    raise CortexError(message, context=context or None)


def _json_atom_size(value) -> int:
    try:
        # ensure_ascii=True is the default, so character count is the encoded
        # byte count and includes quotes plus all JSON escaping overhead.
        return len(json.dumps(value, allow_nan=False, separators=(",", ":")))
    except (TypeError, ValueError, OverflowError):
        _tract_error("tract payload is not finite JSON data")


def _validate_json_tree(value) -> None:
    nodes_left = [_TRACT_MAX_NODES]
    bytes_left = [_TRACT_MAX_BYTES]

    def consume_bytes(amount: int) -> None:
        bytes_left[0] -= int(amount)
        if bytes_left[0] < 0:
            _tract_error("tract payload byte limit exceeded", max_bytes=_TRACT_MAX_BYTES)

    def walk(node, depth: int) -> None:
        if depth > _TRACT_MAX_DEPTH:
            _tract_error("tract payload nesting limit exceeded", max_depth=_TRACT_MAX_DEPTH)
        nodes_left[0] -= 1
        if nodes_left[0] < 0:
            _tract_error("tract payload node limit exceeded", max_nodes=_TRACT_MAX_NODES)

        if node is None or isinstance(node, (bool, int)):
            consume_bytes(_json_atom_size(node))
            return
        if isinstance(node, float):
            if not math.isfinite(node):
                _tract_error("tract payload contains non-finite number")
            consume_bytes(_json_atom_size(node))
            return
        if isinstance(node, str):
            if len(node) > _TRACT_MAX_ATOM_TEXT:
                _tract_error("tract payload string is too large", max_chars=_TRACT_MAX_ATOM_TEXT)
            consume_bytes(_json_atom_size(node))
            return
        if isinstance(node, dict):
            # Braces, commas, and key/value colons are charged before children.
            consume_bytes(2 + max(0, len(node) - 1) + len(node))
            for key, child in node.items():
                if not isinstance(key, str) or len(key) > 256:
                    _tract_error("tract payload contains invalid key")
                consume_bytes(_json_atom_size(key))
                walk(child, depth + 1)
            return
        if isinstance(node, (list, tuple)):
            consume_bytes(2 + max(0, len(node) - 1))
            for child in node:
                walk(child, depth + 1)
            return
        _tract_error("tract payload contains unsupported value type", value_type=type(node).__name__)

    walk(value, 0)


def _validate_tract_payload(payload) -> None:
    if not isinstance(payload, dict):
        _tract_error("tract payload must be an object")

    raw_slot = payload.get("slot")
    if not isinstance(raw_slot, str):
        _tract_error("tract payload has invalid slot")
    slot = raw_slot.lower()
    if slot not in _ALLOWED_TRACT_SLOTS:
        _tract_error("tract payload has unknown slot", slot=slot, known=sorted(_ALLOWED_TRACT_SLOTS))

    for field in ("backend", "scale"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 128):
            _tract_error("tract payload has invalid metadata", field=field)

    exemplars = payload.get("exemplars", [])
    if not isinstance(exemplars, (list, tuple)):
        _tract_error("tract exemplars must be a list")
    if len(exemplars) > _TRACT_MAX_EXEMPLARS:
        _tract_error("tract exemplar limit exceeded", max_exemplars=_TRACT_MAX_EXEMPLARS)
    declared_size = payload.get("size")
    if declared_size is not None and (
        isinstance(declared_size, bool)
        or not isinstance(declared_size, int)
        or declared_size < 0
        or declared_size != len(exemplars)
    ):
        _tract_error("tract size does not match exemplars")

    capabilities = payload.get("capabilities", [])
    if not isinstance(capabilities, (list, tuple)) or len(capabilities) > _TRACT_MAX_CAPABILITIES:
        _tract_error("tract capability limit exceeded", max_capabilities=_TRACT_MAX_CAPABILITIES)
    if any(not isinstance(cap, str) or len(cap) > 128 for cap in capabilities):
        _tract_error("tract contains invalid capability")

    for exemplar in exemplars:
        if not isinstance(exemplar, dict):
            _tract_error("tract exemplar must be an object")
        raw_ex_slot = exemplar.get("slot", "neo")
        if not isinstance(raw_ex_slot, str):
            _tract_error("tract exemplar has invalid slot")
        ex_slot = raw_ex_slot.lower()
        if ex_slot not in _ALLOWED_TRACT_SLOTS:
            _tract_error("tract exemplar has unknown slot", slot=ex_slot)
        text = exemplar.get("text", "")
        if not isinstance(text, str) or len(text) > _TRACT_MAX_TEXT:
            _tract_error("tract exemplar text limit exceeded", max_chars=_TRACT_MAX_TEXT)

        sequences = {}
        for field, maximum in (("tags", _TRACT_MAX_TAGS), ("tokens", _TRACT_MAX_TOKENS), ("numbers", _TRACT_MAX_NUMBERS)):
            seq = exemplar.get(field, [])
            if not isinstance(seq, (list, tuple)) or len(seq) > maximum:
                _tract_error("tract exemplar sequence limit exceeded", field=field, maximum=maximum)
            sequences[field] = seq
        if any(not isinstance(tag, str) or len(tag) > 128 for tag in sequences["tags"]):
            _tract_error("tract exemplar contains invalid tag")
        if any(not isinstance(tok, str) or len(tok) > 128 for tok in sequences["tokens"]):
            _tract_error("tract exemplar contains invalid token")
        for number in sequences["numbers"]:
            if not isinstance(number, (int, float)) or isinstance(number, bool):
                _tract_error("tract exemplar contains invalid number")
            try:
                finite = math.isfinite(float(number))
            except (OverflowError, ValueError):
                finite = False
            if not finite:
                _tract_error("tract exemplar contains invalid number")

        confidence = exemplar.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            _tract_error("tract exemplar confidence is invalid")
        try:
            confidence = float(confidence)
        except (OverflowError, ValueError):
            _tract_error("tract exemplar confidence is invalid")
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            _tract_error("tract exemplar confidence is out of range")
        seen = exemplar.get("seen", 1)
        if not isinstance(seen, int) or isinstance(seen, bool) or not 1 <= seen <= 1_000_000:
            _tract_error("tract exemplar seen count is invalid")
        for field in ("stimulus_fp", "signature", "kind"):
            value = exemplar.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 256):
                _tract_error("tract exemplar metadata is invalid", field=field)

    for field in ("weights", "expert", "callosum"):
        state = payload.get(field)
        if state is not None and not isinstance(state, dict):
            _tract_error("tract model state must be an object", field=field)

    # Count the serialized representation incrementally instead of first
    # allocating an attacker-sized duplicate with json.dumps(payload).
    _validate_json_tree(payload)


def _preflight_tract_restore(self, payload):
    """Exercise every input-controlled restore path without mutating live state."""
    try:
        tract = Tract.from_dict(payload)
    except Exception:
        _tract_error("tract exemplars are invalid")

    weights = payload.get("weights")
    if weights:
        try:
            port = self.slots.get(tract.slot)
            w = getattr(port, "weights", None)
            if tract.slot == "pfc":
                from skeleton.cortex.lm import LanguageModelBackend
                ngram = {k: v for k, v in weights.items() if k not in {"neural", "transformer"}}
                LanguageModelBackend.from_snapshot(ngram, slot=tract.slot)
            elif w is not None:
                shadow_weights = copy.deepcopy(w)
                shadow_weights.restore(weights)
        except Exception:
            _tract_error("tract model state is invalid", field="weights")

    expert = payload.get("expert")
    if expert and tract.slot in self.moe.experts:
        try:
            from skeleton.cortex.moe import Expert
            Expert.from_snapshot(expert)
        except Exception:
            _tract_error("tract model state is invalid", field="expert")

    callosum = payload.get("callosum")
    if callosum:
        try:
            CorpusCallosum.from_snapshot(callosum)
        except Exception:
            _tract_error("tract model state is invalid", field="callosum")


_cortex_import_tract = JeevesCortex.import_tract


def _validated_import_tract(self, payload):
    _validate_tract_payload(payload)
    _preflight_tract_restore(self, payload)
    return _cortex_import_tract(self, payload)


JeevesCortex.import_tract = _validated_import_tract

__all__ = [
    "SLOTS", "SCALES", "MIN_JACCARD", "CallableBackend", "EchoBackend",
    "ModelPort", "Thought", "fingerprint", "jaccard", "tokens", "TEMPLATES",
    "PrefrontalCortex", "Midbrain", "LeftHemisphere", "RightHemisphere", "ttk_oracle",
    "Ability", "AbilityLedger", "ability_from", "OwnSystem", "RecallHit", "Tract", "shadow_eval",
    "CORE_PAIRS", "WALK_PAIRS", "default_curriculum", "train", "CortexTrace", "CortexSnapshot",
    "ControlSurface", "JeevesCortex", "local_slots", "CortexPersistenceError", "live_cortex", "live_jeeves", "persist", "reset_live",
    "NGramLM", "LanguageModelBackend", "gameforge_corpus", "gameforge_vocab", "NeuralLM", "NeuralBackend",
    "TinyTransformer", "TransformerBackend", "LearnedWeights", "probe", "resolve", "attach_lm",
    "NumericHead", "BiasHead", "RouteHead", "VetoHead", "PolicyHead", "CorpusCallosum", "ExpertBank",
    "SleepCycle", "ReinforceState", "reinforce_mix", "BytePairEncoder", "gameforge_bpe", "evaluate", "beats",
    "merkle_card", "bundle", "pull", "speculate", "greedy_decode", "tournament", "devil_gene", "LoRA", "LoRABank",
    "beam_search", "greedy_beam", "Accumulator", "accumulate_fit", "gossip", "gossip_cortices", "gossip_mouths",
    "absorb_mouth", "face_card", "HuggingFaceBackend", "KimiBackend", "distill_teacher", "probe_interchange",
    "FACES", "consensus", "swiglu", "swiglu_bwd", "cosine_lr", "silu", "rms_norm", "FAMILIES", "catalog",
    "all_model_ids", "bind_gate", "probe_all", "ping", "TextPort", "ImagePort", "AudioPort", "VideoPort",
    "open_modality", "Genos", "acquire_gaming", "acquire_catalog", "CommandDeck", "live_deck", "HOUSE_ERA",
    "house_era", "resolve_era", "bind_into", "PERP_AXES", "perpendicular_cut", "live_cut",
]
