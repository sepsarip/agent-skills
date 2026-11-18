#!/usr/bin/env node
/**
 * Unit & integration tests for skills/record-web-demo/scripts/demo-harness.mjs.
 * Uses Node.js built-in node:test and node:assert (zero external packages).
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import {
  buildSpeedRampFilter,
  discoverEnvironment,
  normalizeSegments,
  recordDemo,
  transcodeVideo,
} from '../scripts/demo-harness.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HARNESS_CLI = path.resolve(__dirname, '../scripts/demo-harness.mjs');

test('CLI --help exits 0 and prints usage', () => {
  const res = spawnSync(process.execPath, [HARNESS_CLI, '--help'], { encoding: 'utf8' });
  assert.equal(res.status, 0);
  assert.match(res.stdout, /--check-env/);
  assert.match(res.stdout, /--transcode/);
});

test('discoverEnvironment returns valid schema and finds available binaries offline', () => {
  const res = spawnSync(process.execPath, [HARNESS_CLI, '--check-env'], { encoding: 'utf8' });
  assert.equal(res.status, 0);
  const env = JSON.parse(res.stdout);
  assert.equal(env.node.valid, true);
  assert.equal(env.ready, true);
  assert.ok(Array.isArray(env.browsers));
  assert.ok(env.browsers.length > 0, 'expected at least one local browser binary');
  assert.equal(env.ffmpeg.available, true);
});

test('normalizeSegments merges overlapping intervals and filters short blips', () => {
  const merged = normalizeSegments([
    { start: 5.0, end: 5.2, speed: 1.75 }, // < 0.4s ignored
    { start: 2.0, end: 4.0, speed: 1.5 },
    { start: 3.8, end: 6.0, speed: 2.0 },
  ], 8.0);

  assert.equal(merged.length, 1);
  assert.deepEqual(merged[0], { start: 2.0, end: 6.0, speed: 2.0 });
});

test('buildSpeedRampFilter produces valid trim+setpts+concat filter graphs', () => {
  assert.equal(buildSpeedRampFilter([]), null);

  const single = buildSpeedRampFilter([{ start: 1.5, end: 3.5, speed: 1.75 }], 6.0);
  assert.match(single, /trim=start=0\.000:end=1\.500,setpts=PTS-STARTPTS\[v0\]/);
  assert.match(single, /trim=start=1\.500:end=3\.500,setpts=\(PTS-STARTPTS\)\/1\.750\[v1\]/);
  assert.match(single, /trim=start=3\.500,setpts=PTS-STARTPTS\[v2\]/);
  assert.match(single, /concat=n=3:v=1:a=0\[outv\]/);
});

test('transcodeVideo exports speed-ramped MP4 and two-pass GIF from synthetic WebM', () => {
  const env = discoverEnvironment();
  assert.equal(env.ffmpeg.available, true);

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rwd-transcode-'));
  try {
    const rawWebm = path.join(tmpDir, 'synthetic.webm');
    execFileSync(env.ffmpeg.path, [
      '-y', '-f', 'lavfi', '-i', 'testsrc=duration=3:size=640x360:rate=24',
      '-c:v', 'libvpx-vp9', rawWebm,
    ], { stdio: 'pipe' });

    const outMp4 = path.join(tmpDir, 'out.mp4');
    const outGif = path.join(tmpDir, 'out.gif');
    const results = transcodeVideo(rawWebm, [outMp4, outGif], {
      width: 640,
      segments: [{ start: 0.8, end: 2.2, speed: 1.75 }],
      ffmpegBin: env.ffmpeg.path,
    });

    assert.equal(results.length, 2);
    assert.ok(fs.statSync(outMp4).size > 1000);
    assert.ok(fs.statSync(outGif).size > 1000);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

async function withFixtureServer(fn) {
  const html = `<!doctype html>
<html>
<head><title>Demo Fixture</title></head>
<body style="font-family:sans-serif;padding:40px;background:#f8fafc;">
  <div id="card" style="max-width:420px;padding:24px;background:#fff;border-radius:12px;">
    <h2>Demo Sign In</h2>
    <input id="email" type="email" value="stale@example.com" style="display:block;width:100%;margin-bottom:12px;padding:8px;" />
    <button id="submit-btn" type="button" style="padding:10px 18px;cursor:pointer;">Continue</button>
    <p id="status"></p>
  </div>
  <script>
    document.getElementById('submit-btn').addEventListener('click', () => {
      document.getElementById('status').textContent = 'Signed in: ' + document.getElementById('email').value;
    });
  </script>
</body>
</html>`;

  const server = http.createServer((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  try {
    return await fn(`http://127.0.0.1:${port}/`);
  } finally {
    server.close();
  }
}

test('recordDemo end-to-end with auto driver (static-bar, zoom, locator, type, MP4+GIF, atomic cleanup)', async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rwd-e2e-pw-'));
  const stagingDir = path.join(tmpDir, '.temp');
  const outMp4 = path.join(tmpDir, 'walkthrough.mp4');
  const outGif = path.join(tmpDir, 'walkthrough.gif');

  try {
    const result = await withFixtureServer((url) => recordDemo({
      url,
      output: [outMp4, outGif],
      viewport: { width: 800, height: 450 },
      stepMode: 'static-bar',
      stagingDir,
    }, async (demo) => {
      await demo.showStep('Step 1: Enter account email');
      await demo.zoomTo('#card', 1.4);
      await demo.humanType('#email', 'alex@example.com');
      await demo.resetZoom();
      await demo.showStep('Step 2: Submit sign-in form', { mode: 'floating' });
      const btn = demo.page.getByRole ? demo.page.getByRole('button', { name: 'Continue' }) : '#submit-btn';
      await demo.withSpeedRamp(() => demo.moveAndClick(btn));
      const statusText = await demo.page.locator('#status').textContent();
      assert.equal(statusText, 'Signed in: alex@example.com');
      await demo.pause(350);
    }));

    assert.equal(result.outputs.length, 2);
    assert.ok(fs.statSync(outMp4).size > 1000);
    assert.ok(fs.statSync(outGif).size > 1000);
    assert.equal(fs.existsSync(stagingDir), false, 'stagingDir should be atomically removed');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('recordDemo works with zero-dep native-cdp driver when Playwright/Puppeteer are bypassed', async () => {
  const env = discoverEnvironment();
  if (!env.drivers.nativeCdp.available) return;

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rwd-e2e-cdp-'));
  const stagingDir = path.join(tmpDir, '.temp');
  const outMp4 = path.join(tmpDir, 'cdp-walkthrough.mp4');

  try {
    const result = await withFixtureServer((url) => recordDemo({
      url,
      output: outMp4,
      viewport: { width: 800, height: 450 },
      stepMode: 'static-bar',
      driver: 'native-cdp',
      stagingDir,
    }, async (demo) => {
      await demo.showStep('Step 1: Enter email via CDP');
      await demo.zoomTo('#card', 1.35);
      await demo.humanType('#email', 'cdp@example.com');
      await demo.resetZoom();
      await demo.moveAndClick('text=Continue');
      const statusText = await demo.page.evalFn(`document.getElementById('status').textContent`);
      assert.equal(statusText, 'Signed in: cdp@example.com');
      await demo.pause(400);
    }));

    assert.match(result.driver, /^native-cdp:/);
    assert.ok(fs.statSync(outMp4).size > 1000);
    assert.equal(fs.existsSync(stagingDir), false);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

