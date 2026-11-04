---
name: record-web-demo
description: Record polished, humanized walkthrough demo videos of web applications using Playwright. Use when the user asks to record a web demo, generate video walkthroughs of a web page or web app, capture UI interactions into MP4, WebM, or GIF, or automate browser screen recording for documentation, changelogs, and READMEs.
license: MIT
compatibility: Requires Node.js 18+, Playwright (npx playwright), Chromium browser binary, and optional ffmpeg (for MP4/GIF transcoding).
metadata:
  version: "0.1.0"
---
# Record Web Demo

Automate the recording of web application UI workflows and product demos into clean MP4, WebM, or GIF formats using Playwright with humanized pacing, standardized output locations, atomic temporary directory cleanup, and dynamic cursor simulation (pointer, hand, I-beam).

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

3. Check ffmpeg availability (required for WebM to MP4 or optimized GIF conversion):
   ```bash
   ffmpeg -version
   ```
   If ffmpeg is not available, inform the user that the output will remain in native WebM format.

### Step 2: Define Scenario, Parameters, and Output Path

Determine demo parameters and output destination:

- Target URL: Local development server (e.g., `http://localhost:3000`) or remote URL.
- Resolution: Standardize on 1280x720 (720p 16:9 default for READMEs) or 1920x1080 (1080p).
- Target format: WebM (native Playwright), MP4 (universal web playback), or GIF (GitHub README).
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

   const browser = await chromium.launch({ headless: true });
   const context = await browser.newContext({
     viewport: { width: 1280, height: 720 },
     recordVideo: {
       dir: tempDir,
       size: { width: 1280, height: 720 }
     }
   });
   const page = await context.newPage();
   ```

2. Dynamic Tabler Vector Cursors (MIT Licensed):
   Inject responsive vector cursors that automatically adapt between default arrow, pointer hand, and text I-beam with calibrated hotspots and dual-tone high contrast for light/dark themes:
   ```javascript
   await page.addInitScript(() => {
     window.addEventListener('DOMContentLoaded', () => {
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
       document.body.appendChild(cursor);

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

3. Natural pacing helpers:
   - Use `page.mouse.move(x, y, { steps: 25 })` for smooth visible cursor trajectories before clicks.
   - Use `page.locator().fill(text)` followed by typing delay, or `page.type(selector, text, { delay: 90 })` to make user input readable.
   - Add settle pauses (`await page.waitForTimeout(800)`) after state changes, modal popups, or page switches.

4. Graceful closure: Always close `context` and `browser` to ensure video buffers are fully flushed to disk:
   ```javascript
   const videoPath = await page.video().path();
   await context.close();
   await browser.close();
   console.log(`RAW_VIDEO_PATH:${videoPath}`);
   ```

### Step 4: Execute Recording

Execute the colocated script in headless mode:
```bash
node recordings/.temp/runner.mjs
```

Capture the printed `RAW_VIDEO_PATH` (inside `recordings/.temp/`).

### Step 5: Post-Processing and Transcoding

Transcode or move the raw video to the final standardized output destination:

- Native WebM: If WebM was requested, move and rename the raw file from staging:
  ```bash
  mv recordings/.temp/<hash>.webm recordings/<scenario-name>.webm
  ```

- Convert to MP4 (H.264 with AAC/no audio, web-optimized faststart):
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
- Dynamic Spinners and Hydration: Use `waitForSelector` or `waitForLoadState('networkidle')` instead of arbitrary short sleeps to prevent recordings from capturing incomplete UI states.
- Viewport Mismatch: Set both `viewport` and `recordVideo.size` to the exact same dimensions in `browser.newContext()` to avoid black borders or canvas scaling distortion.
- Headless Environment: Playwright video recording works reliably with `headless: true`. Do not force `headless: false` unless a virtual framebuffer (Xvfb) or active display server is guaranteed.
