#!/usr/bin/env node
import { createApp } from "../src/index.js";
const app = await createApp();
const input = process.argv.slice(2).join(" ") || "status";
const out = await app.cycle(input);
console.log(out.reply ?? out);
console.log(JSON.stringify({ cycle: out.cycle, ms: out.ms, action: out.decision?.action }, null, 2));
