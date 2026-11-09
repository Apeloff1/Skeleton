#!/usr/bin/env node
"use strict";
/* Execute the REAL generated HTML5 game script in a constrained fake DOM.
 * This tests JavaScript gameplay and issued Canvas2D draw calls, not actual
 * Chromium pixels or arbitrary third-party JavaScript safety.
 * Execute only via the operator-approved Python qualification facade.
 */
const fs = require("node:fs");
const vm = require("node:vm");
const crypto = require("node:crypto");

function fail(message) {
  process.stdout.write(JSON.stringify({
    schema: "skeleton.game_builder.js_playthrough_probe.v1",
    executed: false, result: "failed", reason: String(message).slice(0, 160),
  }) + "\n");
  process.exitCode = 2;
}
function sha(content) {
  return crypto.createHash("sha256").update(content).digest("hex");
}
function main() {
  if (process.argv.length !== 4) throw new Error("exact two source inputs required");
  const html = fs.readFileSync(process.argv[2], "utf8");
  const proof = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
  if (Buffer.byteLength(html) > 2000000 || html.length < 1000) {
    throw new Error("browser game outside bounded source size");
  }
  if (proof.schema !== "skeleton.game_builder.solution_trace.v1") {
    throw new Error("canonical solved Python replay required");
  }
  const actions = proof.actions;
  if (!Array.isArray(actions) || actions.length < 1 || actions.length > 20000 ||
      !actions.every(x => ["up", "down", "left", "right"].includes(x))) {
    throw new Error("bounded typed controller replay required");
  }
  const matches = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  if (matches.length !== 1) throw new Error("exactly one generated inline script required");
  const script = matches[0][1];
  let rects = 0;
  let shapes = 0;
  let overlayDraws = 0;
  let audioStarts = 0;
  let timers = [];
  let gamepadFrame = null;
  const gamepad = {
    connected: true,
    axes: [0, 0],
    buttons: Array.from({length: 16}, () => ({pressed: false})),
  };
  const ctx = {
    fillRect() { rects++; },
    drawImage() { rects++; overlayDraws++; },
    strokeRect() { rects++; },
    beginPath() { shapes++; },
    moveTo() {}, lineTo() {}, closePath() {}, arc() {},
    fill() { shapes++; },
  };
  const listeners = Object.create(null);
  const node = (action) => ({
    textContent: "", disabled: false, dataset: action ? {action} : {},
    handlers: Object.create(null),
    setAttribute() {},
    addEventListener(type, fn) { this.handlers[type] = fn; },
    getContext() { return ctx; },
  });
  const buttons = ["up", "left", "right", "down"].map(direction => node(direction));
  const nodes = Object.create(null);
  const document = {
    hidden: false, body: {appendChild() {}},
    getElementById(id) { return nodes[id] ||= node(); },
    querySelectorAll() { return buttons; },
    addEventListener(type, fn) { listeners[type] = fn; },
    createElement() { return node(); },
  };
  class MockAudio {
    constructor(src) {
      if (!src.startsWith("data:audio/wav;base64,"))
        throw new Error("audio attempted non-original or remote media");
      this.paused = true; this.volume = 1; this.currentTime = 0;
    }
    play() { audioStarts++; this.paused=false; return Promise.resolve(); }
  }
  class MockImage {
    constructor() {
      this.complete=false; this.naturalWidth=0; this.onload=null;
    }
    set src(src) {
      if (!src.startsWith("data:image/png;base64,"))
        throw new Error("parallax attempted non-original or remote images");
      this.complete=true;this.naturalWidth=88;
      if(this.onload)this.onload();
    }
  }
  const sandbox = {
    document, Audio: MockAudio, Image: MockImage,
    navigator: {getGamepads() {return [gamepad];}},
    requestAnimationFrame(fn) {gamepadFrame=fn;},
    window: {setInterval(fn, period) {
      if (typeof fn !== "function" || !(period >= 40 && period <= 1000))
        throw new Error("unsafe animation interval");
      timers.push(fn);
    }},
    URL: {createObjectURL() { throw new Error("download not part of replay"); }},
    Blob: class {constructor() {throw new Error("download not part of replay");}},
    setTimeout() {throw new Error("unexpected browser async task");},
  };
  vm.createContext(sandbox, {name: "original-gameplay-probe"});
  vm.runInContext(script, sandbox, {timeout: 2500, displayErrors: false});
  const initial = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (initial.status !== "playing" || initial.steps !== 0) {
    throw new Error("game failed actual startup");
  }
  for (const action of actions) {
    vm.runInContext("takeTurn(" + JSON.stringify(action) + ")", sandbox,
                    {timeout: 200, displayErrors: false});
  }
  const final = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  const expected = proof.final_state;
  if (!expected || final.status !== "won" ||
      final.status !== expected.status ||
      final.level !== expected.level_index ||
      final.x !== expected.x || final.y !== expected.y ||
      final.steps !== expected.steps ||
      final.health !== expected.health || final.score !== expected.score) {
    throw new Error("actual JS gameplay diverged from proven Python end state");
  }
  const recorded = JSON.parse(vm.runInContext("JSON.stringify(replay)", sandbox, {timeout: 100}));
  if (JSON.stringify(recorded) !== JSON.stringify(actions)) {
    throw new Error("JS controller actions diverged from original replay");
  }
  // Exercise actual DOM listeners and user controls, not just the core
  // takeTurn() function. These are synthetic DOM events, not real hardware.
  const keycodes = {up: "ArrowUp", left: "ArrowLeft",
                    right: "ArrowRight", down: "ArrowDown"};
  const keydown = code => {
    if (typeof listeners.keydown !== "function")
      throw new Error("keyboard event listener is missing");
    listeners.keydown({
      code, target: {tagName: "BODY"}, repeat: false,
      altKey: false, ctrlKey: false, metaKey: false, preventDefault() {},
    });
  };
  keydown("KeyZ");
  const undone = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (undone.status !== "playing" || undone.steps !== final.steps - 1)
    throw new Error("actual game undo listener failed to reverse winning move");
  keydown(keycodes[actions[actions.length - 1]]);
  const restored = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (JSON.stringify(restored) !== JSON.stringify(final))
    throw new Error("keyboard controller failed to replay final winning move");
  keydown("KeyR");
  const restarted = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (restarted.status !== "playing" || restarted.steps !== 0 ||
      restarted.level !== 0 || restarted.score !== 0)
    throw new Error("restart/reset hotkey did not clear game session");
  const first = buttons.find(x => x.dataset.action === actions[0]);
  if (!first || typeof first.handlers.click !== "function")
    throw new Error("onscreen controller action was not bound");
  first.handlers.click();
  const fromButton = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (fromButton.steps !== 1 ||
      vm.runInContext("replay[0]", sandbox, {timeout: 100}) !== actions[0])
    throw new Error("actual onscreen directional button failed controller step");
  // The browser game's REAL Gamepad API handler consumes standard buttons.
  // Holding a D-pad button must not flood the 20k-turn replay.
  keydown("KeyR");
  const keyIndex = {up: 12, down: 13, left: 14, right: 15};
  if (typeof gamepadFrame !== "function")
    throw new Error("standard game controller scan was never registered");
  gamepad.buttons[keyIndex[actions[0]]].pressed=true;
  gamepadFrame();
  const padFirst = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (padFirst.steps !== 1)
    throw new Error("gamepad directional input did not reach actual game transition");
  gamepadFrame();
  const padHeld = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (padHeld.steps !== 1)
    throw new Error("held gamepad button incorrectly repeated actions");
  gamepad.buttons[keyIndex[actions[0]]].pressed=false;
  gamepadFrame();
  gamepad.buttons[1].pressed=true;gamepadFrame();
  const padUndo = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if (padUndo.steps !== 0)throw new Error("gamepad B undo did not restore initial state");
  gamepad.buttons[1].pressed=false;gamepadFrame();
  gamepad.buttons[9].pressed=true;gamepadFrame();
  const padRestart = JSON.parse(vm.runInContext("JSON.stringify(state)", sandbox, {timeout: 100}));
  if(padRestart.status!=="playing"||padRestart.steps!==0)
    throw new Error("gamepad Start restart did not restore playable game");
  gamepad.buttons[9].pressed=false;gamepadFrame();
  const studioArt = vm.runInContext("Boolean(STUDIO_ART)", sandbox, {timeout: 100});
  const studioMedia = vm.runInContext("Boolean(STUDIO_MEDIA)", sandbox, {timeout: 100});
  const expectedAudio = vm.runInContext(
    "Boolean(STUDIO_MEDIA && STUDIO_MEDIA.audio.ambient)", sandbox, {timeout: 100});
  const expectedLayers = vm.runInContext(
    "(STUDIO_MEDIA && STUDIO_MEDIA.parallax.length)||0", sandbox, {timeout: 100});
  if (expectedAudio && audioStarts < 1)
    throw new Error("original soundtrack did not start on actual gameplay input");
  if (expectedLayers && overlayDraws < expectedLayers)
    throw new Error("original environmental graphics were not composited onto game canvas");
  const before = rects;
  for (const advance of timers) advance();
  if (studioArt && (timers.length !== 1 || rects <= before || rects < 64 * actions.length)) {
    throw new Error("actual original sprite canvas draw/animation not exercised");
  }
  if (!rects) throw new Error("generated canvas engine drew no pixels");
  process.stdout.write(JSON.stringify({
    schema: "skeleton.game_builder.js_playthrough_probe.v1",
    executed: true, result: "won",
    source_sha256: sha(html),
    proof_sha256: sha(fs.readFileSync(process.argv[3])),
    source_world_digest: proof.world_digest,
    action_count: actions.length,
    state: {level: final.level, x: final.x, y: final.y,
            health: final.health, score: final.score,
            steps: final.steps, status: final.status},
    canvas_draw_calls: rects,
    canvas_shape_calls: shapes,
    original_sprites_drawn: !!studioArt,
    original_soundtrack_playback_method_called: expectedAudio && audioStarts>0,
    original_overlay_draw_calls: overlayDraws,
    original_environment_layers: expectedLayers,
    original_media_present: studioMedia,
    audio_hardware_verified: false,
    original_animation_tick_exercised: !!studioArt && timers.length === 1,
    keyboard_input_verified: true,
    onscreen_button_input_verified: true,
    undo_replay_verified: true,
    restart_verified: true,
    gamepad_input_verified: true,
    gamepad_held_input_debounced: true,
    graphical_browser_pixel_output_verified: false,
    native_godot_executed: false,
    actual_js_gameplay_executed: true,
  }) + "\n");
}
try { main(); } catch (error) { fail(error.message || String(error)); }
