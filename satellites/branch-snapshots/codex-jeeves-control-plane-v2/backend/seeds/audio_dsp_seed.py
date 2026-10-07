"""
Audio Synthesis & DSP knowledge base.
Collection: `audio_dsp`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

SYNTH_PRESETS = [
    ("sine",     {"waveform":"sine","harmonics":1}),
    ("saw-supersaw",{"waveform":"saw","detune_cents":7,"voices":7}),
    ("square-pwm",{"waveform":"square","pulse_width":0.45,"pwm_rate_hz":0.5}),
    ("fm-2op",   {"algo":"2op-fm","mod_index":3.2,"ratio":"2:1"}),
    ("fm-6op-dx",{"algo":"6op-fm-dx","feedback":4}),
    ("wavetable",{"waveform":"wavetable","tables":64}),
    ("granular", {"grain_ms":40,"density":24,"jitter":0.3}),
    ("physical-string",{"algo":"karplus-strong","damping":0.998}),
    ("physical-tube",  {"algo":"waveguide","length_m":0.85}),
    ("additive-32",{"partials":32,"decay_curve":"linear"}),
    ("subtractive",{"osc":"saw","filter":"lp-24","cutoff_hz":2200}),
    ("vocoder",  {"bands":16,"carrier":"saw"}),
]
DSP_FX = [
    ("lowpass",       {"order":2,"cutoff_hz":2000,"q":0.707}),
    ("highpass",      {"order":2,"cutoff_hz":120,"q":0.707}),
    ("bandpass",      {"center_hz":1200,"q":2}),
    ("reverb-plate",  {"size":0.7,"damping":0.4,"wet":0.3}),
    ("reverb-conv",   {"impulse_len_s":3.2}),
    ("delay-tape",    {"time_ms":380,"feedback":0.42,"wow":0.02}),
    ("chorus",        {"rate_hz":0.6,"depth":0.3,"voices":3}),
    ("flanger",       {"rate_hz":0.2,"depth":0.8,"feedback":0.6}),
    ("phaser",        {"stages":6,"rate_hz":0.4}),
    ("distortion-soft",{"drive_db":12,"shape":"tanh"}),
    ("distortion-hard",{"drive_db":24,"shape":"clip"}),
    ("bitcrusher",    {"bits":6,"downsample_factor":4}),
    ("compressor",    {"ratio":4,"attack_ms":10,"release_ms":120,"threshold_db":-18}),
    ("limiter",       {"threshold_db":-1,"lookahead_ms":3}),
    ("side-chain",    {"link":"kick","depth_db":-8}),
    ("eq-parametric", {"bands":[{"hz":80,"gain_db":-3,"q":1.0},{"hz":3000,"gain_db":+2,"q":0.7}]}),
]
MOTIFS = [
    ("action-cue",  {"tempo_bpm":150,"key":"Em","mood":"driving"}),
    ("stealth-cue", {"tempo_bpm":68,"key":"Am","mood":"tense"}),
    ("victory-fanfare",{"tempo_bpm":120,"key":"C","mood":"triumphant"}),
    ("defeat-cue",  {"tempo_bpm":70,"key":"Bm","mood":"somber"}),
    ("boss-phase1", {"tempo_bpm":138,"key":"Dm","mood":"ominous"}),
    ("boss-phase2", {"tempo_bpm":172,"key":"Dm","mood":"frantic"}),
    ("exploration", {"tempo_bpm":92,"key":"G","mood":"wondrous"}),
    ("town-theme",  {"tempo_bpm":110,"key":"F","mood":"warm"}),
    ("horror-stinger",{"tempo_bpm":40,"key":"atonal","mood":"dread"}),
    ("puzzle-loop", {"tempo_bpm":85,"key":"D","mood":"curious"}),
]
GENRES = ["orchestral","chiptune","synthwave","ambient","metal","hiphop","folk","jazz","techno","lofi"]

def _aid(*p): return "audio_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_audio_dsp():
    out = []
    for name, params in SYNTH_PRESETS:
        out.append({"id":_aid(name,"synth"),"category":"synth","preset":name,"params":params,"tags":[name,"synth"]})
    for name, params in DSP_FX:
        out.append({"id":_aid(name,"fx"),"category":"dsp-fx","fx":name,"params":params,"tags":[name,"dsp","effect"]})
    for (motif, params), genre in itertools.product(MOTIFS, GENRES):
        out.append({"id":_aid(motif,genre,"motif"),"category":"motif","motif":motif,"genre":genre,"params":params,
                    "description":f"{motif} in {genre} style","tags":[motif,genre,"motif","music"]})
    return out

async def seed_audio_dsp(db):
    docs = build_audio_dsp()
    try:
        await db.audio_dsp.create_index("id", unique=True)
        await db.audio_dsp.create_index("category")
        await db.audio_dsp.create_index("genre")
        await db.audio_dsp.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.audio_dsp.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.audio_dsp.count_documents({})}
