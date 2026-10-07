import * as THREE from "three";
import type { Thermal } from "./types";
import { clamp } from "./noise";

export class Vfx {
  readonly group = new THREE.Group();
  trauma = 0;
  private ash: THREE.Points;
  private ashVel: Float32Array;
  private trail: THREE.Line;
  private trailPos: Float32Array;
  private trailIdx = 0;
  private trailFilled = 0;
  private bursts: THREE.Points;
  private burstLife: Float32Array;
  private burstVel: Float32Array;
  private thermalPts: THREE.Points;
  private thermalPos: Float32Array;
  private thermalBase: Float32Array;
  private thermalCount: number;
  private streak: THREE.Points;
  private streakPos: Float32Array;
  private time = 0;
  private disposables: THREE.BufferGeometry[] = [];
  private materials: THREE.Material[] = [];

  constructor(thermals: Thermal[], mobile: boolean) {
    const ashN = mobile ? 420 : 900;
    this.ash = this.makeAsh(ashN);
    this.ashVel = new Float32Array(ashN * 3);
    const ap = this.ash.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < ashN; i++) {
      this.ashVel[i * 3 + 1] = 2 + Math.random() * 6;
      this.ashVel[i * 3] = (Math.random() - 0.5) * 4;
      this.ashVel[i * 3 + 2] = (Math.random() - 0.5) * 4;
      void ap;
    }

    const trailN = 48;
    this.trailPos = new Float32Array(trailN * 3);
    const tgeo = new THREE.BufferGeometry();
    tgeo.setAttribute("position", new THREE.BufferAttribute(this.trailPos, 3));
    this.disposables.push(tgeo);
    const tmat = new THREE.LineBasicMaterial({
      color: 0xe8dcc8,
      transparent: true,
      opacity: 0.35,
    });
    this.materials.push(tmat);
    this.trail = new THREE.Line(tgeo, tmat);
    this.trail.frustumCulled = false;
    this.group.add(this.trail);

    this.bursts = this.makeBursts(mobile ? 80 : 140);
    this.burstLife = new Float32Array(this.bursts.geometry.attributes.position.count);
    this.burstVel = new Float32Array(this.burstLife.length * 3);

    const tCount = Math.max(1, thermals.length) * (mobile ? 40 : 70);
    this.thermalCount = tCount;
    this.thermalPts = this.makeThermals(thermals, tCount);
    this.thermalPos = this.thermalPts.geometry.attributes.position.array as Float32Array;
    this.thermalBase = this.thermalPos.slice();

    this.streak = this.makeStreaks(mobile ? 24 : 40);
    this.streakPos = this.streak.geometry.attributes.position.array as Float32Array;
  }

  addTrauma(v: number) {
    this.trauma = clamp(this.trauma + v, 0, 1);
  }

  shakeOffset(out: THREE.Vector3, reduced: boolean) {
    if (reduced || this.trauma <= 0.001) {
      out.set(0, 0, 0);
      return out;
    }
    const s = this.trauma * this.trauma;
    const t = this.time * 28;
    out.set(Math.sin(t * 1.7) * s * 0.55, Math.cos(t * 1.3) * s * 0.4, Math.sin(t * 2.1) * s * 0.35);
    return out;
  }

  emitBurst(origin: THREE.Vector3, color = 0xf0e6d6, n = 28) {
    const pos = this.bursts.geometry.attributes.position as THREE.BufferAttribute;
    const col = this.bursts.geometry.attributes.color as THREE.BufferAttribute;
    const c = new THREE.Color(color);
    let spawned = 0;
    for (let i = 0; i < this.burstLife.length && spawned < n; i++) {
      if (this.burstLife[i] > 0.02) continue;
      this.burstLife[i] = 1;
      pos.setXYZ(i, origin.x, origin.y, origin.z);
      this.burstVel[i * 3] = (Math.random() - 0.5) * 18;
      this.burstVel[i * 3 + 1] = Math.random() * 14;
      this.burstVel[i * 3 + 2] = (Math.random() - 0.5) * 18;
      col.setXYZ(i, c.r, c.g, c.b);
      spawned++;
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
  }

  pushTrail(p: THREE.Vector3) {
    const n = this.trailPos.length / 3;
    const i = this.trailIdx % n;
    this.trailPos[i * 3] = p.x;
    this.trailPos[i * 3 + 1] = p.y;
    this.trailPos[i * 3 + 2] = p.z;
    this.trailIdx++;
    this.trailFilled = Math.min(this.trailFilled + 1, n);
    const geo = this.trail.geometry;
    const ordered = new Float32Array(this.trailFilled * 3);
    for (let k = 0; k < this.trailFilled; k++) {
      const src = (this.trailIdx - this.trailFilled + k + n * 8) % n;
      ordered[k * 3] = this.trailPos[src * 3];
      ordered[k * 3 + 1] = this.trailPos[src * 3 + 1];
      ordered[k * 3 + 2] = this.trailPos[src * 3 + 2];
    }
    geo.setAttribute("position", new THREE.BufferAttribute(ordered, 3));
    geo.computeBoundingSphere();
  }

  resetTrail() {
    this.trailIdx = 0;
    this.trailFilled = 0;
    this.trail.geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3), 3));
  }

  update(dt: number, craftPos: THREE.Vector3, speed: number, playing: boolean) {
    this.time += dt;
    this.trauma = Math.max(0, this.trauma - dt * 1.6);

    const ashPos = this.ash.geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < ashPos.count; i++) {
      let x = ashPos.getX(i) + this.ashVel[i * 3] * dt;
      let y = ashPos.getY(i) + this.ashVel[i * 3 + 1] * dt;
      let z = ashPos.getZ(i) + this.ashVel[i * 3 + 2] * dt;
      if (y > 130) {
        y = -8;
        x = (Math.random() - 0.5) * 420;
        z = (Math.random() - 0.5) * 420;
      }
      ashPos.setXYZ(i, x, y, z);
    }
    ashPos.needsUpdate = true;

    const bPos = this.bursts.geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < this.burstLife.length; i++) {
      if (this.burstLife[i] <= 0) continue;
      this.burstLife[i] -= dt * 1.8;
      bPos.setXYZ(
        i,
        bPos.getX(i) + this.burstVel[i * 3] * dt,
        bPos.getY(i) + this.burstVel[i * 3 + 1] * dt,
        bPos.getZ(i) + this.burstVel[i * 3 + 2] * dt,
      );
      this.burstVel[i * 3 + 1] -= 12 * dt;
    }
    bPos.needsUpdate = true;

    for (let i = 0; i < this.thermalCount; i++) {
      const y = this.thermalBase[i * 3 + 1] + ((this.time * (8 + (i % 7))) % 70);
      this.thermalPos[i * 3] = this.thermalBase[i * 3] + Math.sin(this.time + i) * 1.2;
      this.thermalPos[i * 3 + 1] = y;
      this.thermalPos[i * 3 + 2] = this.thermalBase[i * 3 + 2] + Math.cos(this.time * 0.8 + i) * 1.2;
    }
    this.thermalPts.geometry.attributes.position.needsUpdate = true;

    if (playing && speed > 48) {
      const sPos = this.streak.geometry.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < sPos.count; i++) {
        let z = sPos.getZ(i) + dt * (20 + speed * 0.4);
        if (z > 8) {
          sPos.setXYZ(i, (Math.random() - 0.5) * 10, (Math.random() - 0.5) * 6, -18 - Math.random() * 10);
        } else {
          sPos.setZ(i, z);
        }
      }
      sPos.needsUpdate = true;
      this.streak.position.copy(craftPos);
      this.streak.visible = true;
    } else {
      this.streak.visible = false;
    }

    if (playing) this.pushTrail(craftPos);
  }

  setThermals(thermals: Thermal[]) {
    const g = this.thermalPts.geometry;
    const pos = g.attributes.position as THREE.BufferAttribute;
    const n = pos.count;
    for (let i = 0; i < n; i++) {
      const t = thermals[i % Math.max(thermals.length, 1)] ?? { x: 0, z: 0, radius: 20, strength: 10, ceil: 120 };
      const a = Math.random() * Math.PI * 2;
      const r = Math.random() * t.radius * 0.85;
      this.thermalBase[i * 3] = t.x + Math.cos(a) * r;
      this.thermalBase[i * 3 + 1] = Math.random() * 40;
      this.thermalBase[i * 3 + 2] = t.z + Math.sin(a) * r;
    }
    this.thermalPts.visible = thermals.length > 0;
  }

  private makeAsh(n: number) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 420;
      pos[i * 3 + 1] = Math.random() * 140 - 10;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 420;
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.disposables.push(geo);
    const mat = new THREE.PointsMaterial({
      color: 0xbbaea0,
      size: 0.55,
      transparent: true,
      opacity: 0.45,
      depthWrite: false,
    });
    this.materials.push(mat);
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    this.group.add(pts);
    return pts;
  }

  private makeBursts(n: number) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    this.disposables.push(geo);
    const mat = new THREE.PointsMaterial({
      size: 0.7,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      depthWrite: false,
    });
    this.materials.push(mat);
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    this.group.add(pts);
    return pts;
  }

  private makeThermals(thermals: Thermal[], n: number) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const t = thermals[i % Math.max(thermals.length, 1)] ?? { x: 0, z: 0, radius: 24, strength: 12, ceil: 120 };
      const a = Math.random() * Math.PI * 2;
      const r = Math.random() * t.radius;
      pos[i * 3] = t.x + Math.cos(a) * r;
      pos[i * 3 + 1] = Math.random() * 50;
      pos[i * 3 + 2] = t.z + Math.sin(a) * r;
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.disposables.push(geo);
    const mat = new THREE.PointsMaterial({
      color: 0xc45c38,
      size: 0.85,
      transparent: true,
      opacity: 0.35,
      depthWrite: false,
    });
    this.materials.push(mat);
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    this.group.add(pts);
    return pts;
  }

  private makeStreaks(n: number) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 10;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 6;
      pos[i * 3 + 2] = -8 - Math.random() * 16;
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.disposables.push(geo);
    const mat = new THREE.PointsMaterial({
      color: 0xf2ebe0,
      size: 0.12,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
    });
    this.materials.push(mat);
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    pts.visible = false;
    this.group.add(pts);
    return pts;
  }

  dispose() {
    this.disposables.forEach((g) => g.dispose());
    this.materials.forEach((m) => m.dispose());
  }
}
