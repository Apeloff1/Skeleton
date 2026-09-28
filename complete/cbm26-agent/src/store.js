import { hash32, now } from "./util.js";
export function createStore() {
  const rows = [];
  async function append(event) {
    const row = { id: "ep_" + hash32(JSON.stringify(event) + now()).toString(16), at: now(), ...event };
    rows.push(row);
    return row;
  }
  async function all() { return rows.slice(); }
  function snapshot() { return { count: rows.length }; }
  return { append, all, snapshot };
}
