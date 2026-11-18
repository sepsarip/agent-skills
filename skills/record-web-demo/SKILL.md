---
name: record-web-demo
description: Record polished, humanized walkthrough demo videos of web applications in MP4, WebM, or GIF using whatever browser automation runtime and browser binary are already available (Playwright, Puppeteer, or zero-dependency Chromium CDP with Chrome, Edge, Brave, Chromium, or Playwright caches). Use when the user asks to record a web demo, generate a video walkthrough of a web page or web app, capture UI interactions into MP4, WebM, or GIF, or automate browser screen recording for docs, changelogs, and READMEs. Do not use for end-user written manual books (.docx/.pdf), source-code diagrams, or functional regression test suites.
license: MIT
compatibility: Requires Node.js 18+. Automatically reuses installed Playwright, Puppeteer, or zero-dependency Chromium CDP with any available Chromium/Chrome/Edge/Brave/Playwright browser; optional ffmpeg (PATH or Playwright cache) for MP4/GIF/CDP encoding.
metadata:
  version: "0.3.0"
---

# Record Web Demo

Automate reproducible, human-paced product demo recordings of web applications into MP4, WebM, or GIF without duplicating hundreds of lines of cursor/FFmpeg boilerplate per run.

The bundled [`scripts/demo-harness.mjs`](scripts/demo-harness.mjs) runtime handles offline engine/browser auto-discovery, eased Tabler vector cursors (`default`, `pointer`, `text`), click ripples, optional zoom/pan, dual-mode step narration, FFmpeg speed ramping, multi-format transcoding, and atomic cleanup of `recordings/.temp/`.

## Progress Checklist

Copy and track progress with this checklist:

```markdown
- [ ] Step 0: Check available runtimes, browsers, and ffmpeg (`demo-harness.mjs --check-env`)
- [ ] Step 1: Confirm URL, resolution, output path/format, and optional visual features
- [ ] Step 2: Generate concise `recordings/.temp/runner.mjs` importing `recordDemo`
- [ ] Step 3: Execute `node recordings/.temp/runner.mjs` (records, transcodes, and cleans `.temp`)
- [ ] Step 4: Verify non-zero output file(s), clean workspace, and deliver path(s)
```

---

## Step 0: Offline Environment Discovery

Do **not** run `npx -y playwright ...` first — it can stall offline or re-download browsers when compatible binaries already exist on the machine. Run the bundled discovery check from the skill directory:

```bash
node <skill-dir>/scripts/demo-harness.mjs --check-env
```

(`node <skill-dir>/scripts/demo-harness.mjs --help` prints all CLI flags.)

How `demo-harness.mjs` selects what is already available:
1. **Drivers (in priority order)**: Node `playwright` / `playwright-core` (local `node_modules`, `NODE_PATH`, global npm, or `~/.npm/_npx` cache) $\rightarrow$ Node `puppeteer` / `puppeteer-core` $\rightarrow$ built-in zero-dependency **Chromium CDP** (`native-cdp`, requires any Chromium-family binary + `ffmpeg`).
2. **Browser binaries**: `DEMO_BROWSER_PATH` / `CHROME_BIN` env vars, Playwright caches (`PLAYWRIGHT_BROWSERS_PATH`, `.venv*/ms-playwright`, `~/.cache/ms-playwright`), and system browsers (`google-chrome`, `chromium`, `brave-browser`, `microsoft-edge`, `firefox`).
3. **FFmpeg**: `DEMO_FFMPEG_PATH`, `ffmpeg` on `PATH`, or cached Playwright `ffmpeg-*` binaries.

**If `ready` is `false` or a requested format (`mp4`/`gif`) is unavailable:**
- Only Playwright/Native WebM works without `ffmpeg`. If `ffmpeg` is missing and only `.webm` is viable, inform the user and default to `.webm` (or suggest installing `ffmpeg`).
- If no browser is detected, pick the lightest installation path for the user's environment (e.g., use an existing Chrome/Edge/Brave binary via `DEMO_BROWSER_PATH`, install system Chromium + `ffmpeg`, or run `npx playwright install chromium`).

---

## Step 1: Define Scenario, Parameters, and Features

Confirm the target parameters before writing the runner script:

- **Target URL**: Local dev server (e.g., `http://localhost:3000`) or hosted URL.
- **Resolution**: `1280x720` (16:9 default for READMEs/docs) or `1920x1080`.
- **Output Path & Format**: Default `recordings/<scenario-name>.<ext>` (`.mp4`, `.gif`, or `.webm`; pass an array like `['recordings/login.mp4', 'recordings/login.gif']` to export multiple formats from one capture). Avoid generic names like `demo.mp4` to prevent accidental overwrites.
- **Visual & Timing Features**:
  - **Speed Ramping (Default: ON)**: Long text (`> 15` chars) types faster (`42ms`/char vs `85ms`/char), and `demo.withSpeedRamp()` segments are accelerated (`1.75x` default) via FFmpeg `trim`/`setpts`/`concat` while keeping UI reveals at `1x`.
  - **Auto-Zoom & Pan (Default: OFF — ask user)**: Smoothly zooms (`1.65x`) onto compact inputs or toggles and resets back (`resetZoom()`).
  - **Step Callout / Narration (Default: OFF — ask user)**: Match the step text language to the user's prompt. If enabled, ask the user to choose between:

```text
[A] Static Bottom Bar (stepMode: 'static-bar' — Recommended)
+---------------------------------------------------+
|  +---------------------------------------------+  |
|  |         Web Application Stage (~0.92x)      |  |
|  |       Zero overlap with page controls       |  |
|  +---------------------------------------------+  |
+---------------------------------------------------+
|          [ Step 1: Sign in with account ]         | <- Fixed 52px bottom bar
+---------------------------------------------------+

[B] Floating Pill (stepMode: 'floating')
+---------------------------------------------------+
|                                                   |
|            Web Application Stage (1.0x)           |
|                                                   |
|         ( Step 1: Sign in with account )          | <- Auto-dodges cursor & buttons
+---------------------------------------------------+
```

---

## Step 2: Generate Concise Runner Script

Keep the target repository clean: never create `scripts/` or `tmp/` folders in the target workspace. Write a short declarative script at `recordings/.temp/runner.mjs` that imports `recordDemo` from `<skill-dir>/scripts/demo-harness.mjs` (using its absolute path or relative file path):

```javascript
import { recordDemo } from '/absolute/path/to/record-web-demo/scripts/demo-harness.mjs';

const result = await recordDemo({
  url: 'http://localhost:3000',
  output: ['recordings/login-flow.mp4', 'recordings/login-flow.gif'],
  viewport: { width: 1280, height: 720 },
  stepMode: 'static-bar', // 'static-bar' | 'floating' | 'off'
}, async (demo) => {
  await demo.showStep('Step 1: Enter credentials');
  await demo.zoomTo('#login-card', 1.5);
  await demo.humanType('#email', 'alex.rivera@example.com');
  await demo.humanType('#password', 'correct-horse-battery');
  await demo.resetZoom();

  await demo.showStep('Step 2: Submit and inspect dashboard');
  await demo.withSpeedRamp(async () => {
    await demo.moveAndClick('button[type="submit"]');
    await demo.pause(1200);
  });
  await demo.pause(900);
});

console.log(JSON.stringify(result, null, 2));
```

### `recordDemo(options, scenarioFn)` Reference

| Option / Method | Behavior |
|---|---|
| `options.url` | Initial entry URL navigated automatically before recording starts. |
| `demo.goto(url, waitUntil)` | Direct URL navigation. Use **only** for the initial entry URL, unlinked routes, or explicit user requests to jump via URL — never as a shortcut for in-app menu/tab navigation. |
| `options.output` | Single path or array of `.mp4`, `.webm`, `.gif` destinations. |
| `options.viewport` | `{ width, height }` synchronized with capture size (default `1280x720`). |
| `options.stepMode` | `'static-bar'` (default), `'floating'`, or `'off'`. |
| `options.driver` / `executablePath` | Force `'auto'` (default), `'playwright'`, `'puppeteer'`, or `'native-cdp'`; override binary path if needed. |
| `demo.showStep(text, { mode })` / `hideStep()` | Displays persistent step narration (`sessionStorage` survives full-page reloads) with `300ms` reader lead-in. |
| `demo.zoomTo(target, scale)` / `resetZoom()` | Smooth camera pan/zoom onto a CSS selector or Playwright `Locator`, clamped to the app stage. |
| `demo.moveAndClick(target, opts)` | Scrolls target into view, moves along an eased arc, renders a click ripple, and clicks. |
| `demo.humanType(target, text, { clear, delay })` | Moves, clicks, clears existing value (`clear: true` default), and types sequentially (`85ms` short / `42ms` long). |
| `demo.withSpeedRamp(fn, speed)` | Records segment bounds ($\ge 0.6\text{s}$) for FFmpeg `trim`/`setpts` acceleration (default `1.75x`). |
| `demo.pause(ms)` | Holds at `1x` speed so viewers can read transitions, modals, or confirmations. |
| `demo.page` | Escape hatch to the underlying Playwright/Puppeteer `Page` (or CDP `evalFn` handle) for `waitForSelector`, `getByRole`, etc. |

---

## Step 3: Execute Recording

Run the staging script inside Standard Sandbox Mode first:

```bash
node recordings/.temp/runner.mjs
```

`recordDemo()` flushes video buffers (`context.close()` / `recorder.stop()` / `Page.stopScreencast`), executes FFmpeg speed ramping and two-pass GIF palette encoding when requested, and deletes `recordings/.temp/` inside a `finally` block.

For manual re-transcoding or post-processing an existing raw capture:

```bash
node <skill-dir>/scripts/demo-harness.mjs --transcode raw.webm \
  --output recordings/flow.mp4 \
  --output recordings/flow.gif \
  --segments '[{"start":1.5,"end":4.0,"speed":1.75}]'
```

---

## Step 4: Verification Gate & Handover

Before finishing:
1. Verify all requested output files exist with non-zero size (`ls -lh recordings/<scenario-name>.*`).
2. Verify `recordings/.temp` has been completely purged.
3. Recommend adding `recordings/.temp/` (or `recordings/`) to `.gitignore` if binary captures should stay untracked.
4. Report the exact output path(s), file sizes, and driver/browser used to the user.

---

## Key Gotchas

- **UI click navigation over `demo.goto()`**: Drive all mid-flow page and tab transitions with `demo.moveAndClick()` (including opening prerequisite sidebar, avatar, or dropdown menus first) so viewers see the cursor path and click ripple. Reserve `demo.goto()` strictly for the initial entry URL (`options.url`), pages with no UI link, or when the user explicitly asks to jump directly to a URL.
- **Overlays mount on `document.documentElement`**: Camera transforms target `document.body`; mounting `#demo-cursor`, `.demo-click-ripple`, and step bars on `<html>` prevents cursor distortion during zoom.
- **Navigation persistence**: Cursor coordinates (`__demoCursor`) and active step state (`__demoStep`, `__demoStepMode`) persist in `sessionStorage` so multi-page flows do not snap back to `(0, 0)`.
- **Call order**: Call `demo.showStep()` **after** navigation completes and **before** `demo.zoomTo()` or `demo.moveAndClick()`.
- **Selector portability**: When targeting `native-cdp` or `puppeteer` drivers, prefer standard CSS selectors (or `text=...` in `native-cdp`) rather than Playwright-only `Locator` objects.
