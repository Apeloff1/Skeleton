import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { chmodSync, copyFileSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

// Run against the production image after building it, without starting the app
// stack or calling a model. Both HTTP responders use that same local image.
// NGINX_TEST_IMAGE=frontend:test node --test scripts/test-nginx-runtime-dns.mjs
// Before rebuilding, NGINX_TEST_SOURCE_CONFIG=1 explicitly tests a source mount.
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dockerEnv = { ...process.env };
for (const key of ['DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH']) {
  delete dockerEnv[key];
}
function docker(...args) {
  return execFileSync('docker', ['--host=unix:///var/run/docker.sock', ...args], {
    encoding: 'utf8', env: dockerEnv, timeout: 20_000, stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}
const pause = (ms) => new Promise((done) => setTimeout(done, ms));
async function eventually(action, label) {
  const deadline = Date.now() + 25_000;
  let failure;
  do {
    try { return await action(); } catch (error) { failure = error; }
    await pause(250);
  } while (Date.now() < deadline);
  throw new Error(`${label}: ${failure?.message}`, { cause: failure });
}

test('production ingress starts without upstream DNS and recovers after service replacement', { timeout: 150_000 }, async (t) => {
  const image = process.env.NGINX_TEST_IMAGE;
  assert.ok(image, 'NGINX_TEST_IMAGE must name an already built local production frontend image');
  docker('image', 'inspect', image);
  const suffix = `${process.pid}-${Date.now()}`;
  const network = `nginx-dns-${suffix}`;
  const frontend = `${network}-frontend`;
  const containers = [];
  const scratch = mkdtempSync(join(tmpdir(), 'nginx-dns-'));
  const securityHeaders = {
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'SAMEORIGIN',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'permissions-policy': 'camera=(), microphone=(), geolocation=()',
    'content-security-policy': "frame-ancestors 'self'; base-uri 'self'; object-src 'none'",
    'x-permitted-cross-domain-policies': 'none',
  };
  let origin;
  async function request(path) {
    return fetch(`${origin}${path}`, { signal: AbortSignal.timeout(8_000) });
  }
  function assertHeaders(response) {
    for (const [key, value] of Object.entries(securityHeaders)) {
      assert.equal(response.headers.get(key), value, key);
    }
  }
  function startResponder(service, revision) {
    const name = `${network}-${service}-${revision}`;
    const config = join(scratch, `${service}-${revision}.conf`);
    writeFileSync(config, `pid /run/nginx.pid;
events { worker_connections 32; }
http {
  access_log off;
  server {
    listen 8001;
    default_type application/json;
    return 200 '{"service":"${service}","revision":"${revision}","uri":"$request_uri","host":"$http_host","protocol":"$server_protocol","forwardedProto":"$http_x_forwarded_proto"}';
  }
}
`);
    chmodSync(config, 0o644);
    containers.push(name);
    docker('run', '-d', '--pull=never', '--name', name, '--network', network,
      '--network-alias', service, '--cpus=0.25', '--memory=64m',
      '--mount', `type=bind,source=${config},target=/tmp/responder.conf,readonly`,
      '--entrypoint', 'nginx', image, '-c', '/tmp/responder.conf', '-g', 'daemon off;');
    return name;
  }
  async function assertProxy(path, service, revision) {
    const response = await request(path);
    assert.equal(response.status, 200);
    assertHeaders(response);
    assert.deepEqual(await response.json(), {
      service, revision, uri: path, host: '127.0.0.1', protocol: 'HTTP/1.1', forwardedProto: 'http',
    });
  }
  try {
    docker('network', 'create', network);
    const ingressConfig = join(scratch, 'ingress.conf');
    copyFileSync(join(frontendRoot, 'nginx.conf'), ingressConfig);
    chmodSync(ingressConfig, 0o644);
    const ingressMount = [];
    if (process.env.NGINX_TEST_SOURCE_CONFIG === '1') {
      ingressMount.push('--mount', `type=bind,source=${ingressConfig},target=/etc/nginx/conf.d/default.conf,readonly`);
      t.diagnostic('Pre-build proof: testing source ingress mounted into the existing image.');
    } else {
      const installedConfig = docker('run', '--rm', '--pull=never', '--entrypoint', 'cat', image, '/etc/nginx/conf.d/default.conf');
      assert.equal(installedConfig, readFileSync(ingressConfig, 'utf8').trim(), 'production image must contain the current ingress config');
    }
    // Keep this regression small on large CI hosts. All application ingress
    // directives still come directly from the unchanged production source.
    const mainConfig = join(scratch, 'nginx.conf');
    const originalMainConfig = docker('run', '--rm', '--pull=never', '--entrypoint', 'cat', image, '/etc/nginx/nginx.conf');
    assert.match(originalMainConfig, /worker_processes\s+auto;/);
    writeFileSync(mainConfig, originalMainConfig.replace(/worker_processes\s+auto;/, 'worker_processes 1;'));
    chmodSync(mainConfig, 0o644);
    containers.push(frontend);
    docker('run', '-d', '--pull=never', '--name', frontend, '--network', network,
      '--publish', '127.0.0.1::8080', '--cpus=0.5', '--memory=128m',
      ...ingressMount,
      '--mount', `type=bind,source=${mainConfig},target=/etc/nginx/nginx.conf,readonly`, image);
    const port = await eventually(() => {
      const bindings = JSON.parse(docker('inspect', '--format', '{{json .NetworkSettings.Ports}}', frontend));
      assert.ok(bindings['8080/tcp']?.[0]?.HostPort, 'frontend must stay running with its published port');
      return bindings['8080/tcp'][0].HostPort;
    }, 'frontend startup');
    origin = `http://127.0.0.1:${port}`;

    await t.test('missing backend and engine DNS leave static setup healthy and APIs return 502', async () => {
      await eventually(async () => {
        const health = await request('/healthz');
        assert.equal(health.status, 200);
        assertHeaders(health);
        assert.equal(health.headers.get('cache-control'), 'no-store');
        assert.equal(await health.text(), 'ok\n');
      }, 'static health');
      docker('exec', frontend, 'nginx', '-t');
      const setup = await request('/setup');
      assert.equal(setup.status, 200);
      assertHeaders(setup);
      assert.equal(setup.headers.get('cache-control'), 'no-cache');
      assert.match(await setup.text(), /<!doctype html>/i);
      for (const path of ['/api/dns-probe?phase=missing', '/api/v1/models?phase=missing']) {
        const response = await request(path);
        assert.equal(response.status, 502, path);
        assertHeaders(response);
        await response.text();
      }
    });

    const backend = startResponder('backend', 'first');
    startResponder('skeleton', 'first');
    await t.test('new DNS records recover every API route without rewriting paths or queries', async () => {
      await eventually(() => assertProxy('/api/dns-probe?word=a%20b&encoded=%2F', 'backend', 'first'), 'backend DNS recovery');
      await eventually(() => assertProxy('/api/v1/models?word=a%20b&encoded=%2F', 'skeleton', 'first'), 'engine DNS recovery');
      await assertProxy('/api/v1/conversations?word=a%20b&encoded=%2F', 'backend', 'first');
      await assertProxy('/api/v1/conversations/example/events?cursor=a%2Fb', 'backend', 'first');
    });

    await t.test('replacement at a different IP recovers without restarting nginx', async () => {
      const oldAddress = docker('inspect', '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', backend);
      const replacement = startResponder('backend', 'replacement');
      const newAddress = docker('inspect', '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', replacement);
      assert.notEqual(newAddress, oldAddress, 'replacement must exercise a new IP');
      docker('rm', '-f', backend);
      await eventually(() => assertProxy('/api/dns-probe?phase=replaced', 'backend', 'replacement'), 'replacement DNS recovery');
      const state = JSON.parse(docker('inspect', '--format', '{"running":{{.State.Running}},"restarts":{{.RestartCount}}}', frontend));
      assert.deepEqual(state, { running: true, restarts: 0 });
      t.diagnostic(`Backend recovered from ${oldAddress} to ${newAddress}; frontend restart count stayed zero.`);
    });
  } catch (error) {
    try { t.diagnostic(docker('logs', '--tail', '35', frontend)); } catch { /* May fail before creation. */ }
    throw error;
  } finally {
    for (const name of containers.reverse()) {
      try { docker('rm', '-f', name); } catch { /* Already removed or never created. */ }
    }
    try { docker('network', 'rm', network); } catch { /* Creation may have failed. */ }
    rmSync(scratch, { recursive: true, force: true });
  }
});
