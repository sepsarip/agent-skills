---
name: record-web-demo
description: Record polished, humanized walkthrough demo videos of web applications using Playwright. Use when the user asks to record a web demo, generate video walkthroughs of a web page or web app, capture UI interactions into MP4, WebM, or GIF, or automate browser screen recording for documentation, changelogs, and READMEs.
license: MIT
compatibility: Requires Node.js 18+, Playwright (npx playwright), Chromium browser binary, and optional ffmpeg (for MP4/GIF transcoding).
metadata:
  version: "0.2.0"
---
# Record Web Demo

Automate the recording of web application UI workflows and product demos into clean MP4, WebM, or GIF formats using Playwright with humanized pacing, default speed ramping, optional camera auto-zoom/pan, optional visual step callout badges, standardized output locations, atomic temporary directory cleanup, and dynamic cursor simulation (pointer, hand, I-beam).

## When to Use

- User wants to record a video or GIF demo of a local or hosted web application.
- Creating automated visual walkthroughs for documentation, GitHub READMEs, or changelogs.
- Capturing step-by-step browser interactions (forms, navigation, dashboard clicks, animations).
- Creating reproducible UI flow presentations without manual screen recorder software.

## Workflow

### Step 1: Pre-flight Verification

Verify runtime tools and dependencies before running recordings:

1. Check Node.js and Playwright runtime:
   ```bash
   node -v
   npx -y playwright --version
   ```

2. Check browser binaries (install chromium if missing):
   ```bash
   npx -y playwright install chromium
   ```

3. Check ffmpeg availability (required for WebM to MP4, optimized GIF conversion, or post-process speed ramping):
   ```bash
   ffmpeg -version
   ```
   If ffmpeg is not available, inform the user that the output will remain in native WebM format.

### Step 2: Define Scenario, Parameters, and Output Path

Determine demo parameters, confirm optional visual enhancements with the user, and set the output destination:

- Target URL: Local development server (e.g., `http://localhost:3000`) or remote URL.
- Resolution: Standardize on 1280x720 (720p 16:9 default for READMEs) or 1920x1080 (1080p).
- Target format: WebM (native Playwright), MP4 (universal web playback), or GIF (GitHub README).
- Visual & Timing Features:
  - **Speed Ramping (Dynamic Duration)** — **Default: Active (ON)**. Automatically accelerates long text typing (`1.5x–2x` faster) and compresses slow loading spinners/network waits while keeping key visual moments (modal appearances, theme switches, state confirmations) at normal `1x` speed so the demo never feels sluggish.
  - **Auto-Zoom & Pan (Hotspot Focus)** — **Default: Inactive (OFF)**. Before generating the script, **ask the user** whether they want to enable smooth camera zoom-in (`1.5x–1.8x`) on small inputs, password fields, or compact toggles (especially helpful for 1080p recordings viewed on mobile screens) and zoom-out when viewing full layouts.
  - **Step Callout / Floating Badges (Visual Narration)** — **Default: Inactive (OFF)**. Before generating the script, **ask the user** whether they want to display semi-transparent floating step badges in the corner of the screen (e.g., `"Langkah 1: Masuk dengan Akun Admin"`, `"Langkah 2: Ganti Tema ke Dark Mode"`) to provide clear storytelling in silent/muted videos.
- Output File Path:
  - Default: `recordings/<scenario-name>.<ext>` (e.g. `recordings/login-flow.mp4` or `recordings/dashboard-navigation.gif`). Never use generic `demo.mp4` to avoid accidental overwrites.
  - Custom override: If the user specifies a custom path (e.g. `docs/assets/hero.gif`), save directly there.
- Temporary Staging and Strict Script Location:
  - Never create separate script folders like `scripts/`, `tmp/`, or root files.
  - Colocate the transient runner script AND raw video captures inside an isolated staging folder: `recordings/.temp/`.

### Step 3: Humanized Script Generation with Dynamic Tabler Cursors

Generate the self-contained runner script directly inside `recordings/.temp/runner.mjs`. Do not record at raw machine speed; human viewers need visual rhythm and readable transitions.

Key implementation patterns for `recordings/.temp/runner.mjs`:

1. Video directory setup: Ensure the temporary staging directory exists and configure `recordVideo` inside `browser.newContext()`:
   ```javascript
   import { chromium } from 'playwright';
   import fs from 'node:fs';

   const tempDir = './recordings/.temp';
   fs.mkdirSync(tempDir, { recursive: true });

   const VIEWPORT = { width: 1280, height: 720 };
   const browser = await chromium.launch({ headless: true });
   const context = await browser.newContext({
     viewport: VIEWPORT,
     recordVideo: {
       dir: tempDir,
       size: VIEWPORT
     }
   });
   const page = await context.newPage();
   const recordingStartMs = Date.now();
   const fastSegments = []; // Stores { start: sec, end: sec, speed: 1.75 } for FFmpeg speed ramping
   ```

2. Dynamic Tabler Vector Cursors (MIT Licensed) & Overlay Mount:
   Mount `#demo-cursor` (and optional `#demo-step-badge`) on `document.documentElement` (`<html>`) rather than `document.body`. This guarantees that when `document.body` is scaled during Auto-Zoom & Pan, the cursor and callout badge remain at a crisp `1x` scale and never clip outside the viewport:
   ```javascript
   await page.addInitScript(() => {
     window.addEventListener('DOMContentLoaded', () => {
       window.__demoCamera = { scale: 1, tx: 0, ty: 0 };
       document.body.style.transformOrigin = '0 0';
       document.body.style.transition = 'transform 0.48s cubic-bezier(0.22, 1, 0.36, 1)';
       document.body.style.willChange = 'transform';

       const cursor = document.createElement('div');
       cursor.id = 'demo-cursor';
       cursor.style.cssText = 'position:fixed;top:0;left:0;pointer-events:none;z-index:999999;transform-origin:0 0;transform:scale(1);transition:transform 0.06s ease;will-change:left, top, transform;';

       const ICONS = {
         // Default Arrow (Hotspot: 4, 4)
         default: `
           <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="#ffffff" stroke="#111827" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 0 1px #fff) drop-shadow(0 2px 3px rgba(0,0,0,0.4)); margin-left: -4px; margin-top: -4px;">
             <path stroke="none" d="M0 0h24v24H0z" fill="none" />
             <path d="M7.904 17.563a1.2 1.2 0 0 0 2.228 .308l2.09 -3.093l4.907 4.907a1.067 1.067 0 0 0 1.509 0l1.047 -1.047a1.067 1.067 0 0 0 0 -1.509l-4.907 -4.907l3.113 -2.09a1.2 1.2 0 0 0 -.309 -2.228l-13.582 -3.904l3.904 13.563" />
           </svg>
         `,
         // Hand Finger Pointer (Hotspot: 9.5, 3)
         pointer: `
           <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="#ffffff" stroke="#111827" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 0 1px #fff) drop-shadow(0 2px 3px rgba(0,0,0,0.4)); margin-left: -9.5px; margin-top: -3px;">
             <path stroke="none" d="M0 0h24v24H0z" fill="none" />
             <path d="M8 13v-8.5a1.5 1.5 0 0 1 3 0v7.5" />
             <path d="M11 11.5v-2a1.5 1.5 0 1 1 3 0v2.5" />
             <path d="M14 10.5a1.5 1.5 0 0 1 3 0v1.5" />
             <path d="M17 11.5a1.5 1.5 0 0 1 3 0v4.5a6 6 0 0 1 -6 6h-2h.208a6 6 0 0 1 -5.012 -2.7a69.74 69.74 0 0 1 -.196 -.3c-.312 -.479 -1.407 -2.388 -3.286 -5.728a1.5 1.5 0 0 1 .536 -2.022a1.867 1.867 0 0 1 2.28 .28l1.47 1.47" />
           </svg>
         `,
         // I-Beam Text Cursor (Hotspot: 12, 12)
         text: `
           <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#111827" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 0 1.5px #fff) drop-shadow(0 2px 3px rgba(0,0,0,0.4)); margin-left: -12px; margin-top: -12px;">
             <path stroke="none" d="M0 0h24v24H0z" fill="none" />
             <path d="M10 12h4" />
             <path d="M9 4a3 3 0 0 1 3 3v10a3 3 0 0 1 -3 3" />
             <path d="M15 4a3 3 0 0 0 -3 3v10a3 3 0 0 0 3 3" />
           </svg>
         `
       };

       let currentState = 'default';
       cursor.innerHTML = ICONS.default;
       document.documentElement.appendChild(cursor);

       window.addEventListener('mousemove', (e) => {
         cursor.style.left = `${e.clientX}px`;
         cursor.style.top = `${e.clientY}px`;

         const el = document.elementFromPoint(e.clientX, e.clientY);
         if (!el) return;

         const comp = window.getComputedStyle(el).cursor;
         let nextState = 'default';

         if (comp === 'pointer' || el.closest('button, a, [role="button"], input[type="submit"], input[type="checkbox"], input[type="radio"]')) {
           nextState = 'pointer';
         } else if (comp === 'text' || el.closest('input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]), textarea, [contenteditable="true"]')) {
           nextState = 'text';
         }

         if (nextState !== currentState) {
           currentState = nextState;
           cursor.innerHTML = ICONS[nextState];
         }
       });

       window.addEventListener('mousedown', () => cursor.style.transform = 'scale(0.85)');
       window.addEventListener('mouseup', () => cursor.style.transform = 'scale(1)');
     });
   });
   ```

3. Speed Ramping & Natural Pacing Helpers (Default: Active):
   - **Adaptive Typing (`humanType`)**: Short strings ($\le 15$ chars, such as short codes or usernames) type at normal speed (`85ms`/char). Longer strings ($> 15$ chars, such as emails, URLs, or descriptions) automatically ramp up to `1.5x–2x` speed (`40ms`/char) so typing never drags.
   - **Loading / Async Speed Ramping (`withSpeedRamp`)**: Wrap slow network submissions or loading spinners with `withSpeedRamp(page, async () => { ... }, 1.75)`. It records the exact `[start, end]` timestamps so FFmpeg can accelerate that segment by `1.5x–2x` during post-processing while keeping important UI reveals (modals, theme transitions, toasts) at `1x` speed (`await page.waitForTimeout(800)`).
   ```javascript
   async function moveAndClick(page, selector, { steps = 25 } = {}) {
     const loc = page.locator(selector).first();
     await loc.waitFor({ state: 'visible' });
     const box = await loc.boundingBox();
     if (!box) throw new Error(`Element not visible: ${selector}`);
     const targetX = box.x + box.width / 2;
     const targetY = box.y + box.height / 2;
     await page.mouse.move(targetX, targetY, { steps });
     await page.waitForTimeout(120);
     await page.mouse.down();
     await page.waitForTimeout(90);
     await page.mouse.up();
   }

   async function humanType(page, selector, text) {
     await moveAndClick(page, selector);
     // Speed ramping: 1x (85ms) for short inputs, ~2x (42ms) for longer text
     const delay = text.length > 15 ? 42 : 85;
     await page.keyboard.type(text, { delay });
   }

   async function withSpeedRamp(fn, speed = 1.75) {
     const start = (Date.now() - recordingStartMs) / 1000;
     const result = await fn();
     const end = (Date.now() - recordingStartMs) / 1000;
     if (end - start >= 0.8) {
       fastSegments.push({ start: Number(start.toFixed(2)), end: Number(end.toFixed(2)), speed });
     }
     return result;
   }
   ```

4. Optional Helper: Auto-Zoom & Pan (Include ONLY when user opts in):
   Smoothly zooms and pans the camera onto compact form controls or toggles using clamped viewport translation (so the camera never reveals empty margins outside the page), then resets to `1x` for full-page navigation:
   ```javascript
   async function zoomTo(page, selector, scale = 1.65) {
     const loc = page.locator(selector).first();
     await loc.waitFor({ state: 'visible' });
     await page.evaluate(({ sel, targetScale }) => {
       const el = document.querySelector(sel);
       if (!el) return;
       const cam = window.__demoCamera || { scale: 1, tx: 0, ty: 0 };
       const rect = el.getBoundingClientRect();
       // Recover unscaled element center in viewport coordinates
       const cx0 = (rect.left + rect.width / 2 - cam.tx) / cam.scale;
       const cy0 = (rect.top + rect.height / 2 - cam.ty) / cam.scale;
       const vw = window.innerWidth;
       const vh = window.innerHeight;
       // Clamp translation so viewport edges never show blank space
       const rawTx = vw / 2 - cx0 * targetScale;
       const rawTy = vh / 2 - cy0 * targetScale;
       const tx = Math.max(vw * (1 - targetScale), Math.min(0, rawTx));
       const ty = Math.max(vh * (1 - targetScale), Math.min(0, rawTy));
       window.__demoCamera = { scale: targetScale, tx, ty };
       document.body.style.transform = `translate(${tx}px, ${ty}px) scale(${targetScale})`;
     }, { sel: selector, targetScale: scale });
     await page.waitForTimeout(500); // Wait for smooth camera zoom transition
   }

   async function resetZoom(page) {
     await page.evaluate(() => {
       window.__demoCamera = { scale: 1, tx: 0, ty: 0 };
       document.body.style.transform = 'translate(0px, 0px) scale(1)';
     });
     await page.waitForTimeout(500);
   }
   ```

5. Optional Helper: Step Callout / Floating Badges (Include ONLY when user opts in):
   Injects a semi-transparent storytelling pill badge at the bottom-center (or corner) of the viewport so viewers immediately understand the intent of each step without audio narration:
   ```javascript
   async function showStep(page, stepText) {
     await page.evaluate((text) => {
       let badge = document.getElementById('demo-step-badge');
       if (!badge) {
         badge = document.createElement('div');
         badge.id = 'demo-step-badge';
         badge.style.cssText = [
           'position:fixed',
           'bottom:28px',
           'left:50%',
           'transform:translateX(-50%) translateY(8px)',
           'padding:8px 18px',
           'background:rgba(17, 24, 39, 0.86)',
           'color:#f9fafb',
           'border:1px solid rgba(255, 255, 255, 0.18)',
           'border-radius:9999px',
           'font:600 14px/1.4 system-ui, -apple-system, sans-serif',
           'letter-spacing:0.01em',
           'box-shadow:0 8px 24px rgba(0, 0, 0, 0.35)',
           'backdrop-filter:blur(8px)',
           'pointer-events:none',
           'z-index:999998',
           'opacity:0',
           'transition:opacity 0.25s ease, transform 0.25s ease'
         ].join(';');
         document.documentElement.appendChild(badge);
       }
       badge.textContent = text;
       requestAnimationFrame(() => {
         badge.style.opacity = '1';
         badge.style.transform = 'translateX(-50%) translateY(0)';
       });
     }, stepText);
   }

   async function hideStep(page) {
     await page.evaluate(() => {
       const badge = document.getElementById('demo-step-badge');
       if (badge) {
         badge.style.opacity = '0';
         badge.style.transform = 'translateX(-50%) translateY(8px)';
       }
     });
   }
   ```

6. Graceful closure: Always close `context` and `browser` to ensure video buffers are fully flushed to disk:
   ```javascript
   const videoPath = await page.video().path();
   await context.close();
   await browser.close();
   console.log(`RAW_VIDEO_PATH:${videoPath}`);
   console.log(`FAST_SEGMENTS:${JSON.stringify(fastSegments)}`);
   ```

### Step 4: Execute Recording

Execute the colocated script in headless mode:
```bash
node recordings/.temp/runner.mjs
```

Capture the printed `RAW_VIDEO_PATH` (inside `recordings/.temp/`) and `FAST_SEGMENTS`.

### Step 5: Post-Processing, Speed Ramping, and Transcoding

Transcode or move the raw video to the final standardized output destination:

- **Optional Timeline Speed Ramping** (when `FAST_SEGMENTS` is non-empty, e.g., a loading spinner from `t=3.0s` to `t=6.5s` accelerated by `1.75x`):
  Pre-process the raw WebM using FFmpeg `trim` + `setpts` before or during transcoding so waiting periods play at `1.5x–2x` while normal interactions stay at `1x`:
  ```bash
  ffmpeg -y -i recordings/.temp/<hash>.webm -filter_complex \
    "[0:v]trim=0:3.0,setpts=PTS-STARTPTS[v0]; \
     [0:v]trim=3.0:6.5,setpts=(PTS-STARTPTS)/1.75[v1]; \
     [0:v]trim=6.5,setpts=PTS-STARTPTS[v2]; \
     [v0][v1][v2]concat=n=3:v=1:a=0[outv]" \
    -map "[outv]" -c:v libx264 -pix_fmt yuv420p -movflags +faststart recordings/<scenario-name>.mp4
  ```

- Native WebM (no post-process speed segments): Move and rename the raw file from staging:
  ```bash
  mv recordings/.temp/<hash>.webm recordings/<scenario-name>.webm
  ```

- Convert to MP4 (H.264 with no audio, web-optimized faststart):
  ```bash
  ffmpeg -y -i recordings/.temp/<hash>.webm -c:v libx264 -pix_fmt yuv420p -movflags +faststart recordings/<scenario-name>.mp4
  ```

- Convert to Optimized GIF (two-pass palettegen to avoid color banding and huge file sizes):
  ```bash
  ffmpeg -y -i recordings/.temp/<hash>.webm -filter_complex "[0:v] fps=15,scale=1280:-1:flags=lanczos,split [a][b];[a] palettegen=stats_mode=diff [p];[b][p] paletteuse=dither=bayer:bayer_scale=3" recordings/<scenario-name>.gif
  ```

### Step 6: Atomic Cleanup, Verify, and Deliver

1. Atomic directory purge: Remove the entire staging folder in a single command. Because both the runner script and video buffers were kept in `.temp`, this completely removes all temporary assets without leaving empty directories behind:
   ```bash
   rm -rf recordings/.temp
   ```

2. Verification:
   - Check that the final file exists and has non-zero size (`ls -lh recordings/<scenario-name>.<ext>`).
   - Verify video duration matches expected scenario length.

3. Deliver the final relative/absolute file path and file size clearly to the user.

## Gotchas

- Zero-byte Video Files: Playwright writes video data on a background thread. The file remains locked or empty until `await context.close()` has resolved.
- Orphan Directory Leak: Never create standalone directories like `scripts/` or `tmp/`. Always place transient scripts in `recordings/.temp/runner.mjs` so `rm -rf recordings/.temp` cleanly purges everything.
- Git Hygiene: Add `recordings/.temp/` to `.gitignore` so temporary runs never pollute Git status.
- Machine-Speed Teleportation: By default, Playwright teleports the mouse cursor instantly and clicks in 5ms. Always use stepped mouse moves and humanized typing delays so humans can follow the video.
- Overlay Scaling & Coordinate Drift during Auto-Zoom: Never append `#demo-cursor` or `#demo-step-badge` to `document.body` if `document.body` is zoomed with CSS `transform`. Always append overlays to `document.documentElement` (`<html>`) and wait (`500ms`) for the zoom transition to finish before calling `boundingBox()` or moving the mouse cursor.
- Dynamic Spinners and Hydration: Use `waitForSelector` or `waitForLoadState('networkidle')` instead of arbitrary short sleeps to prevent recordings from capturing incomplete UI states, and wrap unavoidable slow loading waits in `withSpeedRamp()` so they can be accelerated `1.5x–2x`.
- Viewport Mismatch: Set both `viewport` and `recordVideo.size` to the exact same dimensions in `browser.newContext()` to avoid black borders or canvas scaling distortion.
- Headless Environment: Playwright video recording works reliably with `headless: true`. Do not force `headless: false` unless a virtual framebuffer (Xvfb) or active display server is guaranteed.
