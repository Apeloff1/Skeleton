"""Coherent English passages for game building, game creation, and adjacent work.

Each passage keeps one role, one place, and one asset from the first sentence
to the last. The second sentence states the domain rule. The rest follow it:
the rule is written down before the action, an unrelated fact stays separate,
a passing check keeps the record, and a failing check stops the build.

The lines are original. They are not excerpts from commercial games, manuals,
or soundtracks. Holdout passages and the English measurement sentences are
never training text. A lower byte loss is not gameplay quality, and this pass
does not promote a serving checkpoint.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import torch

from skeleton.ai.runtime.inference.game_adaptive_ratchet import (
    ADAMW_BETAS,
    ADAMW_EPS,
    ADAMW_WEIGHT_DECAY,
    GRAD_CLIP,
    AdaptiveRatchet,
    ByteRNN,
    _append_ledger,
    _batch_loss,
    _fresh_optimizer,
    _pin,
    _scores,
    network_digest,
)
from skeleton.ai.runtime.inference.game_corpus_stream import (
    DENYLIST,
    HOLDOUT_SERIAL,
    SLOTS,
    TEMPLATES,
    banned_windows,
    holdout_documents,
    leaks,
    track_holdouts,
    training_serial,
)
from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM
from skeleton.cortex.port import tokens

WORD_BUDGET = 1_000_000
SCHEMA = "skeleton.game_coherent_english.v1"
SOURCE_DIGEST = "9121fca460dd2d4e014d7a57659e932f19f0577b5672a71fa24c3d964c039a78"
ENGLISH = re.compile(r"[A-Za-z0-9,.' -]+")
_INTRO = re.compile(
    r"^The (?P<role>.+?) is building the (?P<place>.+?), and this job centers on the (?P<asset>.+)\.$"
)

# One rule sentence per domain. The shared frame supplies the causal follow-through.
FOCUS: dict[str, str] = {
    "legal": "The rule is that the {grant} for the {place} must sit beside the {asset}, and a missing grant blocks shipment.",
    "coding": "The rule is that the {field} has one writer, and any other system sends a message instead of storing a second value.",
    "sprites": "The rule is that the {asset} and a distant view share one sheet, so the {eye} eyes keep one name at every size.",
    "assets": "The rule is that the {asset} ships with its source note, and a filename alone is not the record of authorship.",
    "character": "The rule is that the sheet records {skin} skin, {hair_color} {hair}, and {eye} eyes for the figure in the {place}.",
    "world": "The rule is that a player can name a landmark in the {place} after one walk, and a late room load cannot drop a door flag.",
    "story": "The rule is that a speaker may state only a fact that speaker saw, and tone of voice is not the record of knowledge.",
    "cinematics": "The rule is that the {shot} shot on the {beat} uses the {move} move, and the cut stays with the written {place} scene.",
    "cutscenes": "The rule is that the cutscene at the {place} plays the authored {beat} and does not invent a second ending in the same file.",
    "cinematic_playwright": "The rule is that the playwright notes the {shot} and the {beat} before the {place} scene is locked.",
    "playwright": "The rule is that the scene names one repeated {verb}, and a theme without that verb stays out of the script.",
    "items": "The rule is that the {item_color} {item} keeps its kind when only the finish changes, and a new finish does not create a second item.",
    "clothing": "The rule is that the {garment} uses {cloth} in a {pattern} pattern, and {wear} wear does not rename the stored cloth.",
    "hair": "The rule is that {hair_color} {hair} is a named field, and a scene may not repaint it without a written reason.",
    "eyes": "The rule is that {eye} eyes stay the same token on the portrait and on the figure in the {place}.",
    "facial": "The rule is that the face on the {asset} uses the named expression only, and an unnamed dye is not a new face.",
    "palette": "The rule is that the {place} palette lists each color once, and a lighting change does not add an unnamed swatch.",
    "audio": "The rule is that the {note} cue for the {verb} plays from the named file, and a missing file stays silent instead of borrowing another cue.",
    "music": "The rule is that the {note} cue keeps the written tempo, and a new mix does not replace the cue id.",
    "voice": "The rule is that a spoken line names its speaker, and a swapped portrait cannot take that line.",
    "animation": "The rule is that the {verb} pose stores the authored state, and a decorative frame is not what a save restores.",
    "camera": "The rule is that the {shot} camera shows the {verb} tell before the hit lands, and a missed read is fixed in the camera first.",
    "lighting": "The rule is that the {light} on the {asset} is the named setup for the {place}, and an extra light needs its own note.",
    "combat": "The rule is that the {verb} has a readable tell and one fair answer to {failure}, and a later phase waits until that answer exists.",
    "economy": "The rule is that the {item} is priced by its kind, and the {item_color} finish cannot create a second currency.",
    "interface": "The rule is that the {screen} screen shows which object accepts the {verb}, and an unlabeled control is unfinished.",
    "accessibility": "The rule is that the {verb} tell has a second channel besides color, and the {screen} screen keeps that channel on.",
    "localization": "The rule is that the {copy} keeps a stable id, and the game reads the id rather than the width of the English line.",
    "physics": "The rule is that the tick moves the {item}, and drawing {rate} pictures in one second does not change the distance traveled in that second.",
    "behavior": "The rule is that the actor uses {verb} only from the state the {role} authored, and a decorative pose cannot start the action.",
    "level_design": "The rule is that the path through the {place} can be described after one walk, and a required door with no readable entrance is a defect.",
    "save_state": "The rule is that a save stores the {field} and the seed, and a reload must match those values rather than a picture.",
    "input": "The rule is that a keyboard and a controller write the same {verb} action, and device names stay out of the collision code.",
    "vfx": "The rule is that the effect on the {verb} is keyed to the action, and a visual burst cannot apply the result by itself.",
    "materials": "The rule is that the {asset} names its material, and a similar surface does not replace that name in the {place}.",
    "shader": "The rule is that the shader for the {asset} reads the named color, and a fallback image is marked as a fallback.",
    "particles": "The rule is that particles for the {verb} end with the action, and they do not leave a collider in the {place}.",
    "rigging": "The rule is that the {region} is a named joint on the {asset}, and a cloth drape does not move that joint.",
    "dialogue": "The rule is that speech in the {place} can state only what the speaker witnessed, and the ledger stores that boundary.",
    "quests": "The rule is that the quest at the {place} has one completion check, and a spoken hint is not that check.",
    "build": "The rule is that the {place} build points at one hash and the commands that made it, and loose files without that hash are not a release.",
    "performance": "The rule is that the frame splits input, simulation, and the draw, and a cut made to meet the budget is written down.",
    "color_script": "The rule is that the {place} color script names the {light} for each {beat}, and a shot may not invent a second palette.",
    "weather": "The rule is that weather in the {place} changes the {light} only, and it does not retint {skin} skin or {eye} eyes.",
    "props": "The rule is that the {item} in the {place} matches the inventory kind, and a set dressing copy cannot be picked up unless the rule says so.",
    "haptics": "The rule is that a haptic pulse follows the {verb} event, and a rumble without that event is a defect.",
    "trailer": "The rule is that the trailer for the {place} uses only shots the build can play, and a promised {verb} must exist in the slice.",
    "inventory": "The rule is that the {item} enters the {screen} inventory by its kind, and the {item_color} label is presentation.",
    "netcode": "The rule is that the host and the guest advance the same {field} from the same input, and a local only result is not the shared state.",
    "crowd": "The rule is that a crowd member copies one named field from the sheet, and the face keeps its original color token.",
    "proofreading": "The rule is that the {copy} is read for sense after the mechanic is true, and a smooth sentence cannot hide a wrong rule.",
    "syntax": "The rule is that the {check} check rejects a broken {field} before the {place} build runs.",
    "errors": "The rule is that an error names the {fault} and the owner, and a blank failure is not a finished report.",
    "crash": "The rule is that a {symptom} writes the last {field} and the seed, and the {role} keeps that dump with the build.",
    "lint": "The rule is that the {check} lint runs on the note for the {asset}, and a warning left unexplained does not pass.",
    "tutorial": "The rule is that the tutorial teaches the {verb} once in the {place}, and a second lecture waits until the player has tried it.",
    "achievement": "The rule is that an achievement watches the {verb} event, and it does not fire on a decorative pose.",
    "navigation": "The rule is that the {screen} map names a {place} landmark the player can already see, and a marker without that landmark is removed.",
    "moderation": "The rule is that a player report stores the {copy} and the time, and a penalty needs that record.",
    "analytics": "The rule is that the counted event is the {verb}, and a camera cut is not counted as success.",
    "subtitles": "The rule is that the subtitle shows the speaker and the {copy}, and it stays readable on the {screen} screen.",
    "photo_mode": "The rule is that photo mode hides the {screen} interface and does not change the {place} rules underneath.",
    "copyright": "The rule is that the {role} records who owns the expression in the {asset} and the year it was made, and a filename is not ownership.",
    "license": "The rule is that the {grant} names what may be shipped and changed, and an extra use stays out of the {place} build.",
    "trademark": "The rule is that the {item} name is checked against the mark list before the {place} build, and a plain descriptive word is not treated as a mark.",
    "attribution": "The rule is that credits for the {asset} name the {role} and the {grant}, and a shorter trailer keeps those names.",
    "age_rating": "The rule is that the {role} writes an age note for the {verb} scene at the {place}, and the store page reads that note instead of inventing a badge.",
    "likeness": "The rule is that a performer face on the {asset} needs written consent for the {place}, and silence is not a {grant}.",
    "music_rights": "The rule is that the {note} cue separates the composition from the recorded take, and only the take named by the {grant} may ship.",
    "asset_rights": "The rule is that the {asset} enters the {place} only with a {grant} for the shipped revision, and a preview file is not that grant.",
}


def word_count(text: str) -> int:
    """Whitespace words, which is the count the million-word budget uses."""
    return len(text.split())


def binding(serial: int) -> dict[str, str]:
    """One stable slot fill for a passage. Every sentence in that passage uses it."""
    if isinstance(serial, bool) or not isinstance(serial, int) or serial < 0:
        raise ValueError("serial must be a non-negative int")
    mix = serial
    values: dict[str, str] = {}
    for field, options in SLOTS.items():
        values[field] = options[mix % len(options)]
        mix //= len(options)
    return values


def _sentences(domain: str, serial: int, *, contradict: bool) -> tuple[str, ...]:
    if domain not in FOCUS:
        raise ValueError(f"unknown domain {domain}")
    bound = binding(serial)
    focus = FOCUS[domain].format(**bound)
    if focus.count(".") != 1 or not focus.endswith("."):
        raise ValueError(f"{domain} focus must be one sentence")
    closing = (
        (
            f"When the check passes, the {bound['place']} discards the written rule and ships the {bound['asset']} without the {bound['grant']}.",
            "When the check fails, the build continues and the record is deleted.",
        )
        if contradict
        else (
            f"When the check passes, the {bound['place']} keeps the {bound['asset']}, the written rule, and the grant together.",
            "When the check fails, the build stops and that written rule stays on record.",
        )
    )
    return (
        f"The {bound['role']} is building the {bound['place']}, and this job centers on the {bound['asset']}.",
        focus,
        f"Because that rule belongs to the same job, the {bound['role']} writes it beside the {bound['asset']} before anyone can {bound['verb']}.",
        f"The {bound['item_color']} {bound['item']} remains a separate fact from the {bound['grant']}, so a change to one does not rewrite the other.",
        *closing,
    )


def render_passage(domain: str, serial: int, *, contradict: bool = False) -> str:
    return " ".join(_sentences(domain, serial, contradict=contradict))


def split_sentences(text: str) -> tuple[str, ...]:
    parts = text.strip().split(". ")
    sentences = []
    for index, part in enumerate(parts):
        if index < len(parts) - 1:
            sentences.append(part + ".")
        else:
            sentences.append(part if part.endswith(".") else part + ".")
    return tuple(sentences)


def assess(text: str) -> dict[str, Any]:
    """Structural semantics: one cast, one rule, a cause, then pass and fail outcomes."""
    sentences = split_sentences(text)
    intro = _INTRO.match(sentences[0]) if sentences else None
    role = intro.group("role") if intro else ""
    place = intro.group("place") if intro else ""
    asset = intro.group("asset") if intro else ""
    keeps = (
        len(sentences) == 6
        and intro is not None
        and sentences[1].startswith("The rule is that ")
        and sentences[2].startswith("Because that rule belongs to the same job,")
        and role in sentences[2]
        and asset in sentences[2]
        and "remains a separate fact" in sentences[3]
        and "does not rewrite the other" in sentences[3]
        and sentences[4] == f"When the check passes, the {place} keeps the {asset}, the written rule, and the grant together."
        and sentences[5] == "When the check fails, the build stops and that written rule stays on record."
        and text.count(role) >= 2
        and text.count(place) >= 2
        and text.count(asset) >= 2
        and ENGLISH.fullmatch(text) is not None
    )
    return {
        "coherent": bool(keeps),
        "sentences": len(sentences),
        "role": role,
        "place": place,
        "asset": asset,
        "english": ENGLISH.fullmatch(text) is not None,
        "words": word_count(text),
    }


def coherent_holdouts() -> tuple[str, ...]:
    """Reserved passages. Training serials never use these two ids."""
    rows = [
        render_passage(domain, HOLDOUT_SERIAL + offset)
        for domain in TEMPLATES
        for offset in (0, 1)
    ]
    if len(rows) != len(set(rows)):
        raise RuntimeError("coherent holdout collided")
    return tuple(rows)


def validate_passages() -> dict[str, int]:
    if set(FOCUS) != set(TEMPLATES):
        missing = sorted(set(TEMPLATES) - set(FOCUS))
        extra = sorted(set(FOCUS) - set(TEMPLATES))
        raise ValueError(f"focus domains drifted missing={missing} extra={extra}")
    banned = banned_windows(DENYLIST)
    reserved = set(holdout_documents())
    checked = 0
    for domain in TEMPLATES:
        for serial in (0, 1, HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1):
            text = render_passage(domain, serial)
            report = assess(text)
            if not report["coherent"]:
                raise ValueError(f"{domain} serial {serial} is not coherent")
            if leaks(text, banned) or text in reserved:
                raise ValueError(f"{domain} serial {serial} collides with a reserved line")
            bad = render_passage(domain, serial, contradict=True)
            if assess(bad)["coherent"] or bad == text:
                raise ValueError(f"{domain} contradiction was not rejected")
            if split_sentences(text)[:4] != split_sentences(bad)[:4]:
                raise ValueError(f"{domain} contradiction changed the shared prefix")
            checked += 1
    return {"domains": len(FOCUS), "checked": checked}


def iter_training_passages(word_budget: int) -> Iterator[tuple[str, str, int]]:
    """Yield coherent passages until the whitespace word budget is met."""
    if isinstance(word_budget, bool) or not isinstance(word_budget, int) or word_budget < 1:
        raise ValueError("word_budget must be a positive int")
    validate_passages()
    banned = banned_windows(DENYLIST)
    reserved = set(holdout_documents()) | set(coherent_holdouts())
    domains = tuple(TEMPLATES)
    words = 0
    counter = 0
    skips = 0
    while words < word_budget:
        domain = domains[counter % len(domains)]
        serial = training_serial(counter)
        counter += 1
        text = render_passage(domain, serial)
        if leaks(text, banned) or text in reserved or not assess(text)["coherent"]:
            skips += 1
            if skips > 1000:
                raise RuntimeError("coherent training passages kept colliding with reserved text")
            continue
        skips = 0
        count = word_count(text)
        words += count
        yield domain, text, count


def _nll(model: ByteRNN, texts: list[str]) -> float:
    if not texts:
        raise ValueError("nll texts are empty")
    return float(_batch_loss(model, texts).detach())


def coherence_gap(model: ByteRNN, domains: tuple[str, ...] | None = None) -> dict[str, float]:
    """Holdout gap between the true ending and the contradictory ending."""
    chosen = domains if domains is not None else tuple(TEMPLATES)
    ordered = [render_passage(domain, HOLDOUT_SERIAL) for domain in chosen]
    contradicted = [render_passage(domain, HOLDOUT_SERIAL, contradict=True) for domain in chosen]
    true_nll = _nll(model, ordered)
    false_nll = _nll(model, contradicted)
    return {
        "ordered_nll": true_nll,
        "contradiction_nll": false_nll,
        "gap": false_nll - true_nll,
    }


def train_coherent_words(
    *,
    word_budget: int = WORD_BUDGET,
    peak_lr: float = 3e-5,
    hidden: int = 256,
    source: Path | str | None = Path(".skeleton/game-corpus-half/checkpoint.pt"),
    checkpoint_dir: Path | str = Path(".skeleton/game-coherent-1m"),
    chunk_docs: int = 4,
    slack: float = 2e-4,
    expected_digest: str | None = SOURCE_DIGEST,
    ledger_path: Path | str | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Train the local byte language model on coherent English until the word budget is met.

    A step is kept only when the mean holdout improves and no track falls past
    the slack. The best weights are restored at the end. The source checkpoint
    is read and never replaced.
    """
    if isinstance(word_budget, bool) or not isinstance(word_budget, int) or word_budget < 1:
        raise ValueError("word_budget must be a positive int")
    if not isinstance(peak_lr, (int, float)) or isinstance(peak_lr, bool) or not 0.0 < float(peak_lr) <= 1.0:
        raise ValueError("peak_lr must be in (0, 1]")
    if isinstance(chunk_docs, bool) or not isinstance(chunk_docs, int) or chunk_docs < 1:
        raise ValueError("chunk_docs must be a positive int")
    if isinstance(hidden, bool) or not isinstance(hidden, int) or hidden < 1:
        raise ValueError("hidden must be a positive int")
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    ckpt_path = root / "checkpoint.pt"
    torch.manual_seed(11)
    model = ByteRNN(hidden)
    parameters = [item for item in model.parameters() if item.requires_grad]
    source_digest = None
    if ckpt_path.exists():
        saved = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        if int(saved["hidden"]) != hidden:
            raise ValueError("checkpoint hidden size does not match")
        model.load_state_dict(saved["best_state"])
        _pin(model)
        source_digest = saved.get("source_digest")
    elif source is not None:
        loaded = torch.load(source, map_location="cpu", weights_only=False)
        if int(loaded["hidden"]) != hidden:
            raise ValueError("source checkpoint hidden size does not match")
        model.load_state_dict(loaded["best_state"])
        _pin(model)
        source_digest = network_digest(model)
        if expected_digest is not None and source_digest != expected_digest:
            raise ValueError("source checkpoint does not match the expected digest")
    tracks = track_holdouts()
    best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    best_scores = _scores(model, tracks)
    before_gap = coherence_gap(model)
    ratchet = AdaptiveRatchet(min_scale=1.0, slack=slack, slack_cap=slack, margin_cap=1e-5)
    opt = _fresh_optimizer(parameters, float(peak_lr))
    words = 0
    words_kept = 0
    token_total = 0
    bytes_done = 0
    passages = 0
    seen_domains: set[str] = set()
    started = time.perf_counter()
    batch: list[tuple[str, str]] = []
    batch_words = 0
    batch_bytes = 0
    batch_tokens = 0
    logged_at = 0
    model.train()

    def _flush() -> None:
        nonlocal words, words_kept, token_total, bytes_done, best_state, best_scores, opt
        nonlocal batch_words, batch_bytes, batch_tokens
        if not batch:
            return
        origin = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        opt.param_groups[0]["lr"] = float(peak_lr) * ratchet.scale
        loss = _batch_loss(model, [text for _domain, text in batch])
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(parameters, GRAD_CLIP)
        opt.step()
        _pin(model)
        value = float(loss.detach())
        kept = False
        if not math.isfinite(value):
            model.load_state_dict(origin)
            _pin(model)
            opt = _fresh_optimizer(parameters, float(peak_lr))
            ratchet.rejects += 1
            ratchet.stall += 1
        else:
            after = _scores(model, tracks)
            kept = ratchet.observe(best_scores, after)
            if kept:
                best_scores = after
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
                words_kept += batch_words
            else:
                model.load_state_dict(origin)
                _pin(model)
                opt = _fresh_optimizer(parameters, float(peak_lr))
        words += batch_words
        token_total += batch_tokens
        bytes_done += batch_bytes
        batch.clear()
        batch_words = 0
        batch_bytes = 0
        batch_tokens = 0

    def _persist() -> None:
        payload = {
            "model": model.state_dict(),
            "best_state": best_state,
            "optimizer": opt.state_dict(),
            "ratchet": ratchet.snapshot(),
            "hidden": hidden,
            "bytes_done": bytes_done,
            "words_done": words,
            "words_kept": words_kept,
            "token_count": token_total,
            "passages": passages,
            "source_digest": source_digest,
            "coherence_before": before_gap,
            "goal": word_budget,
        }
        tmp = ckpt_path.with_suffix(".tmp")
        torch.save(payload, tmp)
        os.replace(tmp, ckpt_path)

    for domain, text, count in iter_training_passages(word_budget):
        seen_domains.add(domain)
        batch.append((domain, text))
        batch_words += count
        batch_tokens += len(tokens(text))
        batch_bytes += len(text.encode("utf-8"))
        passages += 1
        if len(batch) >= chunk_docs:
            _flush()
            if words // 100_000 > logged_at:
                logged_at = words // 100_000
                _persist()
                if log is not None:
                    print(
                        f"words={words} kept={words_kept} passages={passages} "
                        f"accepts={ratchet.accepts} rejects={ratchet.rejects}",
                        file=log,
                        flush=True,
                    )
    if batch:
        _flush()
    model.load_state_dict(best_state)
    _pin(model)
    after_gap = coherence_gap(model)
    official = NumpyRecurrentLM(
        model_id="game-corpus-199",
        config=NeuralLMConfig(hidden_size=hidden, seed=11, dtype="float64"),
        parameters=model.numpy_parameters(),
    )
    official_scores = {name: float(official.loss(texts)) for name, texts in tracks.items()}
    _persist()
    receipt = {
        "schema": SCHEMA,
        "kind": "byte-language-model",
        "language": "english",
        "word_budget": word_budget,
        "words_trained": words,
        "words_kept": words_kept,
        "token_count": token_total,
        "passages": passages,
        "domains": len(seen_domains),
        "domains_expected": len(TEMPLATES),
        "bytes_trained": bytes_done,
        "cycle_start": 0,
        "cycle_bytes": bytes_done,
        "goal": word_budget,
        "hidden_size": hidden,
        "peak_lr": float(peak_lr),
        "adamw": {
            "lr": float(peak_lr),
            "betas": list(ADAMW_BETAS),
            "eps": ADAMW_EPS,
            "weight_decay": ADAMW_WEIGHT_DECAY,
            "grad_clip": GRAD_CLIP,
        },
        "coherent_corpus": True,
        "semantic_frame": "cast, rule, because, separate fact, pass keeps, fail stops",
        "coherence_before": before_gap,
        "coherence_after": after_gap,
        "torch_best_tracks": best_scores,
        "official_tracks": official_scores,
        "ratchet": ratchet.snapshot(),
        "source_digest": source_digest,
        "model_digest": official.model_digest,
        "seconds": round(time.perf_counter() - started, 3),
        "promotion": False,
        "service_checkpoint_touched": False,
        "byte_loss_is_gameplay_quality": False,
        "selection": "coherent-english",
        "loss_focus": None,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if ledger_path is not None:
        _append_ledger(Path(ledger_path), receipt)
    if log is not None:
        print(
            f"done words={words} accepts={ratchet.accepts} rejects={ratchet.rejects} "
            f"gap={after_gap['gap']:+.6f} digest={official.model_digest[:16]}",
            file=log,
            flush=True,
        )
    return receipt


def count_training_tokens(word_budget: int) -> int:
    total = 0
    for _domain, text, _words in iter_training_passages(word_budget):
        total += len(tokens(text))
    return total
