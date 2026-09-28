#!/usr/bin/env node
import { createSystem } from "../src/system.js";
const sys = createSystem();
const input = process.argv.slice(2).join(" ") || "status";
const out = await sys.cycle(input);
console.log(out.reply);
console.log(JSON.stringify({ cycle: out.cycle, ms: out.ms, action: out.decision?.action }, null, 2));
