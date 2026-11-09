import * as THREE from "three";
import type { Actions } from "./types";
import { clamp } from "./noise";

const MAX_BANK = 0.98;
const ROLL_RESP = 10.5;
const PITCH_RATE = 1.05;
const TURN_AUTH = 1.9;
const GRAVITY = 22;
const DRAG = 0.0036;
const CRUISE = 8.2;
const MIN_SPEED = 12;
const MAX_SPEED = 102;

const _q = new THREE.Quaternion();
const _basis = new THREE.Matrix4();
const _worldUp = new THREE.Vector3(0, 1, 0);

export class Craft {
  position = new THREE.Vector3(200, 70, 0);
  yaw = 0;
  pitch = 0.06;
  bank = 0;
  speed = 38;
  alive = true;
  forward = new THREE.Vector3(0, 0, -1);
  right = new THREE.Vector3(1, 0, 0);
  up = new THREE.Vector3(0, 1, 0);
  mesh: THREE.Group;

  constructor() {
    this.mesh = buildGlider();
    this.rebuildBasis();
  }

  reset(x: number, y: number, z: number, yaw: number, speed = 38) {
    this.position.set(x, y, z);
    this.yaw = yaw;
    this.pitch = 0.08;
    this.bank = 0;
    this.speed = speed;
    this.alive = true;
    this.rebuildBasis();
    this.syncMesh(0);
  }

  update(dt: number, input: Actions, thermalLift: number) {
    if (!this.alive) return;

    const rollTarget = input.roll * MAX_BANK;
    this.bank += (rollTarget - this.bank) * (1 - Math.exp(-ROLL_RESP * dt));

    this.pitch += input.pitch * PITCH_RATE * dt;
    this.pitch = clamp(this.pitch, -0.72, 0.82);
    if (Math.abs(input.pitch) < 0.08) {
      this.pitch += (0.07 - this.pitch) * 0.35 * dt;
    }

    const speedFactor = clamp(this.speed / 42, 0.32, 1.85);
    this.yaw += Math.sin(this.bank) * TURN_AUTH * speedFactor * dt;

    const gravityComp = -Math.sin(this.pitch) * GRAVITY;
    const drag = DRAG * this.speed * this.speed;
    const flare = input.flare * (8 + this.speed * 0.35);
    this.speed += (CRUISE + gravityComp - drag - flare) * dt;
    this.speed += thermalLift * 0.38 * dt;
    this.speed = clamp(this.speed, MIN_SPEED, MAX_SPEED);

    if (this.speed < 16 && this.pitch > 0.18) {
      this.pitch -= 0.85 * dt;
    }

    this.rebuildBasis();
    this.position.addScaledVector(this.forward, this.speed * dt);
    if (thermalLift > 0) {
      this.position.y += thermalLift * 0.62 * dt;
    }
  }

  rebuildBasis() {
    const cy = Math.cos(this.yaw);
    const sy = Math.sin(this.yaw);
    const cp = Math.cos(this.pitch);
    const sp = Math.sin(this.pitch);
    this.forward.set(-sy * cp, sp, -cy * cp).normalize();
    this.right.set(cy, 0, -sy);
    this.right.crossVectors(this.forward, _worldUp).normalize();
    if (this.right.lengthSq() < 1e-6) this.right.set(1, 0, 0);
    this.right.applyAxisAngle(this.forward, this.bank);
    this.up.crossVectors(this.right, this.forward).normalize();
  }

  syncMesh(dt: number) {
    this.mesh.position.copy(this.position);
    _basis.makeBasis(this.right, this.up, this.forward);
    _q.setFromRotationMatrix(_basis);
    this.mesh.quaternion.slerp(_q, 1 - Math.exp(-18 * Math.max(dt, 0.001)));
    const stretch = 1 + clamp((this.speed - 30) / 140, 0, 0.12);
    this.mesh.scale.set(1 / Math.sqrt(stretch), 1 / Math.sqrt(stretch), stretch);
  }

  lookPoint(out: THREE.Vector3, dist = 14) {
    return out.copy(this.position).addScaledVector(this.forward, dist);
  }
}

function buildGlider() {
  const g = new THREE.Group();
  const sail = new THREE.MeshStandardMaterial({
    color: 0xd9d2c5,
    roughness: 0.62,
    metalness: 0.04,
    side: THREE.DoubleSide,
    flatShading: true,
  });
  const rim = new THREE.MeshStandardMaterial({
    color: 0x1a1816,
    roughness: 0.45,
    metalness: 0.2,
  });
  const bodyMat = new THREE.MeshStandardMaterial({
    color: 0x2a2622,
    roughness: 0.7,
    metalness: 0.08,
  });

  const wingShape = new THREE.Shape();
  wingShape.moveTo(0, 1.85);
  wingShape.lineTo(-2.55, -1.35);
  wingShape.lineTo(0, -0.55);
  wingShape.lineTo(2.55, -1.35);
  wingShape.closePath();
  const wingGeo = new THREE.ExtrudeGeometry(wingShape, {
    depth: 0.07,
    bevelEnabled: false,
  });
  wingGeo.rotateX(-Math.PI / 2);
  wingGeo.rotateY(Math.PI);
  wingGeo.translate(0, 0.12, 0);
  const wing = new THREE.Mesh(wingGeo, sail);
  wing.castShadow = true;
  g.add(wing);

  const mastGeo = new THREE.CylinderGeometry(0.035, 0.035, 0.85, 5);
  const mast = new THREE.Mesh(mastGeo, rim);
  mast.position.set(0, 0.5, -0.15);
  g.add(mast);

  const barGeo = new THREE.CylinderGeometry(0.03, 0.03, 1.15, 5);
  barGeo.rotateZ(Math.PI / 2);
  const bar = new THREE.Mesh(barGeo, rim);
  bar.position.set(0, -0.22, 0.15);
  g.add(bar);

  const keelGeo = new THREE.BoxGeometry(0.06, 0.05, 2.4);
  const keel = new THREE.Mesh(keelGeo, rim);
  keel.position.set(0, 0.08, 0.05);
  g.add(keel);

  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.16, 0.42, 4, 8), bodyMat);
  torso.rotation.x = Math.PI / 2.4;
  torso.position.set(0, -0.38, 0.35);
  g.add(torso);

  const helm = new THREE.Mesh(new THREE.SphereGeometry(0.13, 8, 6), bodyMat);
  helm.position.set(0, -0.28, 0.72);
  g.add(helm);

  g.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh) m.castShadow = true;
  });

  return g;
}
