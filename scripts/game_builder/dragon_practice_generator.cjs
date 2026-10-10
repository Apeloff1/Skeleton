"use strict";

/* Original offline puzzle generator for Dragon's owned game-builder practice lane.
 * All decisions are seeded, output has canonical JSON and a BFS witness that
 * replays against the Python game engine. No reference games or assets are read.
 */
function practiceRng(id) {
  let state = (0x6D2B79F5 ^ Math.imul(id, 0x9E3779B1)) >>> 0;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
}
const DIRECTIONS = [
  ["up", 0, -1], ["left", -1, 0], ["right", 1, 0], ["down", 0, 1],
];

function provePracticeLevel(grid) {
  const height = grid.length;
  const width = grid[0].length;
  const locations = { S: [], G: [], C: [] };
  grid.forEach((row, y) => row.forEach((cell, x) => {
    if (locations[cell]) locations[cell].push([x, y]);
  }));
  if (locations.S.length !== 1 || locations.G.length !== 1 ||
      locations.C.length < 1 || locations.C.length > 6) {
    throw new Error("practice game objectives malformed");
  }
  const collectedBits = new Map(
    locations.C.map(([x, y], i) => [x + "," + y, 1 << i]),
  );
  const full = (1 << locations.C.length) - 1;
  const queue = [[...locations.S[0], 0]];
  const parent = new Map([[queue[0].join(","), null]]);
  let terminal = null;
  for (let i = 0; i < queue.length; i++) {
    const [x, y, mask] = queue[i];
    if (x === locations.G[0][0] && y === locations.G[0][1] && mask === full) {
      terminal = queue[i];
      break;
    }
    for (const [action, dx, dy] of DIRECTIONS) {
      const nextX = x + dx;
      const nextY = y + dy;
      if (nextX < 0 || nextY < 0 || nextX >= width || nextY >= height ||
          "#H".includes(grid[nextY][nextX])) continue;
      const next = [
        nextX, nextY, mask | (collectedBits.get(nextX + "," + nextY) || 0),
      ];
      const key = next.join(",");
      if (parent.has(key)) continue;
      parent.set(key, { previous: queue[i].join(","), action });
      queue.push(next);
    }
  }
  if (terminal === null) throw new Error("original practice game unsolvable");
  const reversed = [];
  const positions = new Set();
  let key = terminal.join(",");
  while (key !== null) {
    const [x, y] = key.split(",");
    positions.add(x + "," + y);
    const step = parent.get(key);
    if (step === null) break;
    reversed.push(step.action);
    key = step.previous;
  }
  return { actions: reversed.reverse(), positions };
}

function makePracticeGame(id) {
  if (!Number.isInteger(id) || id < 1 || id > 100) {
    throw new Error("practice game index must be 1..100");
  }
  const random = practiceRng(id);
  const width = 11 + 4 * (id % 3);
  const height = 11 + 4 * (Math.floor(id / 3) % 3);
  const grid = Array.from({ length: height }, () => Array(width).fill("#"));
  grid[1][1] = ".";
  const stack = [[1, 1]];
  while (stack.length) {
    const [x, y] = stack[stack.length - 1];
    const choices = [];
    for (const [, dx, dy] of DIRECTIONS) {
      const xx = x + dx * 2;
      const yy = y + dy * 2;
      if (xx > 0 && xx < width - 1 && yy > 0 &&
          yy < height - 1 && grid[yy][xx] === "#") {
        choices.push([xx, yy, dx, dy]);
      }
    }
    if (!choices.length) {
      stack.pop();
      continue;
    }
    const [xx, yy, dx, dy] = choices[Math.floor(random() * choices.length)];
    grid[y + dy][x + dx] = ".";
    grid[yy][xx] = ".";
    stack.push([xx, yy]);
  }
  // Independent side corridors give players alternative route choices.
  for (let n = 0; n < id % 5; n++) {
    const candidates = [];
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        if (grid[y][x] === "#" &&
            ((grid[y - 1][x] !== "#" && grid[y + 1][x] !== "#") ||
             (grid[y][x - 1] !== "#" && grid[y][x + 1] !== "#"))) {
          candidates.push([x, y]);
        }
      }
    }
    if (!candidates.length) break;
    const [x, y] = candidates[Math.floor(random() * candidates.length)];
    grid[y][x] = ".";
  }
  const distance = new Map([["1,1", 0]]);
  const reachable = [[1, 1]];
  for (let i = 0; i < reachable.length; i++) {
    const [x, y] = reachable[i];
    for (const [, dx, dy] of DIRECTIONS) {
      const xx = x + dx;
      const yy = y + dy;
      const key = xx + "," + yy;
      if (xx <= 0 || xx >= width - 1 || yy <= 0 || yy >= height - 1 ||
          grid[yy][xx] === "#" || distance.has(key)) continue;
      distance.set(key, distance.get(x + "," + y) + 1);
      reachable.push([xx, yy]);
    }
  }
  const furthest = [...distance.entries()]
    .filter(([key]) => key !== "1,1")
    .sort((a, b) => b[1] - a[1] ||
      (a[0] < b[0] ? -1 : a[0] === b[0] ? 0 : 1));
  const [goalX, goalY] = furthest[0][0].split(",").map(Number);
  grid[goalY][goalX] = "G";
  grid[1][1] = "S";
  const collectibleCount = 1 + id % 4;
  const used = [];
  const candidates = furthest.slice(1).filter(([key, dist]) =>
    dist > 2 && key !== goalX + "," + goalY,
  ).map(([key]) => key);
  for (let j = 0; j < collectibleCount; j++) {
    const pool = candidates.filter(key => {
      if (used.includes(key)) return false;
      const [x, y] = key.split(",").map(Number);
      return used.every(previous => {
        const [px, py] = previous.split(",").map(Number);
        return Math.abs(x - px) + Math.abs(y - py) >= 3;
      });
    });
    if (!pool.length) throw new Error("insufficient original objectives");
    const key = pool[Math.floor(random() * pool.length)];
    used.push(key);
    const [x, y] = key.split(",").map(Number);
    grid[y][x] = "C";
  }
  const protectedPositions = provePracticeLevel(grid).positions;
  const hazardCandidates = [];
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      if (grid[y][x] !== "." || protectedPositions.has(x + "," + y)) continue;
      const exits = DIRECTIONS.filter(([, dx, dy]) =>
        grid[y + dy][x + dx] !== "#",
      ).length;
      hazardCandidates.push({ x, y, deadEnd: exits <= 1, tie: random() });
    }
  }
  hazardCandidates.sort((a, b) =>
    Number(b.deadEnd) - Number(a.deadEnd) || a.tie - b.tie,
  );
  const hazardCount = Math.min(id % 6, hazardCandidates.length);
  for (let j = 0; j < hazardCount; j++) {
    grid[hazardCandidates[j].y][hazardCandidates[j].x] = "H";
  }
  const solution = provePracticeLevel(grid);
  if (!solution.actions.length || solution.actions.length > 20000) {
    throw new Error("practice game solution outside budget");
  }
  const themes = ["forest", "space", "desert", "ocean", "arcade"];
  const adjectives = [
    "Luminous", "Copper", "Saffron", "Orbit", "Verdant",
    "Silver", "Crystal", "Amber", "Cobalt", "Dusk",
  ];
  const places = [
    "Labyrinth", "Atrium", "Harbor", "Starfield", "Cavern",
    "Gateway", "Runes", "Passage", "Circuit", "Sanctum",
  ];
  const gameId = "dragon-practice-" + String(id).padStart(3, "0");
  return {
    schema: "skeleton.dragon.original_practice_game.v1",
    intent: {
      project_id: gameId,
      title: adjectives[Math.floor((id - 1) / 10)] + " " + places[(id - 1) % 10],
      subtitle: "Original one-level collectible-and-exit puzzle. A Dragon practice build with verified safe completion.",
      seed: Math.imul(id, 982451653) >>> 0,
      width, height, levels: 1, collectibles_per_level: collectibleCount,
      hazards_per_level: hazardCount, theme: themes[(id - 1) % 5],
      starting_health: 2 + (id % 4),
    },
    rows: grid.map(row => row.join("")),
    safe_solution: solution.actions,
    originality_status: "original_algorithmic_no_external_media",
    release_state: "practice_only_not_hardware_verified",
  };
}

function canonicalPracticeJSON(value) {
  if (Array.isArray(value)) return "[" + value.map(canonicalPracticeJSON).join(",") + "]";
  if (value !== null && typeof value === "object") {
    return "{" + Object.keys(value).sort()
      .map(key => JSON.stringify(key) + ":" + canonicalPracticeJSON(value[key]))
      .join(",") + "}";
  }
  if (typeof value === "number" && !Number.isFinite(value)) {
    throw new Error("nonfinite game parameter");
  }
  return JSON.stringify(value);
}

if (typeof module !== "undefined") {
  module.exports = { makePracticeGame, canonicalPracticeJSON, provePracticeLevel };
}
if (typeof require !== "undefined" && typeof module !== "undefined" &&
    require.main === module) {
  const fs = require("node:fs");
  const path = require("node:path");
  const [flag, output] = process.argv.slice(2);
  if (!["--check", "--write"].includes(flag) || !output) {
    throw new Error("usage: node dragon_practice_generator.cjs --check|--write DIRECTORY");
  }
  for (let id = 1; id <= 100; id++) {
    const pack = makePracticeGame(id);
    const dest = path.join(output, pack.intent.project_id + ".json");
    const bytes = canonicalPracticeJSON(pack) + "\n";
    if (Buffer.byteLength(bytes) > 16384) throw new Error("game pack exceeds byte budget");
    if (flag === "--write") fs.writeFileSync(dest, bytes, { flag: "wx" });
    else if (fs.readFileSync(dest, "utf8") !== bytes) throw new Error("pack drift " + dest);
  }
  process.stdout.write("100 original practice games generated/verified\n");
}
