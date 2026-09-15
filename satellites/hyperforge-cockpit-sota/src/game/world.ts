import * as THREE from "three";
import { fbm, mulberry32, smoothstep, clamp } from "./noise";
import { LAVA_R, RIM_R, WORLD_SIZE } from "./courses";
import type { Thermal } from "./types";

export const HALF = WORLD_SIZE / 2;

export function terrainHeight(x: number, z: number) {
  const r = Math.hypot(x, z);
  if (r < LAVA_R - 2) return -16;
  const fromLava = smoothstep(LAVA_R - 2, LAVA_R + 16, r);
  const bowl = -10 + fromLava * 10;
  const rim =
    Math.exp(-((r - RIM_R) ** 2) / (2 * 40 * 40)) * 64 +
    Math.exp(-((r - (RIM_R + 18)) ** 2) / (2 * 22 * 22)) * 18;
  const outer = smoothstep(RIM_R + 40, 360, r) * 10;
  const drop = r > 270 ? (r - 270) * 0.05 : 0;
  const nMask = smoothstep(LAVA_R + 6, LAVA_R + 26, r);
  const n =
    fbm(x * 0.016, z * 0.016, 5, 1) * 11 + fbm(x * 0.045, z * 0.045, 3, 7) * 3.4;
  const ang = Math.atan2(z, x);
  const ridges =
    Math.sin(ang * 7.0 + fbm(x * 0.01, z * 0.01, 2, 3) * 1.4) *
    5.5 *
    smoothstep(90, 175, r) *
    (1 - smoothstep(230, 290, r));
  const vent =
    Math.exp(-((x - 86) ** 2 + (z + 40) ** 2) / (2 * 28 * 28)) * 22 +
    Math.exp(-((x + 120) ** 2 + (z - 70) ** 2) / (2 * 24 * 24)) * 16;
  return bowl + rim + outer - drop + n * nMask + ridges + vent * nMask;
}

export class HeightField {
  readonly data: Float32Array;
  constructor(
    readonly size: number,
    readonly res: number,
  ) {
    this.data = new Float32Array(res * res);
    const half = size / 2;
    for (let z = 0; z < res; z++) {
      for (let x = 0; x < res; x++) {
        const wx = (x / (res - 1)) * size - half;
        const wz = (z / (res - 1)) * size - half;
        this.data[z * res + x] = terrainHeight(wx, wz);
      }
    }
  }

  sample(x: number, z: number) {
    const half = this.size / 2;
    const u = ((x + half) / this.size) * (this.res - 1);
    const v = ((z + half) / this.size) * (this.res - 1);
    const x0 = Math.max(0, Math.min(this.res - 2, Math.floor(u)));
    const z0 = Math.max(0, Math.min(this.res - 2, Math.floor(v)));
    const tx = clamp(u - x0, 0, 1);
    const tz = clamp(v - z0, 0, 1);
    const i = z0 * this.res + x0;
    const a = this.data[i];
    const b = this.data[i + 1];
    const c = this.data[i + this.res];
    const d = this.data[i + this.res + 1];
    return a * (1 - tx) * (1 - tz) + b * tx * (1 - tz) + c * (1 - tx) * tz + d * tx * tz;
  }
}

const dummy = new THREE.Object3D();

export class World {
  readonly group = new THREE.Group();
  readonly field: HeightField;
  readonly sun = new THREE.Vector3();
  private lavaMat: THREE.ShaderMaterial;
  private skyMat: THREE.ShaderMaterial;
  private birds: THREE.Group;
  private disposables: THREE.BufferGeometry[] = [];
  private materials: THREE.Material[] = [];
  private lava: THREE.Mesh;

  constructor(mobile: boolean) {
    const res = mobile ? 96 : 168;
    this.field = new HeightField(WORLD_SIZE, res);
    this.group.add(this.buildTerrain());
    this.lavaMat = this.buildLava();
    this.skyMat = this.buildSky();
    this.placeScatter(mobile);
    this.placeSpires();
    this.placeRuins();
    this.birds = this.placeBirds();
    this.addLights();
    this.lava = this.group.getObjectByName("lava") as THREE.Mesh;
  }

  getHeight(x: number, z: number) {
    return this.field.sample(x, z);
  }

  liftAt(x: number, y: number, z: number, thermals: Thermal[]) {
    let lift = 0;
    for (const t of thermals) {
      if (y > t.ceil) continue;
      const d = Math.hypot(x - t.x, z - t.z);
      if (d >= t.radius) continue;
      const radial = 1 - d / t.radius;
      const heightFade = 1 - clamp(y / t.ceil, 0, 1) * 0.35;
      lift = Math.max(lift, radial * radial * t.strength * heightFade);
    }
    return lift;
  }

  update(t: number) {
    this.lavaMat.uniforms.uTime.value = t;
    this.skyMat.uniforms.uTime.value = t;
    this.birds.rotation.y = t * 0.07;
    this.birds.position.y = 78 + Math.sin(t * 0.4) * 4;
  }

  private track<T extends THREE.BufferGeometry>(g: T) {
    this.disposables.push(g);
    return g;
  }
  private mat<T extends THREE.Material>(m: T) {
    this.materials.push(m);
    return m;
  }

  private buildTerrain() {
    const { res, size, data } = this.field;
    const geo = this.track(new THREE.PlaneGeometry(size, size, res - 1, res - 1));
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    const color = new THREE.Color();
    const slag = new THREE.Color(0x1b1410);
    const basalt = new THREE.Color(0x2a2622);
    const ash = new THREE.Color(0x6a6358);
    const rim = new THREE.Color(0x8a8174);
    const ochre = new THREE.Color(0x4a3a30);

    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const col = i % res;
      const row = Math.floor(i / res);
      const y = data[row * res + col] ?? terrainHeight(x, z);
      pos.setY(i, y);
      const r = Math.hypot(x, z);
      if (r < LAVA_R + 8) color.copy(slag);
      else if (r < 120) color.lerpColors(slag, basalt, smoothstep(LAVA_R + 8, 120, r));
      else if (Math.abs(r - RIM_R) < 36) color.lerpColors(basalt, rim, smoothstep(0, 28, 28 - Math.abs(r - RIM_R)));
      else if (r > 240) color.lerpColors(ochre, ash, smoothstep(240, 320, r));
      else color.lerpColors(basalt, ash, 0.45);
      const n = fbm(x * 0.08, z * 0.08, 2, 11);
      color.offsetHSL(0, 0, n * 0.05);
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    const mat = this.mat(
      new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.94,
        metalness: 0.03,
      }),
    );
    const mesh = new THREE.Mesh(geo, mat);
    mesh.receiveShadow = true;
    mesh.name = "terrain";
    return mesh;
  }

  private buildLava() {
    const geo = this.track(new THREE.CircleGeometry(LAVA_R + 1.5, 64));
    geo.rotateX(-Math.PI / 2);
    const mat = this.mat(
      new THREE.ShaderMaterial({
        uniforms: {
          uTime: { value: 0 },
          ...THREE.UniformsLib.fog,
        },
        fog: true,
        vertexShader: `
          varying vec2 vUv;
          #include <fog_pars_vertex>
          void main() {
            vUv = uv;
            vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
            gl_Position = projectionMatrix * mvPosition;
            #include <fog_vertex>
          }
        `,
        fragmentShader: `
          uniform float uTime;
          varying vec2 vUv;
          #include <fog_pars_fragment>
          void main() {
            vec2 p = vUv - 0.5;
            float r = length(p);
            float t = uTime;
            float n = sin(p.x * 28.0 + t * 0.55) * 0.5 + sin(p.y * 24.0 - t * 0.4) * 0.5;
            n += sin((r * 40.0) - t * 1.1) * 0.35;
            vec3 cold = vec3(0.10, 0.025, 0.01);
            vec3 mid = vec3(0.72, 0.16, 0.03);
            vec3 hot = vec3(1.0, 0.42, 0.08);
            vec3 col = mix(cold, mid, smoothstep(-0.5, 0.15, n));
            col = mix(col, hot, smoothstep(0.3, 0.95, n));
            col += hot * smoothstep(0.55, 0.2, r) * 0.15;
            gl_FragColor = vec4(col, 1.0);
            #include <fog_fragment>
          }
        `,
      }),
    );
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.y = -12.2;
    mesh.name = "lava";
    this.group.add(mesh);
    return mat;
  }

  private buildSky() {
    const geo = this.track(new THREE.SphereGeometry(900, 24, 16));
    const mat = this.mat(
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        uniforms: { uTime: { value: 0 }, uSun: { value: new THREE.Vector3() } },
        vertexShader: `
          varying vec3 vDir;
          void main() {
            vDir = position;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: `
          varying vec3 vDir;
          uniform vec3 uSun;
          void main() {
            vec3 n = normalize(vDir);
            float h = clamp(n.y * 0.5 + 0.5, 0.0, 1.0);
            vec3 zenith = vec3(0.10, 0.14, 0.20);
            vec3 horizon = vec3(0.62, 0.38, 0.22);
            vec3 dusk = vec3(0.18, 0.12, 0.12);
            vec3 col = mix(horizon, zenith, pow(h, 1.15));
            col = mix(dusk, col, smoothstep(-0.15, 0.25, n.y));
            float sun = pow(max(dot(n, normalize(uSun)), 0.0), 180.0);
            col += vec3(1.0, 0.72, 0.38) * sun * 1.6;
            float glow = pow(max(dot(n, normalize(uSun)), 0.0), 6.0);
            col += vec3(0.85, 0.35, 0.12) * glow * 0.25;
            gl_FragColor = vec4(col, 1.0);
          }
        `,
      }),
    );
    const mesh = new THREE.Mesh(geo, mat);
    mesh.frustumCulled = false;
    this.group.add(mesh);
    return mat;
  }

  private addLights() {
    this.sun.set(-0.72, 0.22, 0.48).normalize();
    this.skyMat.uniforms.uSun.value.copy(this.sun);

    const hemi = new THREE.HemisphereLight(0x8aa0b4, 0x3a2218, 0.55);
    this.group.add(hemi);
    const dir = new THREE.DirectionalLight(0xffc090, 1.35);
    dir.position.copy(this.sun).multiplyScalar(220);
    dir.castShadow = true;
    dir.shadow.mapSize.set(1024, 1024);
    dir.shadow.camera.near = 10;
    dir.shadow.camera.far = 520;
    dir.shadow.camera.left = -180;
    dir.shadow.camera.right = 180;
    dir.shadow.camera.top = 180;
    dir.shadow.camera.bottom = -180;
    dir.shadow.bias = -0.0007;
    this.group.add(dir);
    const lavaLight = new THREE.PointLight(0xff5a18, 4.2, 220, 1.6);
    lavaLight.position.set(0, -4, 0);
    this.group.add(lavaLight);
    const fill = new THREE.DirectionalLight(0x6a7c90, 0.25);
    fill.position.set(80, 40, -120);
    this.group.add(fill);
  }

  private placeScatter(mobile: boolean) {
    const rng = mulberry32(0xc4de7a);
    const rockGeo = this.track(new THREE.IcosahedronGeometry(1, 0));
    const rockMat = this.mat(
      new THREE.MeshStandardMaterial({ color: 0x3a342e, roughness: 0.95, flatShading: true }),
    );
    const rockN = mobile ? 90 : 170;
    const rocks = new THREE.InstancedMesh(rockGeo, rockMat, rockN);
    rocks.castShadow = true;
    rocks.receiveShadow = true;
    let placed = 0;
    let guard = 0;
    while (placed < rockN && guard++ < 4000) {
      const a = rng() * Math.PI * 2;
      const r = 70 + rng() * 250;
      const x = Math.cos(a) * r;
      const z = Math.sin(a) * r;
      if (Math.hypot(x, z) < LAVA_R + 10) continue;
      const y = this.getHeight(x, z);
      dummy.position.set(x, y, z);
      dummy.rotation.set(rng() * 1.2, rng() * 6, rng() * 1.2);
      const s = 1.2 + rng() * 4.2;
      dummy.scale.set(s, s * (0.6 + rng() * 0.8), s);
      dummy.updateMatrix();
      rocks.setMatrixAt(placed, dummy.matrix);
      placed++;
    }
    rocks.instanceMatrix.needsUpdate = true;
    this.group.add(rocks);

    const trunkGeo = this.track(new THREE.CylinderGeometry(0.18, 0.28, 4.2, 5));
    const crownGeo = this.track(new THREE.ConeGeometry(1.6, 5.4, 6));
    const wood = this.mat(new THREE.MeshStandardMaterial({ color: 0x2a221c, roughness: 0.9, flatShading: true }));
    const needle = this.mat(new THREE.MeshStandardMaterial({ color: 0x3d4338, roughness: 0.85, flatShading: true }));
    const pineN = mobile ? 36 : 64;
    const trunks = new THREE.InstancedMesh(trunkGeo, wood, pineN);
    const crowns = new THREE.InstancedMesh(crownGeo, needle, pineN);
    trunks.castShadow = true;
    crowns.castShadow = true;
    let p = 0;
    guard = 0;
    while (p < pineN && guard++ < 3000) {
      const a = rng() * Math.PI * 2;
      const r = 230 + rng() * 90;
      const x = Math.cos(a) * r;
      const z = Math.sin(a) * r;
      const y = this.getHeight(x, z);
      const s = 0.7 + rng() * 1.1;
      dummy.position.set(x, y + 2.1 * s, z);
      dummy.rotation.set(0, rng() * 6, 0);
      dummy.scale.set(s, s, s);
      dummy.updateMatrix();
      trunks.setMatrixAt(p, dummy.matrix);
      dummy.position.y = y + 5.6 * s;
      dummy.updateMatrix();
      crowns.setMatrixAt(p, dummy.matrix);
      p++;
    }
    trunks.instanceMatrix.needsUpdate = true;
    crowns.instanceMatrix.needsUpdate = true;
    this.group.add(trunks, crowns);
  }

  private placeSpires() {
    const rng = mulberry32(0x51fe01);
    const geo = this.track(new THREE.CylinderGeometry(0.4, 2.4, 1, 6));
    const mat = this.mat(
      new THREE.MeshStandardMaterial({ color: 0x322c28, roughness: 0.92, flatShading: true }),
    );
    const n = 22;
    const mesh = new THREE.InstancedMesh(geo, mat, n);
    mesh.castShadow = true;
    for (let i = 0; i < n; i++) {
      const a = 4.15 + (i / n) * 1.55 + (rng() - 0.5) * 0.12;
      const r = 232 + rng() * 28;
      const x = Math.cos(a) * r;
      const z = Math.sin(a) * r;
      const y = this.getHeight(x, z);
      const h = 10 + rng() * 18;
      dummy.position.set(x, y + h * 0.5, z);
      dummy.rotation.set(0, rng() * 6, (rng() - 0.5) * 0.15);
      dummy.scale.set(1.4 + rng(), h, 1.4 + rng());
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    this.group.add(mesh);
  }

  private placeRuins() {
    const colGeo = this.track(new THREE.CylinderGeometry(0.7, 0.85, 9, 8));
    const capGeo = this.track(new THREE.BoxGeometry(2.2, 0.45, 2.2));
    const stone = this.mat(
      new THREE.MeshStandardMaterial({ color: 0x5a534a, roughness: 0.88, metalness: 0.05, flatShading: true }),
    );
    const spots = [
      [70, 1.1],
      [95, 2.4],
      [-60, 0.4],
      [40, 3.3],
      [-90, 4.8],
      [110, 5.2],
    ] as const;
    spots.forEach(([r, a]) => {
      const x = Math.cos(a) * r;
      const z = Math.sin(a) * r;
      const y = this.getHeight(x, z);
      const col = new THREE.Mesh(colGeo, stone);
      col.position.set(x, y + 4.5, z);
      col.castShadow = true;
      const cap = new THREE.Mesh(capGeo, stone);
      cap.position.set(x, y + 9.1, z);
      cap.rotation.y = a;
      this.group.add(col, cap);
    });

    const lintelGeo = this.track(new THREE.BoxGeometry(8.5, 0.7, 1.4));
    const archA = 1.15;
    const archR = 100;
    const ax = Math.cos(archA) * archR;
    const az = Math.sin(archA) * archR;
    const ay = this.getHeight(ax, az);
    const left = new THREE.Mesh(colGeo, stone);
    const right = new THREE.Mesh(colGeo, stone);
    const lintel = new THREE.Mesh(lintelGeo, stone);
    const tangent = archA + Math.PI / 2;
    left.position.set(ax + Math.cos(tangent) * 3.6, ay + 4.5, az + Math.sin(tangent) * 3.6);
    right.position.set(ax - Math.cos(tangent) * 3.6, ay + 4.5, az - Math.sin(tangent) * 3.6);
    lintel.position.set(ax, ay + 9.2, az);
    lintel.rotation.y = -archA;
    this.group.add(left, right, lintel);
  }

  private placeBirds() {
    const g = new THREE.Group();
    const geo = this.track(new THREE.ConeGeometry(0.35, 1.4, 3));
    geo.rotateX(Math.PI / 2);
    const mat = this.mat(new THREE.MeshBasicMaterial({ color: 0x1a1816 }));
    for (let i = 0; i < 11; i++) {
      const m = new THREE.Mesh(geo, mat);
      const a = (i / 11) * Math.PI * 2;
      m.position.set(Math.cos(a) * 14, Math.sin(i * 1.7) * 2, Math.sin(a) * 14);
      m.lookAt(0, 0, 0);
      g.add(m);
    }
    g.position.set(-40, 80, 90);
    this.group.add(g);
    return g;
  }

  dispose() {
    this.disposables.forEach((g) => g.dispose());
    this.materials.forEach((m) => m.dispose());
  }
}
