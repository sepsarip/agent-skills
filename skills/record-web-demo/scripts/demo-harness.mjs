#!/usr/bin/env node
/**
 * Multi-engine, offline-first web demo recording harness.
 * Discovers available browser runtimes (Playwright, Puppeteer, or zero-dep Chromium CDP),
 * system/cached browser binaries, and ffmpeg, then records humanized UI demos to MP4, WebM, or GIF.
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import crypto from 'node:crypto';
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const DEFAULT_VIEWPORT = { width: 1280, height: 720 };
const DEFAULT_STAGING_DIR = path.resolve('recordings/.temp');

function fileExists(targetPath) {
  try {
    return Boolean(targetPath) && fs.statSync(targetPath).isFile();
  } catch {
    return false;
  }
}

function dirExists(targetPath) {
  try {
    return Boolean(targetPath) && fs.statSync(targetPath).isDirectory();
  } catch {
    return false;
  }
}

function whichBinary(name) {
  const pathEnv = process.env.PATH || '';
  const exts = process.platform === 'win32' ? ['.exe', '.cmd', '.bat', ''] : [''];
  for (const dir of pathEnv.split(path.delimiter)) {
    if (!dir) continue;
    for (const ext of exts) {
      const candidate = path.join(dir, name + ext);
      if (fileExists(candidate)) return candidate;
    }
  }
  return null;
}

function getSearchNodeModulesRoots() {
  const roots = [];
  let cur = process.cwd();
  while (true) {
    roots.push(path.join(cur, 'node_modules'));
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  if (process.env.NODE_PATH) {
    for (const entry of process.env.NODE_PATH.split(path.delimiter)) {
      if (entry) roots.push(entry);
    }
  }
  // Common global npm prefixes relative to node binary
  const nodeBinDir = path.dirname(process.execPath);
  roots.push(path.resolve(nodeBinDir, '..', 'lib', 'node_modules'));
  roots.push(path.resolve(nodeBinDir, 'node_modules'));

  // Cached npx installs (offline reuse without triggering network downloads)
  const npxCache = path.join(os.homedir(), '.npm', '_npx');
  if (dirExists(npxCache)) {
    try {
      const entries = fs.readdirSync(npxCache)
        .map((d) => ({ path: path.join(npxCache, d, 'node_modules'), mtime: fs.statSync(path.join(npxCache, d)).mtimeMs }))
        .sort((a, b) => b.mtime - a.mtime);
      for (const e of entries) roots.push(e.path);
    } catch { /* ignore unreadable cache */ }
  }
  return [...new Set(roots.filter(dirExists))];
}

function findNodePackage(names) {
  for (const root of getSearchNodeModulesRoots()) {
    for (const pkgName of names) {
      const pkgDir = path.join(root, pkgName);
      const pkgJsonPath = path.join(pkgDir, 'package.json');
      if (!fileExists(pkgJsonPath)) continue;
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
        const entry = pkg.exports?.['.']?.import || pkg.exports?.['.']?.default || pkg.module || pkg.main || 'index.js';
        const resolvedEntry = path.resolve(pkgDir, typeof entry === 'string' ? entry : 'index.js');
        if (fileExists(resolvedEntry)) {
          return { name: pkgName, version: pkg.version || 'unknown', entryPath: resolvedEntry, root };
        }
      } catch { /* try next candidate */ }
    }
  }
  return null;
}

function getPlaywrightCacheDirs() {
  const dirs = [];
  if (process.env.PLAYWRIGHT_BROWSERS_PATH && process.env.PLAYWRIGHT_BROWSERS_PATH !== '0') {
    dirs.push(process.env.PLAYWRIGHT_BROWSERS_PATH);
  }
  // Scan current and parent dirs for local .venv*/ms-playwright caches
  for (const base of [process.cwd(), path.dirname(process.cwd())]) {
    try {
      for (const entry of fs.readdirSync(base)) {
        if (entry.startsWith('.venv')) {
          dirs.push(path.join(base, entry, 'ms-playwright'));
        }
      }
    } catch { /* ignore */ }
  }
  dirs.push(path.join(os.homedir(), '.cache', 'ms-playwright'));
  if (process.platform === 'darwin') {
    dirs.push(path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright'));
  } else if (process.platform === 'win32' && process.env.LOCALAPPDATA) {
    dirs.push(path.join(process.env.LOCALAPPDATA, 'ms-playwright'));
  }
  return [...new Set(dirs.filter(dirExists))];
}

function findFirstMatchingFile(dir, matchFn, maxDepth = 3) {
  if (maxDepth < 0 || !dirExists(dir)) return null;
  let entries = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return null;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isFile() && matchFn(entry.name, full)) return full;
  }
  for (const entry of entries) {
    if (entry.isDirectory()) {
      const found = findFirstMatchingFile(path.join(dir, entry.name), matchFn, maxDepth - 1);
      if (found) return found;
    }
  }
  return null;
}

function findBrowsers() {
  const found = [];
  const seen = new Set();
  const add = (kind, browserPath, source, engine) => {
    if (!fileExists(browserPath)) return;
    let real = browserPath;
    try { real = fs.realpathSync(browserPath); } catch { /* keep raw */ }
    if (seen.has(real)) return;
    seen.add(real);
    found.push({ kind, path: browserPath, realPath: real, source, engine });
  };

  for (const envKey of ['DEMO_BROWSER_PATH', 'CHROME_BIN', 'PUPPETEER_EXECUTABLE_PATH', 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']) {
    if (process.env[envKey]) add('custom-chromium', process.env[envKey], `env:${envKey}`, 'chromium');
  }

  // Scan Playwright caches (prefer headless-shell and chromium first for sandbox resilience)
  for (const cacheDir of getPlaywrightCacheDirs()) {
    let entries = [];
    try { entries = fs.readdirSync(cacheDir).sort().reverse(); } catch { continue; }
    for (const dirName of entries) {
      const subDir = path.join(cacheDir, dirName);
      if (dirName.startsWith('chromium_headless_shell-')) {
        const bin = findFirstMatchingFile(subDir, (n) => n === 'chrome-headless-shell' || n === 'chrome-headless-shell.exe');
        if (bin) add('chromium-headless-shell', bin, `cache:${cacheDir}`, 'chromium');
      } else if (dirName.startsWith('chromium-')) {
        const bin = findFirstMatchingFile(subDir, (n) => n === 'chrome' || n === 'chrome.exe' || n === 'Google Chrome for Testing');
        if (bin) add('playwright-chromium', bin, `cache:${cacheDir}`, 'chromium');
      } else if (dirName.startsWith('firefox-')) {
        const bin = findFirstMatchingFile(subDir, (n) => n === 'firefox' || n === 'firefox.exe');
        if (bin) add('playwright-firefox', bin, `cache:${cacheDir}`, 'firefox');
      } else if (dirName.startsWith('webkit-')) {
        const bin = findFirstMatchingFile(subDir, (n) => n === 'pw_run.sh' || n === 'MiniBrowser');
        if (bin) add('playwright-webkit', bin, `cache:${cacheDir}`, 'webkit');
      }
    }
  }

  // System browsers
  const sysBins = [
    ['google-chrome', 'chromium'],
    ['google-chrome-stable', 'chromium'],
    ['chromium', 'chromium'],
    ['chromium-browser', 'chromium'],
    ['brave-browser', 'chromium'],
    ['microsoft-edge', 'chromium'],
    ['msedge', 'chromium'],
    ['firefox', 'firefox'],
  ];
  for (const [name, engine] of sysBins) {
    const p = whichBinary(name);
    if (p) add(`system-${name}`, p, 'PATH', engine);
  }

  const fixedPaths = [
    ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', 'system-chrome', 'chromium'],
    ['/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', 'system-edge', 'chromium'],
    ['/Applications/Brave Browser.app/Contents/MacOS/Brave Browser', 'system-brave', 'chromium'],
    ['/snap/bin/chromium', 'system-chromium', 'chromium'],
  ];
  for (const [p, kind, engine] of fixedPaths) add(kind, p, 'os-default', engine);

  return found;
}

function findFfmpeg() {
  if (fileExists(process.env.DEMO_FFMPEG_PATH)) {
    return { available: true, path: process.env.DEMO_FFMPEG_PATH, source: 'env:DEMO_FFMPEG_PATH' };
  }
  const sys = whichBinary('ffmpeg');
  if (sys) return { available: true, path: sys, source: 'PATH' };
  for (const cacheDir of getPlaywrightCacheDirs()) {
    try {
      for (const entry of fs.readdirSync(cacheDir).sort().reverse()) {
        if (!entry.startsWith('ffmpeg-')) continue;
        const bin = findFirstMatchingFile(path.join(cacheDir, entry), (n) => n.startsWith('ffmpeg'));
        if (bin) return { available: true, path: bin, source: `cache:${cacheDir}` };
      }
    } catch { /* ignore */ }
  }
  return { available: false, path: null, source: null };
}

function findPythonPlaywright() {
  const candidates = [];
  for (const base of [process.cwd(), path.dirname(process.cwd())]) {
    try {
      for (const entry of fs.readdirSync(base)) {
        if (entry.startsWith('.venv')) {
          const py = path.join(base, entry, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3');
          if (fileExists(py)) candidates.push(py);
        }
      }
    } catch { /* ignore */ }
  }
  const sysPy = whichBinary('python3');
  if (sysPy) candidates.push(sysPy);

  for (const py of [...new Set(candidates)]) {
    const res = spawnSync(py, ['-c', 'import importlib.util,sys;sys.exit(0 if importlib.util.find_spec("playwright") else 1)'], { timeout: 2500 });
    if (res.status === 0) return { available: true, pythonPath: py };
  }
  return { available: false, pythonPath: null };
}

function isPlaywrightBrowser(b) {
  return b.engine === 'chromium' || b.kind === 'playwright-firefox' || b.kind === 'playwright-webkit';
}

export function discoverEnvironment() {
  const nodeMajor = Number(process.versions.node.split('.')[0]);
  const playwright = findNodePackage(['playwright', 'playwright-core']);
  const puppeteer = findNodePackage(['puppeteer', 'puppeteer-core']);
  const browsers = findBrowsers();
  const ffmpeg = findFfmpeg();
  const pythonPlaywright = findPythonPlaywright();
  const hasChromium = browsers.some((b) => b.engine === 'chromium');
  const hasPwBrowser = browsers.some(isPlaywrightBrowser);

  let recommendedDriver = null;
  if (playwright && hasPwBrowser) recommendedDriver = 'playwright';
  else if (puppeteer && (hasChromium || browsers.some((b) => b.engine === 'firefox'))) recommendedDriver = 'puppeteer';
  else if (hasChromium && ffmpeg.available) recommendedDriver = 'native-cdp';

  return {
    ready: Boolean(recommendedDriver) && nodeMajor >= 18,
    node: { version: process.version, valid: nodeMajor >= 18 },
    recommendedDriver,
    drivers: {
      playwright: playwright ? { available: true, ...playwright } : { available: false },
      puppeteer: puppeteer ? { available: true, ...puppeteer } : { available: false },
      nativeCdp: { available: hasChromium && ffmpeg.available, detail: hasChromium && ffmpeg.available ? 'Zero-dep Chromium CDP + ffmpeg screencast' : 'Needs any Chromium binary + ffmpeg' },
      pythonPlaywright,
    },
    browsers,
    ffmpeg,
    capabilities: {
      webm: Boolean((playwright && hasPwBrowser) || (recommendedDriver && ffmpeg.available)),
      mp4: Boolean(recommendedDriver && ffmpeg.available),
      gif: Boolean(recommendedDriver && ffmpeg.available),
    },
  };
}

// --- FFmpeg Timeline & Transcoding ---

export function normalizeSegments(segments = [], maxDurationSec = null) {
  const cleaned = segments
    .map((s) => ({
      start: Math.max(0, Number(s.start) || 0),
      end: Number(s.end) || 0,
      speed: Math.min(4, Math.max(1.1, Number(s.speed) || 1.75)),
    }))
    .map((s) => (maxDurationSec != null ? { ...s, end: Math.min(s.end, maxDurationSec) } : s))
    .filter((s) => s.end - s.start >= 0.4)
    .sort((a, b) => a.start - b.start);

  const merged = [];
  for (const seg of cleaned) {
    const prev = merged[merged.length - 1];
    if (prev && seg.start <= prev.end + 0.05) {
      prev.end = Math.max(prev.end, seg.end);
      prev.speed = Math.max(prev.speed, seg.speed);
    } else {
      merged.push({ ...seg });
    }
  }
  return merged;
}

export function buildSpeedRampFilter(segments = [], totalDurationSec = null) {
  const normalized = normalizeSegments(segments, totalDurationSec);
  if (normalized.length === 0) return null;

  const parts = [];
  let cursor = 0;
  let idx = 0;
  const labels = [];

  for (const seg of normalized) {
    if (seg.start - cursor >= 0.05) {
      const label = `v${idx++}`;
      parts.push(`[0:v]trim=start=${cursor.toFixed(3)}:end=${seg.start.toFixed(3)},setpts=PTS-STARTPTS[${label}]`);
      labels.push(`[${label}]`);
    }
    const fastLabel = `v${idx++}`;
    parts.push(`[0:v]trim=start=${seg.start.toFixed(3)}:end=${seg.end.toFixed(3)},setpts=(PTS-STARTPTS)/${seg.speed.toFixed(3)}[${fastLabel}]`);
    labels.push(`[${fastLabel}]`);
    cursor = seg.end;
  }

  if (totalDurationSec == null || totalDurationSec - cursor >= 0.05) {
    const tailLabel = `v${idx++}`;
    parts.push(`[0:v]trim=start=${cursor.toFixed(3)},setpts=PTS-STARTPTS[${tailLabel}]`);
    labels.push(`[${tailLabel}]`);
  }

  if (labels.length === 1) {
    return `${parts[0].replace(/\[v\d+\]$/, '[outv]')}`;
  }
  return `${parts.join(';')};${labels.join('')}concat=n=${labels.length}:v=1:a=0[outv]`;
}

export function probeDuration(ffmpegBin, inputPath) {
  const ffprobe = ffmpegBin.replace(/ffmpeg(\.exe)?$/, 'ffprobe$1');
  if (fileExists(ffprobe)) {
    const res = spawnSync(ffprobe, ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', inputPath], { encoding: 'utf8' });
    const parsed = parseFloat((res.stdout || '').trim());
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  const res = spawnSync(ffmpegBin, ['-i', inputPath], { encoding: 'utf8' });
  const m = (res.stderr || '').match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);
  if (!m) return null;
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}

export function transcodeVideo(inputPath, outputs, { segments = [], width = 1280, gifFps = 15, ffmpegBin = null } = {}) {
  const outputList = (Array.isArray(outputs) ? outputs : [outputs]).filter(Boolean);
  const ffmpeg = ffmpegBin || findFfmpeg().path;
  const duration = (ffmpeg && segments.length > 0) ? probeDuration(ffmpeg, inputPath) : null;
  const speedFilter = buildSpeedRampFilter(segments, duration);
  const results = [];

  for (const rawOut of outputList) {
    const outPath = path.resolve(rawOut);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    const ext = path.extname(outPath).toLowerCase();

    if (ext === '.webm' && !speedFilter && path.extname(inputPath).toLowerCase() === '.webm') {
      fs.copyFileSync(inputPath, outPath);
    } else {
      if (!ffmpeg) {
        throw new Error(`ffmpeg is required to export ${ext} (${outPath})`);
      }
      const args = ['-y', '-i', inputPath];
      if (ext === '.gif') {
        const gifChain = `fps=${gifFps},scale=${width}:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3`;
        const filter = speedFilter ? `${speedFilter};[outv]${gifChain}[gifv]` : `[0:v]${gifChain}[gifv]`;
        args.push('-filter_complex', filter, '-map', '[gifv]', outPath);
      } else if (ext === '.mp4') {
        if (speedFilter) {
          args.push('-filter_complex', `${speedFilter};[outv]fps=30[mp4v]`, '-map', '[mp4v]');
        } else {
          args.push('-vf', 'fps=30');
        }
        args.push('-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', outPath);
      } else if (ext === '.webm') {
        if (speedFilter) {
          args.push('-filter_complex', speedFilter, '-map', '[outv]');
        }
        args.push('-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0', outPath);
      } else {
        throw new Error(`Unsupported output format: ${ext}. Use .mp4, .webm, or .gif`);
      }
      execFileSync(ffmpeg, args, { stdio: 'pipe' });
    }

    const stat = fs.statSync(outPath);
    if (!stat.size) throw new Error(`Generated output is empty: ${outPath}`);
    results.push({ path: outPath, bytes: stat.size });
  }
  return results;
}

// --- Browser DOM Overlay (Tabler Icons MIT + Click Ripple + Dual-Mode Step Overlay) ---

const OVERLAY_INIT_SCRIPT = `(() => {
  if (window.__demoOverlayInstalled) return;
  window.__demoOverlayInstalled = true;

  const BAR_HEIGHT = 52;
  const ICONS = {
    default: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="#ffffff" stroke="#111827" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="filter:drop-shadow(0 0 1px #fff) drop-shadow(0 2px 3px rgba(0,0,0,0.4));margin-left:-4px;margin-top:-4px;"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7.904 17.563a1.2 1.2 0 0 0 2.228 .308l2.09 -3.093l4.907 4.907a1.067 1.067 0 0 0 1.509 0l1.047 -1.047a1.067 1.067 0 0 0 0 -1.509l-4.907 -4.907l3.113 -2.09a1.2 1.2 0 0 0 -.309 -2.228l-13.582 -3.904l3.904 13.563"/></svg>',
    pointer: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="#ffffff" stroke="#111827" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="filter:drop-shadow(0 0 1px #fff) drop-shadow(0 2px 3px rgba(0,0,0,0.4));margin-left:-9.5px;margin-top:-3px;"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M8 13v-8.5a1.5 1.5 0 0 1 3 0v7.5"/><path d="M11 11.5v-2a1.5 1.5 0 1 1 3 0v2.5"/><path d="M14 10.5a1.5 1.5 0 0 1 3 0v1.5"/><path d="M17 11.5a1.5 1.5 0 0 1 3 0v4.5a6 6 0 0 1 -6 6h-2h.208a6 6 0 0 1 -5.012 -2.7a69.74 69.74 0 0 1 -.196 -.3c-.312 -.479 -1.407 -2.388 -3.286 -5.728a1.5 1.5 0 0 1 .536 -2.022a1.867 1.867 0 0 1 2.28 .28l1.47 1.47"/></svg>',
    text: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#111827" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="filter:drop-shadow(0 0 1.5px #fff) drop-shadow(0 2px 3px rgba(0,0,0,0.4));margin-left:-12px;margin-top:-12px;"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M10 12h4"/><path d="M9 4a3 3 0 0 1 3 3v10a3 3 0 0 1 -3 3"/><path d="M15 4a3 3 0 0 0 -3 3v10a3 3 0 0 0 3 3"/></svg>'
  };

  window.__applyBaseStage = (animate = true) => {
    if (!document.body) return;
    const stepMode = sessionStorage.getItem('__demoStepMode');
    const hasBar = stepMode === 'static-bar';
    document.body.style.transformOrigin = '0 0';
    document.body.style.transition = animate ? 'transform 0.48s cubic-bezier(0.22, 1, 0.36, 1)' : 'none';
    document.body.style.willChange = 'transform';

    if (hasBar) {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const baseScale = Number(((vh - BAR_HEIGHT - 8) / vh).toFixed(4));
      const tx = Math.round((vw * (1 - baseScale)) / 2);
      const ty = 4;
      const bodyBg = window.getComputedStyle(document.body).backgroundColor;
      const htmlBg = window.getComputedStyle(document.documentElement).backgroundColor;
      if (!bodyBg || bodyBg === 'rgba(0, 0, 0, 0)' || bodyBg === 'transparent') {
        document.body.style.backgroundColor = (htmlBg && htmlBg !== 'rgba(0, 0, 0, 0)' && htmlBg !== 'transparent' && htmlBg !== 'rgb(15, 23, 42)') ? htmlBg : '#ffffff';
      }
      document.documentElement.style.backgroundColor = '#0f172a';
      document.body.style.borderRadius = '8px';
      document.body.style.boxShadow = '0 8px 28px rgba(0, 0, 0, 0.45)';
      window.__demoCamera = { scale: baseScale, tx, ty, barHeight: BAR_HEIGHT };
      document.body.style.transform = \`translate(\${tx}px, \${ty}px) scale(\${baseScale})\`;
    } else {
      document.body.style.borderRadius = '';
      document.body.style.boxShadow = '';
      window.__demoCamera = { scale: 1, tx: 0, ty: 0, barHeight: 0 };
      document.body.style.transform = 'translate(0px, 0px) scale(1)';
    }
    if (!animate) {
      requestAnimationFrame(() => {
        if (document.body) document.body.style.transition = 'transform 0.48s cubic-bezier(0.22, 1, 0.36, 1)';
      });
    }
  };

  window.__zoomElement = (el, targetScale = 1.65) => {
    if (!el || !document.body) return;
    const cam = window.__demoCamera || { scale: 1, tx: 0, ty: 0, barHeight: 0 };
    const rect = el.getBoundingClientRect();
    const cx0 = (rect.left + rect.width / 2 - cam.tx) / cam.scale;
    const cy0 = (rect.top + rect.height / 2 - cam.ty) / cam.scale;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const barH = cam.barHeight || (sessionStorage.getItem('__demoStepMode') === 'static-bar' ? BAR_HEIGHT : 0);
    const stageH = vh - barH;
    const rawTx = vw / 2 - cx0 * targetScale;
    const rawTy = stageH / 2 - cy0 * targetScale;
    const tx = Math.max(vw * (1 - targetScale), Math.min(0, rawTx));
    const ty = Math.max(stageH - vh * targetScale, Math.min(0, rawTy));
    window.__demoCamera = { scale: targetScale, tx, ty, barHeight: barH };
    document.body.style.transform = \`translate(\${tx}px, \${ty}px) scale(\${targetScale})\`;
  };

  window.__checkBadgeCollision = (cx, cy) => {
    if (sessionStorage.getItem('__demoStepMode') !== 'floating') return;
    const badge = document.getElementById('demo-step-badge');
    if (!badge || badge.style.opacity === '0') return;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem('__demoCursor') || 'null'); } catch {}
    const curX = cx ?? saved?.x ?? vw / 2;
    const curY = cy ?? saved?.y ?? vh / 2;
    const slots = [
      { name: 'bottom-center', x: vw / 2, y: vh - 44, top: 'auto', bottom: '28px', left: '50%', right: 'auto', transform: 'translateX(-50%)' },
      { name: 'top-right', x: vw - 160, y: 42, top: '20px', bottom: 'auto', left: 'auto', right: '24px', transform: 'translateY(0)' },
      { name: 'bottom-right', x: vw - 160, y: vh - 44, top: 'auto', bottom: '28px', left: 'auto', right: '24px', transform: 'translateY(0)' },
      { name: 'top-center', x: vw / 2, y: 42, top: '20px', bottom: 'auto', left: '50%', right: 'auto', transform: 'translateX(-50%)' }
    ];
    const isBusy = (s) => {
      if (Math.abs(curX - s.x) < 210 && Math.abs(curY - s.y) < 64) return true;
      for (const dx of [-80, 0, 80]) {
        for (const el of document.elementsFromPoint(s.x + dx, s.y)) {
          if (el.id === 'demo-step-badge' || el.id === 'demo-cursor') continue;
          if (el.closest('button, a, input, select, textarea, [role="button"], [role="tab"]')) return true;
        }
      }
      return false;
    };
    const chosen = slots.find((s) => !isBusy(s)) || slots[0];
    if (badge.dataset.dock !== chosen.name) {
      badge.dataset.dock = chosen.name;
      badge.style.top = chosen.top;
      badge.style.bottom = chosen.bottom;
      badge.style.left = chosen.left;
      badge.style.right = chosen.right;
      badge.style.transform = chosen.transform;
    }
  };

  window.__renderStepBadge = (text, mode = 'static-bar') => {
    if (mode === 'floating') {
      const existingBar = document.getElementById('demo-step-bar');
      if (existingBar) existingBar.style.display = 'none';
      let badge = document.getElementById('demo-step-badge');
      if (!badge || badge.parentElement?.id === 'demo-step-bar') {
        if (badge) badge.remove();
        badge = document.createElement('div');
        badge.id = 'demo-step-badge';
        badge.style.cssText = 'position:fixed;bottom:28px;left:50%;transform:translateX(-50%);padding:8px 18px;background:rgba(17,24,39,0.88);color:#f9fafb;border:1px solid rgba(255,255,255,0.18);border-radius:9999px;font:600 14px/1.4 system-ui,-apple-system,sans-serif;letter-spacing:0.01em;box-shadow:0 8px 24px rgba(0,0,0,0.35);backdrop-filter:blur(8px);pointer-events:none;z-index:999998;opacity:0;transition:opacity 0.25s ease,transform 0.25s ease,top 0.25s ease,bottom 0.25s ease,left 0.25s ease,right 0.25s ease;';
        document.documentElement.appendChild(badge);
      }
      badge.textContent = text;
      badge.style.opacity = '1';
      window.__checkBadgeCollision();
      return;
    }
    let bar = document.getElementById('demo-step-bar');
    let badge = document.getElementById('demo-step-badge');
    if (!bar) {
      if (badge) badge.remove();
      bar = document.createElement('div');
      bar.id = 'demo-step-bar';
      bar.style.cssText = \`position:fixed;left:0;right:0;bottom:0;height:\${BAR_HEIGHT}px;background:#0f172a;border-top:1px solid rgba(255,255,255,0.12);display:flex;align-items:center;justify-content:center;pointer-events:none;z-index:999998;\`;
      badge = document.createElement('div');
      badge.id = 'demo-step-badge';
      badge.style.cssText = 'padding:6px 18px;background:rgba(30,41,59,0.95);color:#f8fafc;border:1px solid rgba(255,255,255,0.18);border-radius:9999px;font:600 14px/1.4 system-ui,-apple-system,sans-serif;letter-spacing:0.01em;box-shadow:0 4px 14px rgba(0,0,0,0.3);transition:opacity 0.2s ease;';
      bar.appendChild(badge);
      document.documentElement.appendChild(bar);
    }
    bar.style.display = 'flex';
    badge.textContent = text;
    badge.style.opacity = '1';
  };

  function spawnClickRipple(x, y) {
    const ring = document.createElement('div');
    ring.className = 'demo-click-ripple';
    ring.style.cssText = \`position:fixed;left:\${x}px;top:\${y}px;width:14px;height:14px;margin-left:-7px;margin-top:-7px;border-radius:9999px;border:2px solid rgba(59,130,246,0.9);background:rgba(59,130,246,0.22);pointer-events:none;z-index:999997;transform:scale(0.6);opacity:0.95;transition:transform 0.36s cubic-bezier(0.22,1,0.36,1),opacity 0.36s ease-out;\`;
    document.documentElement.appendChild(ring);
    requestAnimationFrame(() => {
      ring.style.transform = 'scale(2.8)';
      ring.style.opacity = '0';
    });
    setTimeout(() => ring.remove(), 400);
  }

  const initOverlays = () => {
    if (!document.body) return;
    window.__applyBaseStage(false);
    let savedCursor = null;
    try { savedCursor = JSON.parse(sessionStorage.getItem('__demoCursor') || 'null'); } catch {}
    const startX = savedCursor?.x ?? Math.round(window.innerWidth / 2);
    const startY = savedCursor?.y ?? Math.round(window.innerHeight / 2);
    let currentState = savedCursor?.state || 'default';

    let cursor = document.getElementById('demo-cursor');
    if (!cursor) {
      cursor = document.createElement('div');
      cursor.id = 'demo-cursor';
      cursor.style.cssText = \`position:fixed;top:\${startY}px;left:\${startX}px;pointer-events:none;z-index:999999;transform-origin:0 0;transform:scale(1);transition:transform 0.06s ease;will-change:left,top,transform;\`;
      cursor.innerHTML = ICONS[currentState] || ICONS.default;
      document.documentElement.appendChild(cursor);
    }

    const savedStep = sessionStorage.getItem('__demoStep');
    const savedMode = sessionStorage.getItem('__demoStepMode') || 'static-bar';
    if (savedStep) window.__renderStepBadge(savedStep, savedMode);

    window.addEventListener('mousemove', (e) => {
      cursor.style.left = \`\${e.clientX}px\`;
      cursor.style.top = \`\${e.clientY}px\`;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (el) {
        const comp = window.getComputedStyle(el).cursor;
        let next = 'default';
        if (comp === 'pointer' || el.closest('button,a,[role="button"],input[type="submit"],input[type="checkbox"],input[type="radio"]')) next = 'pointer';
        else if (comp === 'text' || el.closest('input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]),textarea,[contenteditable="true"]')) next = 'text';
        if (next !== currentState) {
          currentState = next;
          cursor.innerHTML = ICONS[next];
        }
      }
      try { sessionStorage.setItem('__demoCursor', JSON.stringify({ x: e.clientX, y: e.clientY, state: currentState })); } catch {}
      window.__checkBadgeCollision(e.clientX, e.clientY);
    });

    window.addEventListener('mousedown', (e) => {
      cursor.style.transform = 'scale(0.85)';
      spawnClickRipple(e.clientX, e.clientY);
    });
    window.addEventListener('mouseup', () => { cursor.style.transform = 'scale(1)'; });
  };

  if (document.readyState === 'loading') window.addEventListener('DOMContentLoaded', initOverlays);
  else initOverlays();
})();`;

// --- Shared Eased Cursor & DemoSession API ---

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function buildCursorPath(from, to, stepsOverride = null) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dist = Math.hypot(dx, dy);
  const steps = stepsOverride ?? Math.max(12, Math.min(34, Math.round(dist / 22)));
  const arc = Math.min(18, dist * 0.04) * (dx >= 0 ? -1 : 1);
  const points = [];
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const eased = easeInOutCubic(t);
    const arcOffset = Math.sin(Math.PI * t) * arc;
    points.push({
      x: Math.round((from.x + dx * eased) * 10) / 10,
      y: Math.round((from.y + dy * eased + arcOffset) * 10) / 10,
    });
  }
  return points;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function createDemoSession(adapter, options) {
  const fastSegments = [];
  const cursorPos = { x: options.viewport.width / 2, y: options.viewport.height / 2 };
  let startMs = Date.now();

  async function moveToPoint(x, y, steps) {
    for (const pt of buildCursorPath(cursorPos, { x, y }, steps)) {
      await adapter.mouseMove(pt.x, pt.y);
      await wait(12);
    }
    cursorPos.x = x;
    cursorPos.y = y;
  }

  return {
    page: adapter.page,
    driver: adapter.driverName,
    fastSegments,
    markStart() { startMs = Date.now(); },
    async goto(url, waitUntil = 'domcontentloaded') {
      await adapter.goto(url, waitUntil);
    },
    async pause(ms = 800) {
      await wait(ms);
    },
    async moveAndClick(target, { steps = null, holdMs = 90 } = {}) {
      const box = await adapter.resolveBox(target);
      await moveToPoint(box.x + box.width / 2, box.y + box.height / 2, steps);
      await wait(110);
      await adapter.mouseDown();
      await wait(holdMs);
      await adapter.mouseUp();
    },
    async humanType(target, text, { clear = true, delay = null } = {}) {
      await this.moveAndClick(target);
      if (clear) await adapter.clearActiveIfNeeded(target);
      const charDelay = delay ?? (text.length > 15 ? 42 : 85);
      await adapter.typeSequentially(target, text, charDelay);
    },
    async zoomTo(target, scale = 1.65) {
      await adapter.zoomTo(target, scale);
      await wait(520);
      await adapter.checkBadgeCollision();
    },
    async resetZoom() {
      await adapter.resetZoom();
      await wait(520);
      await adapter.checkBadgeCollision();
    },
    async showStep(text, { mode = options.stepMode || 'static-bar' } = {}) {
      if (mode === 'off') return;
      await adapter.showStep(text, mode);
      await wait(300);
    },
    async hideStep() {
      await adapter.hideStep();
    },
    async withSpeedRamp(fn, speed = 1.75) {
      const start = (Date.now() - startMs) / 1000;
      const result = await fn();
      const end = (Date.now() - startMs) / 1000;
      if (end - start >= 0.6) {
        fastSegments.push({ start: Number(start.toFixed(2)), end: Number(end.toFixed(2)), speed });
      }
      return result;
    },
  };
}

// --- Driver 1: Playwright (Node) ---

async function launchPlaywrightBrowser(pwModule, browsers, explicitExec) {
  const candidates = explicitExec
    ? [{ path: explicitExec, engine: 'chromium', kind: 'explicit' }]
    : browsers.filter(isPlaywrightBrowser);

  const tried = [];
  for (const b of candidates) {
    const type = pwModule[b.engine];
    if (!type) continue;
    const isChromium = b.engine === 'chromium';
    const argSets = isChromium ? [[], ['--no-sandbox', '--disable-dev-shm-usage']] : [[]];
    for (const args of argSets) {
      try {
        const browser = await type.launch({ executablePath: b.path, headless: true, args });
        return { browser, browserUsed: b };
      } catch (err) {
        tried.push(`${b.kind} (${args.join(' ') || 'default'}): ${err.message.split('\n')[0]}`);
      }
    }
  }
  throw new Error(`No discovered browser could launch via Playwright:\n  ${tried.join('\n  ')}`);
}

async function runWithPlaywright(env, options, scenarioFn, stagingDir) {
  const pw = await import(pathToFileURL(env.drivers.playwright.entryPath).href);
  const { browser, browserUsed } = await launchPlaywrightBrowser(pw, env.browsers, options.executablePath);
  const context = await browser.newContext({
    viewport: options.viewport,
    recordVideo: { dir: stagingDir, size: options.viewport },
  });
  let videoPath = null;
  try {
    const page = await context.newPage();
    await page.addInitScript(OVERLAY_INIT_SCRIPT);
    await page.mouse.move(options.viewport.width / 2, options.viewport.height / 2);

    const resolveLoc = (t) => (typeof t === 'string' ? page.locator(t).first() : t.first());
    const adapter = {
      driverName: `playwright:${browserUsed.kind}`,
      page,
      goto: (url, waitUntil) => page.goto(url, { waitUntil }),
      mouseMove: (x, y) => page.mouse.move(x, y),
      mouseDown: () => page.mouse.down(),
      mouseUp: () => page.mouse.up(),
      resolveBox: async (target) => {
        const loc = resolveLoc(target);
        await loc.waitFor({ state: 'visible' });
        await loc.scrollIntoViewIfNeeded();
        const box = await loc.boundingBox();
        if (!box) throw new Error(`Element has no bounding box: ${target}`);
        return box;
      },
      clearActiveIfNeeded: async (target) => {
        const loc = resolveLoc(target);
        const hasText = await loc.evaluate((el) => Boolean('value' in el ? el.value : el.textContent?.trim()));
        if (hasText) {
          const mod = process.platform === 'darwin' ? 'Meta' : 'Control';
          await page.keyboard.press(`${mod}+a`);
          await page.keyboard.press('Backspace');
        }
      },
      typeSequentially: async (target, text, delay) => {
        await resolveLoc(target).pressSequentially(text, { delay });
      },
      zoomTo: async (target, scale) => {
        const loc = resolveLoc(target);
        await loc.waitFor({ state: 'visible' });
        await loc.evaluate((el, s) => window.__zoomElement && window.__zoomElement(el, s), scale);
      },
      resetZoom: () => page.evaluate(() => window.__applyBaseStage && window.__applyBaseStage(true)),
      checkBadgeCollision: () => page.evaluate(() => window.__checkBadgeCollision && window.__checkBadgeCollision()),
      showStep: async (text, mode) => {
        await page.waitForLoadState('domcontentloaded');
        await page.evaluate(({ t, m }) => {
          const prev = sessionStorage.getItem('__demoStepMode');
          try {
            sessionStorage.setItem('__demoStepMode', m);
            sessionStorage.setItem('__demoStep', t);
          } catch {}
          if (prev !== m && window.__applyBaseStage) window.__applyBaseStage(false);
          if (window.__renderStepBadge) window.__renderStepBadge(t, m);
        }, { t: text, m: mode });
      },
      hideStep: () => page.evaluate(() => {
        try { sessionStorage.removeItem('__demoStep'); } catch {}
        const badge = document.getElementById('demo-step-badge');
        if (badge) badge.style.opacity = '0';
      }),
    };

    const session = createDemoSession(adapter, options);
    if (options.url) await session.goto(options.url);
    session.markStart();
    await scenarioFn(session);

    videoPath = await page.video().path();
    await context.close();
    await browser.close();
    return { rawVideoPath: videoPath, fastSegments: session.fastSegments, driver: adapter.driverName };
  } catch (err) {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
    throw err;
  }
}

// --- Driver 2: Puppeteer (Node) ---

async function runWithPuppeteer(env, options, scenarioFn, stagingDir) {
  const mod = await import(pathToFileURL(env.drivers.puppeteer.entryPath).href);
  const puppeteer = mod.default || mod;
  const chromiumBrowsers = env.browsers.filter((b) => b.engine === 'chromium');
  const execPath = options.executablePath || chromiumBrowsers[0]?.path;
  if (!execPath) throw new Error('Puppeteer driver requires a Chromium binary.');

  let browser;
  try {
    browser = await puppeteer.launch({ executablePath: execPath, headless: true, defaultViewport: options.viewport });
  } catch {
    browser = await puppeteer.launch({ executablePath: execPath, headless: true, defaultViewport: options.viewport, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  }

  const rawVideoPath = path.join(stagingDir, `pptr-${Date.now()}.webm`);
  let recorder = null;
  try {
    const page = await browser.newPage();
    await page.evaluateOnNewDocument(OVERLAY_INIT_SCRIPT);
    await page.mouse.move(options.viewport.width / 2, options.viewport.height / 2);

    const adapter = {
      driverName: 'puppeteer',
      page,
      goto: (url, waitUntil) => page.goto(url, { waitUntil }),
      mouseMove: (x, y) => page.mouse.move(x, y),
      mouseDown: () => page.mouse.down(),
      mouseUp: () => page.mouse.up(),
      resolveBox: async (sel) => {
        await page.waitForSelector(sel, { visible: true });
        await page.$eval(sel, (el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
        const el = await page.$(sel);
        const box = await el.boundingBox();
        if (!box) throw new Error(`Element not visible: ${sel}`);
        return box;
      },
      clearActiveIfNeeded: async (sel) => {
        const hasText = await page.$eval(sel, (el) => Boolean('value' in el ? el.value : el.textContent?.trim()));
        if (hasText) {
          const modKey = process.platform === 'darwin' ? 'Meta' : 'Control';
          await page.keyboard.down(modKey);
          await page.keyboard.press('KeyA');
          await page.keyboard.up(modKey);
          await page.keyboard.press('Backspace');
        }
      },
      typeSequentially: (_sel, text, delay) => page.keyboard.type(text, { delay }),
      zoomTo: (sel, scale) => page.$eval(sel, (el, s) => window.__zoomElement && window.__zoomElement(el, s), scale),
      resetZoom: () => page.evaluate(() => window.__applyBaseStage && window.__applyBaseStage(true)),
      checkBadgeCollision: () => page.evaluate(() => window.__checkBadgeCollision && window.__checkBadgeCollision()),
      showStep: (text, mode) => page.evaluate(({ t, m }) => {
        const prev = sessionStorage.getItem('__demoStepMode');
        try { sessionStorage.setItem('__demoStepMode', m); sessionStorage.setItem('__demoStep', t); } catch {}
        if (prev !== m && window.__applyBaseStage) window.__applyBaseStage(false);
        if (window.__renderStepBadge) window.__renderStepBadge(t, m);
      }, { t: text, m: mode }),
      hideStep: () => page.evaluate(() => {
        try { sessionStorage.removeItem('__demoStep'); } catch {}
        const b = document.getElementById('demo-step-badge');
        if (b) b.style.opacity = '0';
      }),
    };

    const session = createDemoSession(adapter, options);
    if (options.url) await session.goto(options.url);
    recorder = await page.screencast({ path: rawVideoPath });
    session.markStart();
    await scenarioFn(session);
    await recorder.stop();
    await browser.close();
    return { rawVideoPath, fastSegments: session.fastSegments, driver: 'puppeteer' };
  } catch (err) {
    if (recorder) await recorder.stop().catch(() => {});
    await browser.close().catch(() => {});
    throw err;
  }
}

// --- Driver 3: Zero-Dependency Native Chromium CDP + FFmpeg Frame Stitcher ---

function openWsClient(wsUrl) {
  return new Promise((resolve, reject) => {
    const u = new URL(wsUrl);
    const key = crypto.randomBytes(16).toString('base64');
    const req = http.request({
      host: u.hostname,
      port: Number(u.port),
      path: u.pathname + u.search,
      headers: {
        Connection: 'Upgrade',
        Upgrade: 'websocket',
        'Sec-WebSocket-Key': key,
        'Sec-WebSocket-Version': '13',
      },
    });
    const listeners = new Set();
    let socketRef = null;
    let buf = Buffer.alloc(0);

    const parseFrames = () => {
      while (buf.length >= 2) {
        const opcode = buf[0] & 0x0f;
        const masked = (buf[1] & 0x80) !== 0;
        let len = buf[1] & 0x7f;
        let offset = 2;
        if (len === 126) {
          if (buf.length < 4) return;
          len = buf.readUInt16BE(2);
          offset = 4;
        } else if (len === 127) {
          if (buf.length < 10) return;
          len = Number(buf.readBigUInt64BE(2));
          offset = 10;
        }
        const maskLen = masked ? 4 : 0;
        if (buf.length < offset + maskLen + len) return;
        let payload = buf.subarray(offset + maskLen, offset + maskLen + len);
        if (masked) {
          const mask = buf.subarray(offset, offset + 4);
          payload = Buffer.from(payload);
          for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i % 4];
        }
        buf = buf.subarray(offset + maskLen + len);
        if (opcode === 0x8) socketRef.end();
        else if (opcode === 0x9) sendFrame(payload, 0xA);
        else if (opcode === 0x1 || opcode === 0x2) {
          const text = payload.toString('utf8');
          for (const fn of listeners) fn(text);
        }
      }
    };

    function sendFrame(data, opcode = 0x1) {
      const payload = Buffer.isBuffer(data) ? data : Buffer.from(data);
      const mask = crypto.randomBytes(4);
      let header;
      if (payload.length < 126) {
        header = Buffer.alloc(6);
        header[0] = 0x80 | opcode;
        header[1] = 0x80 | payload.length;
        mask.copy(header, 2);
      } else if (payload.length < 65536) {
        header = Buffer.alloc(8);
        header[0] = 0x80 | opcode;
        header[1] = 0x80 | 126;
        header.writeUInt16BE(payload.length, 2);
        mask.copy(header, 4);
      } else {
        header = Buffer.alloc(14);
        header[0] = 0x80 | opcode;
        header[1] = 0x80 | 127;
        header.writeBigUInt64BE(BigInt(payload.length), 2);
        mask.copy(header, 10);
      }
      const masked = Buffer.allocUnsafe(payload.length);
      for (let i = 0; i < payload.length; i++) masked[i] = payload[i] ^ mask[i % 4];
      socketRef.write(Buffer.concat([header, masked]));
    }

    req.on('upgrade', (_res, socket) => {
      socketRef = socket;
      socket.on('data', (chunk) => {
        buf = Buffer.concat([buf, chunk]);
        parseFrames();
      });
      resolve({
        send: (str) => sendFrame(str, 0x1),
        onMessage: (fn) => listeners.add(fn),
        close: () => socket.end(),
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function runWithNativeCdp(env, options, scenarioFn, stagingDir) {
  const ffmpeg = env.ffmpeg.path;
  if (!ffmpeg) throw new Error('Native CDP driver requires ffmpeg to encode captured frames.');
  const chromium = options.executablePath
    ? { path: options.executablePath, kind: 'explicit' }
    : env.browsers.find((b) => b.engine === 'chromium');
  if (!chromium) throw new Error('Native CDP driver requires a Chromium binary.');

  const profileDir = path.join(stagingDir, `cdp-profile-${Date.now()}`);
  const framesDir = path.join(stagingDir, `cdp-frames-${Date.now()}`);
  fs.mkdirSync(profileDir, { recursive: true });
  fs.mkdirSync(framesDir, { recursive: true });

  const spawnArgs = [
    '--headless',
    '--remote-debugging-port=0',
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--mute-audio',
    `--window-size=${options.viewport.width},${options.viewport.height}`,
    'about:blank',
  ];

  const proc = spawn(chromium.path, spawnArgs, { stdio: ['ignore', 'pipe', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => {
    let errBuf = '';
    const timer = setTimeout(() => reject(new Error(`Timed out waiting for CDP DevTools URL.\n${errBuf}`)), 10000);
    proc.stderr.on('data', (chunk) => {
      errBuf += chunk.toString();
      const m = errBuf.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (m) {
        clearTimeout(timer);
        resolve(m[1]);
      }
    });
    proc.on('exit', (code) => {
      clearTimeout(timer);
      reject(new Error(`Chromium exited (${code}) before opening DevTools:\n${errBuf}`));
    });
  });

  const ws = await openWsClient(wsUrl);
  let nextId = 1;
  const pending = new Map();
  const eventHandlers = new Map();
  ws.onMessage((raw) => {
    const msg = JSON.parse(raw);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result);
    } else if (msg.method && eventHandlers.has(msg.method)) {
      for (const h of eventHandlers.get(msg.method)) h(msg.params, msg.sessionId);
    }
  });

  const cdp = (method, params = {}, sessionId = undefined) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    const payload = sessionId ? { id, method, params, sessionId } : { id, method, params };
    ws.send(JSON.stringify(payload));
  });
  const onEvent = (method, fn) => {
    if (!eventHandlers.has(method)) eventHandlers.set(method, []);
    eventHandlers.get(method).push(fn);
  };

  try {
    const { targetInfos } = await cdp('Target.getTargets');
    const pageTarget = targetInfos.find((t) => t.type === 'page') || (await cdp('Target.createTarget', { url: 'about:blank' }));
    const targetId = pageTarget.targetId;
    const { sessionId } = await cdp('Target.attachToTarget', { targetId, flatten: true });

    await cdp('Page.enable', {}, sessionId);
    await cdp('Runtime.enable', {}, sessionId);
    await cdp('Emulation.setDeviceMetricsOverride', {
      width: options.viewport.width,
      height: options.viewport.height,
      deviceScaleFactor: 1,
      mobile: false,
    }, sessionId);
    await cdp('Page.addScriptToEvaluateOnNewDocument', { source: OVERLAY_INIT_SCRIPT }, sessionId);
    await cdp('Runtime.evaluate', { expression: OVERLAY_INIT_SCRIPT }, sessionId);

    const evalFn = async (expr) => {
      const res = await cdp('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }, sessionId);
      if (res.exceptionDetails) throw new Error(res.exceptionDetails.text || 'CDP eval error');
      return res.result?.value;
    };

    const frames = [];
    onEvent('Page.screencastFrame', async (params) => {
      const idx = frames.length;
      const framePath = path.join(framesDir, `frame-${String(idx).padStart(5, '0')}.jpg`);
      fs.writeFileSync(framePath, Buffer.from(params.data, 'base64'));
      frames.push({ path: framePath, ts: params.metadata?.timestamp || Date.now() / 1000 });
      cdp('Page.screencastFrameAck', { sessionId: params.sessionId }, sessionId).catch(() => {});
    });

    await cdp('Page.startScreencast', { format: 'jpeg', quality: 92, everyNthFrame: 1 }, sessionId);

    let lastMouse = { x: options.viewport.width / 2, y: options.viewport.height / 2 };
    await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: lastMouse.x, y: lastMouse.y }, sessionId);

    const findElSnippet = `(sel) => {
      if (typeof sel === 'string' && sel.startsWith('text=')) {
        const needle = sel.slice(5).trim();
        const matches = [...document.querySelectorAll('button,a,[role="button"],input,label,span,h1,h2,h3,p,div')]
          .filter((el) => el.textContent && el.textContent.includes(needle));
        return matches.find((el) => !matches.some((other) => other !== el && el.contains(other))) || matches[0] || null;
      }
      return document.querySelector(sel);
    }`;

    const adapter = {
      driverName: `native-cdp:${chromium.kind}`,
      page: { evalFn, cdp, sessionId },
      goto: async (url) => {
        await cdp('Page.navigate', { url }, sessionId);
        await wait(350);
        await evalFn(`new Promise(r => document.readyState !== 'loading' ? r() : document.addEventListener('DOMContentLoaded', r, { once: true }))`);
      },
      mouseMove: async (x, y) => {
        lastMouse = { x, y };
        await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y }, sessionId);
      },
      mouseDown: () => cdp('Input.dispatchMouseEvent', { type: 'mousePressed', x: lastMouse.x, y: lastMouse.y, button: 'left', clickCount: 1 }, sessionId),
      mouseUp: () => cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', x: lastMouse.x, y: lastMouse.y, button: 'left', clickCount: 1 }, sessionId),
      resolveBox: async (sel) => {
        const box = await evalFn(`(() => {
          const el = (${findElSnippet})(${JSON.stringify(sel)});
          if (!el) return null;
          el.scrollIntoView({ block: 'center', inline: 'center' });
          const r = el.getBoundingClientRect();
          return { x: r.left, y: r.top, width: r.width, height: r.height };
        })()`);
        if (!box || box.width === 0) throw new Error(`Element not visible: ${sel}`);
        return box;
      },
      clearActiveIfNeeded: async (sel) => {
        await evalFn(`(() => {
          const el = (${findElSnippet})(${JSON.stringify(sel)});
          if (el && 'value' in el) { el.value = ''; el.dispatchEvent(new Event('input', { bubbles: true })); }
        })()`);
      },
      typeSequentially: async (_sel, text, delay) => {
        for (const ch of text) {
          await cdp('Input.dispatchKeyEvent', { type: 'keyDown', text: ch }, sessionId);
          await cdp('Input.dispatchKeyEvent', { type: 'keyUp', text: ch }, sessionId);
          if (delay > 0) await wait(delay);
        }
      },
      zoomTo: (sel, scale) => evalFn(`(() => { const el = (${findElSnippet})(${JSON.stringify(sel)}); if (el && window.__zoomElement) window.__zoomElement(el, ${Number(scale)}); })()`),
      resetZoom: () => evalFn(`window.__applyBaseStage && window.__applyBaseStage(true)`),
      checkBadgeCollision: () => evalFn(`window.__checkBadgeCollision && window.__checkBadgeCollision()`),
      showStep: (text, mode) => evalFn(`(() => {
        const prev = sessionStorage.getItem('__demoStepMode');
        try { sessionStorage.setItem('__demoStepMode', ${JSON.stringify(mode)}); sessionStorage.setItem('__demoStep', ${JSON.stringify(text)}); } catch {}
        if (prev !== ${JSON.stringify(mode)} && window.__applyBaseStage) window.__applyBaseStage(false);
        if (window.__renderStepBadge) window.__renderStepBadge(${JSON.stringify(text)}, ${JSON.stringify(mode)});
      })()`),
      hideStep: () => evalFn(`(() => {
        try { sessionStorage.removeItem('__demoStep'); } catch {}
        const b = document.getElementById('demo-step-badge');
        if (b) b.style.opacity = '0';
      })()`),
    };

    const session = createDemoSession(adapter, options);
    if (options.url) await session.goto(options.url);
    session.markStart();
    await scenarioFn(session);
    await wait(250);
    await cdp('Page.stopScreencast', {}, sessionId);

    if (frames.length === 0) throw new Error('Native CDP screencast produced 0 frames.');
    const concatPath = path.join(framesDir, 'frames.txt');
    const lines = [];
    for (let i = 0; i < frames.length; i++) {
      const dur = i < frames.length - 1
        ? Math.max(0.033, Math.min(2.0, frames[i + 1].ts - frames[i].ts))
        : 0.1;
      lines.push(`file '${frames[i].path.replace(/'/g, "'\\''")}'`, `duration ${dur.toFixed(4)}`);
    }
    lines.push(`file '${frames[frames.length - 1].path.replace(/'/g, "'\\''")}'`);
    fs.writeFileSync(concatPath, lines.join('\n'));

    const rawVideoPath = path.join(stagingDir, `cdp-${Date.now()}.mp4`);
    execFileSync(ffmpeg, [
      '-y', '-f', 'concat', '-safe', '0', '-i', concatPath,
      '-vf', `scale=${options.viewport.width}:${options.viewport.height}:force_original_aspect_ratio=decrease,pad=${options.viewport.width}:${options.viewport.height}:(ow-iw)/2:(oh-ih)/2,fps=30`,
      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', rawVideoPath,
    ], { stdio: 'pipe' });

    return { rawVideoPath, fastSegments: session.fastSegments, driver: adapter.driverName };
  } finally {
    ws.close();
    proc.kill('SIGTERM');
  }
}

// --- Public API ---

export async function recordDemo(options, scenarioFn) {
  const opts = {
    url: options.url || null,
    output: options.output || 'recordings/demo-recording.mp4',
    viewport: options.viewport || DEFAULT_VIEWPORT,
    stepMode: options.stepMode || 'static-bar',
    driver: options.driver || 'auto',
    executablePath: options.executablePath || null,
    stagingDir: path.resolve(options.stagingDir || DEFAULT_STAGING_DIR),
    keepTemp: Boolean(options.keepTemp),
  };

  const env = discoverEnvironment();
  if (!env.ready && !opts.executablePath) {
    throw new Error('No compatible browser/driver found. Run with --check-env to inspect missing prerequisites.');
  }

  const candidateDrivers = opts.driver !== 'auto'
    ? [opts.driver]
    : [
        env.drivers.playwright.available && 'playwright',
        env.drivers.puppeteer.available && 'puppeteer',
        env.drivers.nativeCdp.available && 'native-cdp',
      ].filter(Boolean);

  if (candidateDrivers.length === 0) {
    throw new Error('Unable to select automation driver. Run --check-env.');
  }

  const runners = {
    playwright: runWithPlaywright,
    puppeteer: runWithPuppeteer,
    'native-cdp': runWithNativeCdp,
  };

  fs.mkdirSync(opts.stagingDir, { recursive: true });
  try {
    let capture = null;
    const failures = [];
    for (const drv of candidateDrivers) {
      const fn = runners[drv];
      if (!fn) throw new Error(`Unsupported driver: ${drv}`);
      let ranScenario = false;
      try {
        capture = await fn(env, opts, async (s) => {
          ranScenario = true;
          return scenarioFn(s);
        }, opts.stagingDir);
        break;
      } catch (err) {
        if (opts.driver !== 'auto' || ranScenario) throw err;
        failures.push(`${drv}: ${err.message.split('\n')[0]}`);
      }
    }
    if (!capture) {
      throw new Error(`All detected drivers failed:\n  ${failures.join('\n  ')}`);
    }

    const outputs = transcodeVideo(capture.rawVideoPath, opts.output, {
      segments: capture.fastSegments,
      width: opts.viewport.width,
      ffmpegBin: env.ffmpeg.path,
    });
    return { driver: capture.driver, fastSegments: capture.fastSegments, outputs };
  } finally {
    if (!opts.keepTemp) {
      fs.rmSync(opts.stagingDir, { recursive: true, force: true });
    }
  }
}

// --- CLI Entrypoint ---

function printHelp() {
  console.log(`Usage: demo-harness.mjs [options]

Options:
  --check-env              Inspect Node.js, automation drivers, installed browsers, and ffmpeg (JSON).
  --transcode <input>      Transcode an existing WebM/MP4 recording to target format(s).
  --output <path>          Output file path (.mp4, .webm, or .gif). Repeatable.
  --segments <json>        Optional speed-ramp segments JSON: '[{"start":1.0,"end":3.2,"speed":1.75}]'.
  --width <px>             Output GIF scale width (default: 1280).
  --help                   Show this help message.`);
}

async function runCli(argv) {
  if (argv.includes('--help') || argv.includes('-h')) {
    printHelp();
    return;
  }
  if (argv.includes('--check-env')) {
    const env = discoverEnvironment();
    console.log(JSON.stringify(env, null, 2));
    process.exitCode = env.ready ? 0 : 1;
    return;
  }

  const transcodeIdx = argv.indexOf('--transcode');
  if (transcodeIdx !== -1) {
    const input = argv[transcodeIdx + 1];
    if (!input) throw new Error('--transcode requires an input file path.');
    const outputs = [];
    let segments = [];
    let width = 1280;
    for (let i = 0; i < argv.length; i++) {
      if (argv[i] === '--output' && argv[i + 1]) outputs.push(argv[++i]);
      else if (argv[i] === '--segments' && argv[i + 1]) segments = JSON.parse(argv[++i]);
      else if (argv[i] === '--width' && argv[i + 1]) width = Number(argv[++i]);
    }
    if (outputs.length === 0) throw new Error('--transcode requires at least one --output <path>.');
    const res = transcodeVideo(input, outputs, { segments, width });
    console.log(JSON.stringify({ outputs: res }, null, 2));
    return;
  }

  printHelp();
  process.exitCode = 1;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  runCli(process.argv.slice(2)).catch((err) => {
    console.error(`[demo-harness] ${err.message}`);
    process.exitCode = 1;
  });
}
