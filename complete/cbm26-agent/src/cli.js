#!/usr/bin/env node
import { createCBM26 } from "./model.js";
const model = createCBM26();
const input = process.argv.slice(2).join(" ") || "status";
const out = await model.turn(input);
console.log(out.reply);
console.log("---");
console.log(JSON.stringify({ ms: out.ms, action: out.decision.action }, null, 2));
