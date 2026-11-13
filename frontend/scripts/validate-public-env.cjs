#!/usr/bin/env node
'use strict';
// Validates the EXPO_PUBLIC_* values that get inlined into the web/mobile
// bundle for a target environment. Everything here is PUBLIC: secrets must
// never use the EXPO_PUBLIC_ prefix, and this check rejects names that look
// like credentials. Usage: node scripts/validate-public-env.cjs [development|staging|production]

const ENVIRONMENTS = ['development', 'staging', 'production'];
const REQUIRED_URLS = ['EXPO_PUBLIC_BACKEND_URL', 'EXPO_PUBLIC_SKELETON_URL'];
const SECRETISH = /(SECRET|TOKEN|PASSWORD|PRIVATE|API_KEY|_KEY$)/;

/**
 * WHATWG URL canonicalizes abbreviated/hex IPv4 and bracketed IPv6 before
 * exposing hostname. Block the complete 127/8 range and its IPv4-mapped IPv6
 * equivalent, not just 127.0.0.1. Leave local development unrestricted.
 */
function isLoopbackHostname(hostname) {
  const host = hostname.toLowerCase().replace(/\.+$/, '');
  if (host === 'localhost' || host.endsWith('.localhost')) return true;
  if (/^127(?:\.\d{1,3}){3}$/.test(host)) return true;

  // Node's URL.hostname encloses IPv6 in brackets and normalizes zero runs.
  const ipv6 = host.startsWith('[') && host.endsWith(']')
    ? host.slice(1, -1)
    : host;
  if (ipv6 === '::1') return true;
  const mapped = /^::ffff:([0-9a-f]{1,4}):[0-9a-f]{1,4}$/.exec(ipv6);
  return mapped !== null && (Number.parseInt(mapped[1], 16) & 0xff00) === 0x7f00;
}

function validatePublicEnv(environment, env) {
  const problems = [];
  if (!ENVIRONMENTS.includes(environment)) {
    problems.push(`environment must be one of ${ENVIRONMENTS.join(', ')} (got ${environment})`);
  }
  const strict = environment === 'staging' || environment === 'production';
  for (const name of REQUIRED_URLS) {
    const raw = (env[name] || '').trim();
    if (!raw) { problems.push(`${name} is required`); continue; }
    let url;
    try { url = new URL(raw); } catch { problems.push(`${name} is not a valid URL`); continue; }
    if (!['http:', 'https:'].includes(url.protocol)) problems.push(`${name} must be http(s)`);
    // URL userinfo is shipped to every client, including in development builds.
    if (url.username || url.password) {
      problems.push(`${name} must not contain URL credentials (public client build)`);
    }
    if (strict && isLoopbackHostname(url.hostname)) {
      problems.push(`${name} must not point at localhost or loopback in ${environment}`);
    }
    if (environment === 'production' && url.protocol !== 'https:') {
      problems.push(`${name} must use https in production`);
    }
  }
  const overlay = (env.EXPO_PUBLIC_DEV_LOG_OVERLAY || '0').trim();
  if (!['0', '1'].includes(overlay)) problems.push('EXPO_PUBLIC_DEV_LOG_OVERLAY must be 0 or 1');
  if (environment === 'production' && overlay === '1') {
    problems.push('EXPO_PUBLIC_DEV_LOG_OVERLAY must be 0 in production');
  }
  for (const name of Object.keys(env)) {
    if (name.startsWith('EXPO_PUBLIC_') && SECRETISH.test(name.slice('EXPO_PUBLIC_'.length))) {
      problems.push(`${name} looks like a secret; EXPO_PUBLIC_ values ship to every client`);
    }
  }
  return problems;
}

module.exports = { validatePublicEnv, ENVIRONMENTS, REQUIRED_URLS };

if (require.main === module) {
  const environment = process.argv[2] || process.env.APP_ENV || 'development';
  const problems = validatePublicEnv(environment, process.env);
  if (problems.length) {
    console.error(`Invalid public env for ${environment}:\n  - ${problems.join('\n  - ')}`);
    process.exit(1);
  }
  console.log(`public env OK for ${environment}`);
}
