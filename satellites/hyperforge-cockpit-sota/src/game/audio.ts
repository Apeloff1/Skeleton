import { clamp } from "./noise";

export class GameAudio {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private music: GainNode | null = null;
  private sfx: GainNode | null = null;
  private windGain: GainNode | null = null;
  private windFilter: BiquadFilterNode | null = null;
  private drone: OscillatorNode[] = [];
  private thermalGain: GainNode | null = null;
  private muted = false;
  private masterVal = 0.72;
  unlocked = false;

  unlock() {
    if (!this.ctx) {
      const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new Ctor({ latencyHint: "interactive" });
      this.buildGraph();
    }
    if (this.ctx.state === "suspended") void this.ctx.resume();
    this.unlocked = true;
  }

  private buildGraph() {
    const ctx = this.ctx!;
    this.master = ctx.createGain();
    this.music = ctx.createGain();
    this.sfx = ctx.createGain();
    this.music.gain.value = 0.22;
    this.sfx.gain.value = 0.9;
    this.music.connect(this.master);
    this.sfx.connect(this.master);
    this.master.connect(ctx.destination);
    this.applyMaster();

    const noise = this.makeNoise(2);
    const src = ctx.createBufferSource();
    src.buffer = noise;
    src.loop = true;
    this.windFilter = ctx.createBiquadFilter();
    this.windFilter.type = "bandpass";
    this.windFilter.frequency.value = 420;
    this.windFilter.Q.value = 0.7;
    this.windGain = ctx.createGain();
    this.windGain.gain.value = 0.0;
    src.connect(this.windFilter);
    this.windFilter.connect(this.windGain);
    this.windGain.connect(this.sfx);
    src.start();

    const freqs = [55, 82.4, 110];
    this.drone = freqs.map((f, i) => {
      const osc = ctx.createOscillator();
      osc.type = i === 2 ? "triangle" : "sine";
      osc.frequency.value = f;
      const g = ctx.createGain();
      g.gain.value = i === 0 ? 0.18 : 0.08;
      osc.connect(g);
      g.connect(this.music!);
      osc.start();
      return osc;
    });

    this.thermalGain = ctx.createGain();
    this.thermalGain.gain.value = 0;
    const th = ctx.createOscillator();
    th.type = "sine";
    th.frequency.value = 196;
    th.connect(this.thermalGain);
    this.thermalGain.connect(this.music);
    th.start();

    document.addEventListener("visibilitychange", () => {
      if (!this.ctx) return;
      if (document.visibilityState === "visible" && this.unlocked) void this.ctx.resume();
    });
  }

  private makeNoise(seconds: number) {
    const ctx = this.ctx!;
    const n = Math.floor(ctx.sampleRate * seconds);
    const buf = ctx.createBuffer(1, n, ctx.sampleRate);
    const data = buf.getChannelData(0);
    let last = 0;
    for (let i = 0; i < n; i++) {
      const white = Math.random() * 2 - 1;
      last = (last + 0.02 * white) / 1.02;
      data[i] = last * 3.5;
    }
    return buf;
  }

  setMuted(v: boolean) {
    this.muted = v;
    this.applyMaster();
  }

  setMaster(v: number) {
    this.masterVal = clamp(v, 0, 1);
    this.applyMaster();
  }

  private applyMaster() {
    if (!this.master || !this.ctx) return;
    const g = this.muted ? 0 : this.masterVal * this.masterVal;
    this.master.gain.setTargetAtTime(g, this.ctx.currentTime, 0.03);
  }

  setWind(speed: number, lift: number) {
    if (!this.ctx || !this.windGain || !this.windFilter) return;
    const t = this.ctx.currentTime;
    const amt = clamp((speed - 12) / 80, 0, 1);
    this.windGain.gain.setTargetAtTime(0.04 + amt * 0.42, t, 0.08);
    this.windFilter.frequency.setTargetAtTime(280 + amt * 1400, t, 0.08);
    if (this.thermalGain) {
      this.thermalGain.gain.setTargetAtTime(lift > 2 ? 0.05 : 0, t, 0.12);
    }
  }

  blip(freq: number, dur = 0.12, gain = 0.2, type: OscillatorType = "sine") {
    if (!this.ctx || !this.sfx) return;
    const t = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g);
    g.connect(this.sfx);
    osc.start(t);
    osc.stop(t + dur + 0.02);
    osc.onended = () => {
      osc.disconnect();
      g.disconnect();
    };
  }

  ring(combo: number) {
    const base = 440 + Math.min(combo, 8) * 48;
    this.blip(base, 0.14, 0.16, "triangle");
    this.blip(base * 2, 0.1, 0.06, "sine");
  }

  crash() {
    if (!this.ctx || !this.sfx) return;
    const t = this.ctx.currentTime;
    const noise = this.makeNoise(0.4);
    const src = this.ctx.createBufferSource();
    src.buffer = noise;
    const f = this.ctx.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.setValueAtTime(800, t);
    f.frequency.exponentialRampToValueAtTime(90, t + 0.35);
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0.55, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.4);
    src.connect(f);
    f.connect(g);
    g.connect(this.sfx);
    src.start(t);
    src.stop(t + 0.42);
    this.blip(70, 0.3, 0.3, "sine");
  }

  finish() {
    this.blip(392, 0.18, 0.18, "triangle");
    setTimeout(() => this.blip(494, 0.18, 0.16, "triangle"), 90);
    setTimeout(() => this.blip(587, 0.28, 0.2, "triangle"), 180);
  }

  ui() {
    this.blip(620, 0.06, 0.08, "square");
  }
}
