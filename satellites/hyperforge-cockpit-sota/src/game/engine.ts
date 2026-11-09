import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { Craft } from "./craft";
import { World } from "./world";
import { Input } from "./input";
import { GameAudio } from "./audio";
import { Vfx } from "./vfx";
import { buildCourses, LAVA_R } from "./courses";
import { useGameStore } from "./store";
import { getSave, recordFinish } from "./save";
import { clamp, medalFor, wrapPi } from "./noise";
import type { Course, CourseId, GhostSample, Phase, RingDef } from "./types";

const FIXED = 1 / 60;
const _camPos = new THREE.Vector3();
const _camLook = new THREE.Vector3();
const _shake = new THREE.Vector3();
const _ghostQ = new THREE.Quaternion();
const _basis = new THREE.Matrix4();
const _right = new THREE.Vector3();
const _up = new THREE.Vector3();
const _fwd = new THREE.Vector3();
const _worldUp = new THREE.Vector3(0, 1, 0);

export class Game {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private composer: EffectComposer | null = null;
  private bloom: UnrealBloomPass | null = null;
  private craft = new Craft();
  private world: World;
  private input = new Input();
  private audio = new GameAudio();
  private vfx: Vfx;
  private courses: Course[];
  private course: Course;
  private rings: RingDef[] = [];
  private ringMeshes: THREE.Mesh[] = [];
  private ringPrev: number[] = [];
  private nextRing = 0;
  private ghostMesh: THREE.Group;
  private ghost: GhostSample[] = [];
  private recording: GhostSample[] = [];
  private phase: Phase = "title";
  private time = 0;
  private acc = 0;
  private clock = 0;
  private last = performance.now();
  private raf = 0;
  private running = true;
  private mobile: boolean;
  private reduced: boolean;
  private hudAcc = 0;
  private combo = 0;
  private comboT = 0;
  private distance = 0;
  private maxSpeed = 0;
  private freeze = 0;
  private titleAngle = 0.6;
  private lastPos = new THREE.Vector3();
  private onResize: () => void;
  private ringMat: THREE.MeshStandardMaterial;
  private ringMatNext: THREE.MeshStandardMaterial;

  constructor(private canvas: HTMLCanvasElement) {
    this.mobile = window.matchMedia("(pointer: coarse)").matches || window.innerWidth < 700;
    this.reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: !this.mobile,
      powerPreference: "high-performance",
      alpha: false,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, this.mobile ? 1.25 : 1.75));
    this.renderer.setSize(canvas.clientWidth || window.innerWidth, canvas.clientHeight || window.innerHeight, false);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;
    this.renderer.shadowMap.enabled = !this.mobile;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.setClearColor(0x0c0b0a, 1);

    this.camera = new THREE.PerspectiveCamera(
      60,
      (canvas.clientWidth || 1) / (canvas.clientHeight || 1),
      0.4,
      1400,
    );
    this.scene.fog = new THREE.FogExp2(0x1a1614, 0.00155);

    this.world = new World(this.mobile);
    this.scene.add(this.world.group);
    this.courses = buildCourses((x, z) => this.world.getHeight(x, z));
    this.course = this.courses[0];

    this.vfx = new Vfx(this.course.thermals, this.mobile);
    this.scene.add(this.vfx.group);
    this.scene.add(this.craft.mesh);

    this.ghostMesh = this.craft.mesh.clone(true);
    this.ghostMesh.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) {
        m.material = new THREE.MeshStandardMaterial({
          color: 0xc9c3b8,
          transparent: true,
          opacity: 0.28,
          roughness: 0.5,
          depthWrite: false,
        });
      }
    });
    this.ghostMesh.visible = false;
    this.scene.add(this.ghostMesh);

    this.ringMat = new THREE.MeshStandardMaterial({
      color: 0x9a948a,
      emissive: 0x3a3834,
      roughness: 0.4,
      metalness: 0.35,
    });
    this.ringMatNext = new THREE.MeshStandardMaterial({
      color: 0xece8e1,
      emissive: 0x8a7a68,
      emissiveIntensity: 1.4,
      roughness: 0.35,
      metalness: 0.4,
    });
    this.buildRingPool();

    if (getSave().settings.bloom && !this.mobile) this.initBloom();

    this.onResize = () => this.resize();
    window.addEventListener("resize", this.onResize);

    this.wireControlsTest();
    window.__caldera = {
      startCourse: (id) => this.startCourse(id),
      getPhase: () => this.phase,
      pauseToggle: () => this.pauseToggle(),
      retry: () => this.retry(),
      toTitle: () => this.toTitle(),
      applySettings: () => this.applySettings(),
    };

    this.lastPos.copy(this.craft.position);
    this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
    this.pushHud(true);

    const params = new URLSearchParams(window.location.search);
    if (params.get("qa") === "1") {
      this.audio.unlock();
      this.startCourse("rim");
    }
  }

  startCourse(id: CourseId) {
    const course = this.courses.find((c) => c.id === id) ?? this.courses[0];
    this.course = course;
    this.rings = course.rings;
    this.nextRing = 0;
    this.time = 0;
    this.combo = 0;
    this.comboT = 0;
    this.distance = 0;
    this.maxSpeed = 0;
    this.recording = [];
    this.ghost = getSave().ghosts[id] ?? [];
    this.ghostMesh.visible = this.ghost.length > 1 && id !== "free";
    this.vfx.resetTrail();
    this.vfx.setThermals(course.thermals);
    this.layoutRings();
    const ground = this.world.getHeight(course.start.x, course.start.z);
    const y = Math.max(course.start.y, ground + 28);
    this.craft.reset(course.start.x, y, course.start.z, course.start.yaw, 44);
    this.lastPos.copy(this.craft.position);
    this.ringPrev = this.rings.map((r) => {
      const dx = this.craft.position.x - r.x;
      const dy = this.craft.position.y - r.y;
      const dz = this.craft.position.z - r.z;
      return dx * r.nx + dy * r.ny + dz * r.nz;
    });
    this.phase = "playing";
    this.audio.unlock();
    this.audio.ui();
    useGameStore.getState().setHud({
      phase: "playing",
      courseId: course.id,
      courseName: course.name,
      ringsTotal: course.rings.length,
      ringsDone: 0,
      time: 0,
      medal: "none",
      hint: course.id === "free" ? "Stay aloft. Thermals glow in the bowl." : "",
    });
  }

  pauseToggle() {
    if (this.phase === "playing") {
      this.phase = "paused";
      useGameStore.getState().setHud({ phase: "paused" });
    } else if (this.phase === "paused") {
      this.phase = "playing";
      useGameStore.getState().setHud({ phase: "playing" });
    }
  }

  toTitle() {
    this.phase = "title";
    this.ghostMesh.visible = false;
    this.vfx.resetTrail();
    useGameStore.getState().setHud({ phase: "title", hint: "" });
  }

  setTouch(roll: number, pitch: number, flare: boolean) {
    this.input.setTouch(roll, pitch, flare);
  }

  private initBloom() {
    const size = new THREE.Vector2();
    this.renderer.getSize(size);
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(size, 0.42, 0.55, 0.84);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
  }

  private buildRingPool() {
    const geo = new THREE.TorusGeometry(1, 0.07, 8, 40);
    for (let i = 0; i < 20; i++) {
      const m = new THREE.Mesh(geo, this.ringMat);
      m.visible = false;
      m.castShadow = true;
      this.scene.add(m);
      this.ringMeshes.push(m);
    }
  }

  private layoutRings() {
    this.ringMeshes.forEach((m, i) => {
      const r = this.rings[i];
      if (!r) {
        m.visible = false;
        return;
      }
      m.visible = true;
      m.position.set(r.x, r.y, r.z);
      m.scale.setScalar(r.radius);
      _fwd.set(r.nx, r.ny, r.nz);
      m.lookAt(r.x + r.nx, r.y + r.ny, r.z + r.nz);
      m.material = i === 0 ? this.ringMatNext : this.ringMat;
    });
  }

  private loop() {
    if (!this.running) return;
    this.raf = requestAnimationFrame(this.loop);
    const now = performance.now();
    let dt = Math.min((now - this.last) / 1000, 0.1);
    this.last = now;
    this.clock += dt;

    if (this.freeze > 0) {
      this.freeze -= dt;
      dt *= 0.15;
    }

    this.acc += dt;
    let steps = 0;
    while (this.acc >= FIXED && steps < 5) {
      this.fixedUpdate(FIXED);
      this.acc -= FIXED;
      steps++;
    }

    this.updateVisuals(dt);
    this.world.update(this.clock);
    const save = getSave();
    const useBloom = save.settings.bloom && this.composer && !this.mobile;
    if (useBloom) this.composer!.render();
    else this.renderer.render(this.scene, this.camera);

    this.hudAcc += dt;
    if (this.hudAcc > 0.08) {
      this.hudAcc = 0;
      this.pushHud(false);
    }
  }

  private fixedUpdate(dt: number) {
    const actions = this.input.sample();
    if (actions.pausePressed && (this.phase === "playing" || this.phase === "paused")) {
      this.pauseToggle();
    }

    if (this.phase !== "playing") return;

    const p = this.craft.position;
    const lift = this.world.liftAt(p.x, p.y, p.z, this.course.thermals);
    this.craft.update(dt, actions, lift);
    this.time += dt;
    this.comboT = Math.max(0, this.comboT - dt);
    if (this.comboT <= 0) this.combo = 0;

    const step = this.craft.position.distanceTo(this.lastPos);
    this.distance += step;
    this.lastPos.copy(this.craft.position);
    this.maxSpeed = Math.max(this.maxSpeed, this.craft.speed);

    this.checkRings();
    this.checkCollision();

    if (this.time * 10 - this.recording.length > 0) {
      this.recording.push({
        t: this.time,
        x: p.x,
        y: p.y,
        z: p.z,
        yaw: this.craft.yaw,
        pitch: this.craft.pitch,
        bank: this.craft.bank,
      });
    }

    this.audio.setWind(this.craft.speed, lift);
  }

  private checkRings() {
    if (this.course.id === "free" || this.rings.length === 0) return;
    const i = this.nextRing;
    const r = this.rings[i];
    if (!r) return;
    const p = this.craft.position;
    const dx = p.x - r.x;
    const dy = p.y - r.y;
    const dz = p.z - r.z;
    const dist = dx * r.nx + dy * r.ny + dz * r.nz;
    const prev = this.ringPrev[i] ?? dist;
    this.ringPrev[i] = dist;
    const radial = Math.hypot(dx - r.nx * dist, dy - r.ny * dist, dz - r.nz * dist);
    if (prev > 0 && dist <= 0 && radial < r.radius + 1.6) {
      this.nextRing++;
      this.combo += 1;
      this.comboT = 3.2;
      this.audio.ring(this.combo);
      this.vfx.emitBurst(p, 0xf4eee4, 22);
      if (getSave().settings.shake && !this.reduced) this.vfx.addTrauma(0.18);
      if (this.ringMeshes[i]) this.ringMeshes[i].visible = false;
      const nxt = this.ringMeshes[this.nextRing];
      if (nxt) nxt.material = this.ringMatNext;
      if (this.nextRing >= this.rings.length) this.finish();
    }
  }

  private checkCollision() {
    const p = this.craft.position;
    const ground = this.world.getHeight(p.x, p.z);
    const agl = p.y - ground;
    const lava = Math.hypot(p.x, p.z) < LAVA_R + 3 && p.y < 2;
    if (agl < 1.4 || lava || p.y < -18) {
      this.crash();
    }
  }

  private crash() {
    if (this.phase !== "playing") return;
    this.phase = "crash";
    this.craft.alive = false;
    this.audio.crash();
    this.vfx.emitBurst(this.craft.position, 0xc45c38, 50);
    if (getSave().settings.shake && !this.reduced) this.vfx.addTrauma(0.72);
    this.freeze = 0.09;
    useGameStore.getState().setHud({ phase: "crash" });
  }

  retry() {
    this.startCourse(this.course.id);
  }

  private finish() {
    this.phase = "finish";
    const medal = this.course.par > 0 ? medalFor(this.time, this.course.par) : "none";
    const { save } = recordFinish(this.course.id, this.time, medal, this.recording, this.distance);
    useGameStore.getState().setMeta({
      best: save.best,
      medals: save.medals,
      unlocked: save.unlocked,
      totalDistance: save.totalDistance,
    });
    this.audio.finish();
    this.vfx.emitBurst(this.craft.position, 0xece8e1, 60);
    useGameStore.getState().setHud({
      phase: "finish",
      lastTime: this.time,
      bestTime: save.best[this.course.id] ?? this.time,
      medal,
    });
  }

  private updateVisuals(dt: number) {
    this.craft.syncMesh(dt);
    this.vfx.update(dt, this.craft.position, this.craft.speed, this.phase === "playing");
    this.updateGhost();

    if (this.phase === "title") {
      this.titleAngle += dt * 0.07;
      const r = 268;
      this.camera.position.set(
        Math.sin(this.titleAngle) * r,
        92,
        Math.cos(this.titleAngle) * r,
      );
      this.camera.lookAt(0, 8, 0);
      this.camera.fov += (52 - this.camera.fov) * (1 - Math.exp(-3 * dt));
      this.camera.updateProjectionMatrix();
      return;
    }

    const follow = 11 + this.craft.speed * 0.07;
    const height = 3.4 + this.craft.speed * 0.018;
    _camPos
      .copy(this.craft.position)
      .addScaledVector(this.craft.forward, -follow)
      .addScaledVector(this.craft.up, height * 0.35)
      .addScaledVector(_worldUp, height);
    _camPos.addScaledVector(this.craft.right, this.craft.bank * 2.4);

    if (getSave().settings.shake && !this.reduced) {
      this.vfx.shakeOffset(_shake, this.reduced);
      _camPos.add(_shake);
    }

    this.camera.position.lerp(_camPos, 1 - Math.exp(-5.5 * dt));
    this.craft.lookPoint(_camLook, 16);
    this.camera.lookAt(_camLook);

    const targetFov = 56 + clamp(this.craft.speed - 30, 0, 50) * 0.22;
    this.camera.fov += (targetFov - this.camera.fov) * (1 - Math.exp(-3 * dt));
    this.camera.updateProjectionMatrix();
  }

  private updateGhost() {
    if (!this.ghostMesh.visible || this.ghost.length < 2) return;
    const t = this.time;
    let i = 0;
    while (i < this.ghost.length - 2 && this.ghost[i + 1].t < t) i++;
    const a = this.ghost[i];
    const b = this.ghost[i + 1];
    const u = clamp((t - a.t) / Math.max(0.001, b.t - a.t), 0, 1);
    this.ghostMesh.position.set(
      a.x + (b.x - a.x) * u,
      a.y + (b.y - a.y) * u,
      a.z + (b.z - a.z) * u,
    );
    const yaw = a.yaw + wrapPi(b.yaw - a.yaw) * u;
    const pitch = a.pitch + (b.pitch - a.pitch) * u;
    const bank = a.bank + (b.bank - a.bank) * u;
    const cy = Math.cos(yaw);
    const sy = Math.sin(yaw);
    const cp = Math.cos(pitch);
    const sp = Math.sin(pitch);
    _fwd.set(-sy * cp, sp, -cy * cp);
    _right.crossVectors(_fwd, _up.set(0, 1, 0)).normalize();
    _right.applyAxisAngle(_fwd, bank);
    _up.crossVectors(_right, _fwd).normalize();
    _basis.makeBasis(_right, _up, _fwd);
    _ghostQ.setFromRotationMatrix(_basis);
    this.ghostMesh.quaternion.copy(_ghostQ);
  }

  private pushHud(_force: boolean) {
    const p = this.craft.position;
    const ground = this.world.getHeight(p.x, p.z);
    const agl = p.y - ground;
    const lift = this.world.liftAt(p.x, p.y, p.z, this.course.thermals);
    useGameStore.getState().setHud({
      phase: this.phase,
      time: this.time,
      speed: this.craft.speed,
      altitude: p.y,
      agl,
      lift,
      inThermal: lift > 3,
      ringsDone: this.nextRing,
      ringsTotal: this.rings.length,
      combo: this.comboT > 0 ? this.combo : 0,
      nearTerrain: agl < 10 && this.phase === "playing",
      distance: this.distance,
      maxSpeed: this.maxSpeed,
      bestTime: getSave().best[this.course.id] ?? 0,
      hint:
        this.phase === "playing" && this.course.id !== "free" && this.time < 4
          ? "W pull up · S dive · A/D bank · Space flare"
          : useGameStore.getState().hint,
    });
  }

  private wireControlsTest() {
    window.__controlsTest = {
      getYaw: () => this.craft.yaw,
      getSpeed: () => this.craft.speed,
      getRoll: () => this.craft.bank,
      setSteer: (v) => this.input.setSteer(v),
      setKeys: (codes) => this.input.setKeys(codes),
    };
  }

  resize() {
    const w = this.canvas.clientWidth || window.innerWidth;
    const h = this.canvas.clientHeight || window.innerHeight;
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
    this.composer?.setSize(w, h);
    this.bloom?.resolution.set(w, h);
  }

  applySettings() {
    const s = getSave().settings;
    this.audio.setMuted(s.muted);
    this.audio.setMaster(s.master);
    if (s.bloom && !this.mobile && !this.composer) this.initBloom();
  }

  dispose() {
    this.running = false;
    cancelAnimationFrame(this.raf);
    window.removeEventListener("resize", this.onResize);
    this.input.dispose();
    this.world.dispose();
    this.vfx.dispose();
    this.renderer.dispose();
    this.composer?.dispose();
    delete window.__controlsTest;
    delete window.__caldera;
  }
}

export function createGame(canvas: HTMLCanvasElement) {
  const game = new Game(canvas);
  return game;
}
