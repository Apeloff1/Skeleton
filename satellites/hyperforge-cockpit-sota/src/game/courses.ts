import type { Course, CourseId, RingDef, Thermal } from "./types";

export const LAVA_R = 50;
export const RIM_R = 198;
export const WORLD_SIZE = 640;

type HeightFn = (x: number, z: number) => number;

function yawTo(fromX: number, fromZ: number, toX: number, toZ: number) {
  return Math.atan2(-(toX - fromX), -(toZ - fromZ));
}

function closeRings(rings: RingDef[]) {
  for (let i = 0; i < rings.length; i++) {
    const a = rings[i];
    const b = rings[(i + 1) % rings.length];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dz = b.z - a.z;
    const len = Math.hypot(dx, dy, dz) || 1;
    a.nx = dx / len;
    a.ny = dy / len;
    a.nz = dz / len;
  }
  return rings;
}

function openRings(rings: RingDef[]) {
  for (let i = 0; i < rings.length; i++) {
    const a = rings[i];
    const b = rings[Math.min(i + 1, rings.length - 1)];
    const dx = b.x - a.x || a.nx;
    const dy = b.y - a.y;
    const dz = b.z - a.z || a.nz;
    const len = Math.hypot(dx, dy, dz) || 1;
    a.nx = dx / len;
    a.ny = dy / len;
    a.nz = dz / len;
  }
  return rings;
}

function polar(
  angle: number,
  radius: number,
  alt: number,
  getHeight: HeightFn,
  ringR = 7.2,
): RingDef {
  const x = Math.cos(angle) * radius;
  const z = Math.sin(angle) * radius;
  return {
    x,
    y: getHeight(x, z) + alt,
    z,
    nx: -Math.sin(angle),
    ny: 0,
    nz: Math.cos(angle),
    radius: ringR,
  };
}

function thermal(angle: number, radius: number, rad: number, strength: number, ceil: number): Thermal {
  return {
    x: Math.cos(angle) * radius,
    z: Math.sin(angle) * radius,
    radius: rad,
    strength,
    ceil,
  };
}

export function buildCourses(getHeight: HeightFn): Course[] {
  const rimRings: RingDef[] = [];
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
    const wobble = Math.sin(i * 1.7) * 10;
    rimRings.push(polar(a, RIM_R + wobble, 26 + (i % 3) * 2, getHeight, 7.4));
  }
  closeRings(rimRings);
  const rimStart = rimRings[0];
  const rim: Course = {
    id: "rim",
    name: "Rim Circuit",
    blurb: "A clean lap along the inner rim. Learn the bank.",
    par: 42,
    start: {
      x: rimStart.x - rimStart.nx * 36,
      y: rimStart.y + 10,
      z: rimStart.z - rimStart.nz * 36,
      yaw: yawTo(rimStart.x - rimStart.nx * 32, rimStart.z - rimStart.nz * 32, rimStart.x, rimStart.z),
    },
    rings: rimRings,
    thermals: [
      thermal(-0.4, 150, 28, 18, 120),
      thermal(1.6, 155, 26, 16, 120),
      thermal(3.5, 148, 30, 17, 120),
    ],
  };

  const bowlPts: { a: number; r: number; alt: number }[] = [
    { a: 0.15, r: 200, alt: 28 },
    { a: 0.45, r: 168, alt: 26 },
    { a: 0.8, r: 132, alt: 24 },
    { a: 1.15, r: 100, alt: 30 },
    { a: 1.55, r: 86, alt: 36 },
    { a: 2.05, r: 78, alt: 42 },
    { a: 2.55, r: 92, alt: 34 },
    { a: 3.05, r: 128, alt: 26 },
    { a: 3.45, r: 170, alt: 24 },
    { a: 3.85, r: 205, alt: 26 },
  ];
  const bowlRings = openRings(bowlPts.map((p) => polar(p.a, p.r, p.alt, getHeight, 7.6)));
  const b0 = bowlRings[0];
  const bowl: Course = {
    id: "bowl",
    name: "Ash Descent",
    blurb: "Dive the bowl, skim the heat, climb the far wall.",
    par: 48,
    lockedBy: "rim",
    start: {
      x: b0.x - b0.nx * 30,
      y: b0.y + 8,
      z: b0.z - b0.nz * 30,
      yaw: yawTo(b0.x - b0.nx * 30, b0.z - b0.nz * 30, b0.x, b0.z),
    },
    rings: bowlRings,
    thermals: [
      thermal(1.7, 70, 36, 26, 140),
      thermal(2.4, 88, 24, 18, 130),
      thermal(3.4, 160, 22, 14, 120),
    ],
  };

  const spirePts: { a: number; r: number; alt: number; rad?: number }[] = [
    { a: 4.0, r: 210, alt: 26 },
    { a: 4.22, r: 228, alt: 28 },
    { a: 4.42, r: 246, alt: 24, rad: 6.4 },
    { a: 4.58, r: 238, alt: 30, rad: 6.2 },
    { a: 4.78, r: 252, alt: 22, rad: 6.0 },
    { a: 5.0, r: 236, alt: 27, rad: 6.4 },
    { a: 5.22, r: 218, alt: 25 },
    { a: 5.5, r: 200, alt: 24 },
    { a: 5.85, r: 188, alt: 28 },
    { a: 6.2, r: 196, alt: 26 },
  ];
  const spireRings = openRings(
    spirePts.map((p) => polar(p.a, p.r, p.alt, getHeight, p.rad ?? 7.0)),
  );
  const s0 = spireRings[0];
  const spire: Course = {
    id: "spire",
    name: "Needle Field",
    blurb: "Thread basalt needles on the outer shoulder.",
    par: 44,
    lockedBy: "bowl",
    start: {
      x: s0.x - s0.nx * 28,
      y: s0.y + 7,
      z: s0.z - s0.nz * 28,
      yaw: yawTo(s0.x - s0.nx * 28, s0.z - s0.nz * 28, s0.x, s0.z),
    },
    rings: spireRings,
    thermals: [thermal(5.1, 210, 22, 15, 110), thermal(5.9, 170, 26, 17, 120)],
  };

  const helixRings: RingDef[] = [];
  for (let i = 0; i < 16; i++) {
    const t = i / 15;
    const a = -0.2 + t * Math.PI * 2.65;
    const r = 188 - t * 108;
    const alt = 30 - t * 10 + (t > 0.72 ? (t - 0.72) * 48 : 0);
    helixRings.push(polar(a, r, alt, getHeight, 6.8));
  }
  openRings(helixRings);
  const h0 = helixRings[0];
  const helix: Course = {
    id: "helix",
    name: "Helios Coil",
    blurb: "A descending spiral, then a thermal punch to the sun gate.",
    par: 52,
    lockedBy: "spire",
    start: {
      x: h0.x - h0.nx * 30,
      y: h0.y + 8,
      z: h0.z - h0.nz * 30,
      yaw: yawTo(h0.x - h0.nx * 30, h0.z - h0.nz * 30, h0.x, h0.z),
    },
    rings: helixRings,
    thermals: [
      thermal(1.4, 92, 40, 28, 150),
      thermal(2.8, 80, 32, 24, 150),
      thermal(4.2, 140, 22, 16, 130),
    ],
  };

  const free: Course = {
    id: "free",
    name: "Free Soar",
    blurb: "No gates. Ride thermals, chase the rim, stay aloft.",
    par: 0,
    start: { x: 0, y: getHeight(0, 210) + 32, z: 210, yaw: Math.PI },
    rings: [],
    thermals: [
      thermal(0.2, 150, 32, 20, 140),
      thermal(1.4, 70, 40, 28, 150),
      thermal(2.3, 160, 28, 18, 130),
      thermal(3.6, 145, 30, 19, 130),
      thermal(4.8, 80, 36, 24, 145),
      thermal(5.7, 175, 26, 16, 120),
    ],
  };

  return [rim, bowl, spire, helix, free];
}

export const COURSE_ORDER: CourseId[] = ["rim", "bowl", "spire", "helix", "free"];
