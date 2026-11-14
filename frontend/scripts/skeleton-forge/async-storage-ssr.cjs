'use strict';
// Process-local stand-in for native storage; never persists to device or disk.
const data = new Map();
module.exports = {
  async getItem(key) { return data.has(key) ? data.get(key) : null; },
  async setItem(key, value) { data.set(key, value); },
  async removeItem(key) { data.delete(key); },
  async getAllKeys() { return [...data.keys()]; },
  async multiGet(keys) { return keys.map(key => [key, data.get(key) ?? null]); },
  async multiRemove(keys) { for (const key of keys) data.delete(key); },
};
