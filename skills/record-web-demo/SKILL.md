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
  - **Step Callout / Visual Narration** — **Default: Inactive (OFF)**. Before generating the script, **ask the user** whether they want step narration enabled, and if yes, present this visual comparison so they can choose between the 2 layout styles:
    ```text
    [A] Static Bottom Bar (mode: 'static-bar' — Recommended)
    +---------------------------------------------------+
    |  +---------------------------------------------+  |
    |  |         Halaman Web Demo (Scale ~0.92x)     |  |
    |  |       Bebas tumpang tindih dengan tombol    |  |
    |  +---------------------------------------------+  |
    +---------------------------------------------------+
    |         [ Langkah 1: Masuk dengan Akun ]          | <- Bar Statis 52px (Posisi Tetap)
    +---------------------------------------------------+

    [B] Floating Badge (mode: 'floating')
    +---------------------------------------------------+
    |                                                   |
    |            Halaman Web Demo (Full 1.0x)           |
    |                                                   |
    |         ( Langkah 1: Masuk dengan Akun )          | <- Pill Melayang (Auto-Dodge jika ada tombol)
    +---------------------------------------------------+
    ```
- Output File Path:
  - Default: `recordings/<scenario-name>.<ext>` (e.g. `recordings/login-flow.mp4` or `recordings/dashboard-navigation.gif`). Never use generic `demo.mp4` to avoid accidental overwrites.
  - Custom override: If the user specifies a custom path (e.g. `docs/assets/hero.gif`), save directly there.
- Temporary Staging and Strict Script Location:
  - Never create separate script folders like `scripts/`, `tmp/`, or root files.
  - Colocate the transient runner script AND raw video captures inside an isolated staging folder: `recordings/.temp/`.

### Step 3: Humanized Script Generation with Dynamic Tabler Cursors

Generate the self-contained runner script directly inside `recordings/.temp/runner.mjs`. Do not record at raw machine speed; human viewers need visual rhythm and readable transitions.

Key implementation patterns for `recordings/.temp/runner.mjs`:

1. Video directory setup: Ensure the temporary staging directory exists, configure `recordVideo` inside `browser.newContext()`, and initialize the mouse at the center of the viewport so the cursor never starts at `(0, 0)`:
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
   await page.mouse.move(VIEWPORT.width / 2, VIEWPORT.height / 2);
   const recordingStartMs = Date.now();
   const fastSegments = []; // Stores { start: sec, end: sec, speed: 1.75 } for FFmpeg speed ramping
   ```

2. Dynamic Tabler Vector Cursors (MIT Licensed), Session Persistence & Dual-Mode Step Overlay:
   Mount `#demo-cursor` and the step overlay (`#demo-step-bar` or `#demo-step-badge`) on `document.documentElement` (`<html>`) rather than `document.body`, and persist cursor coordinates (`__demoCursor`), active step text (`__demoStep`), and step mode (`__demoStepMode`: `'static-bar'` or `'floating'`) in `sessionStorage`. This guarantees:
   - **`'static-bar'` mode**: Splits the viewport into a **Dedicated Static Bottom Bar (`52px`, `#0f172a`)** and a **Scaled App Stage (`~0.92x`)** above it so the badge remains fixed at the bottom center without ever overlapping controls.
   - **`'floating'` mode**: Keeps the web page at full `1.0x` scale and renders a floating semi-transparent pill badge with automatic collision avoidance (`bottom-center` $\rightarrow$ `top-right` $\rightarrow$ `bottom-right` $\rightarrow$ `top-center`) when buttons or the cursor occupy the bottom center.
   - Across full-page navigations (`page.goto()` or form submits), the cursor stays at its last position instead of jumping back to `(0, 0)`, and the active step overlay is immediately restored:
   ```javascript
   await page.addInitScript(() => {
     const BAR_HEIGHT = 52;
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
         document.body.style.transform = `translate(${tx}px, ${ty}px) scale(${baseScale})`;
       } else {
         window.__demoCamera = { scale: 1, tx: 0, ty: 0, barHeight: 0 };
         document.body.style.transform = 'translate(0px, 0px) scale(1)';
       }
       if (!animate) {
         requestAnimationFrame(() => {
           if (document.body) document.body.style.transition = 'transform 0.48s cubic-bezier(0.22, 1, 0.36, 1)';
         });
       }
     };

     window.__checkBadgeCollision = (cx, cy) => {
       if (sessionStorage.getItem('__demoStepMode') !== 'floating') return;
       const badge = document.getElementById('demo-step-badge');
       if (!badge || badge.style.opacity === '0') return;
       const vw = window.innerWidth;
       const vh = window.innerHeight;
       const saved = (() => {
         try { return JSON.parse(sessionStorage.getItem('__demoCursor') || 'null'); } catch { return null; }
       })();
       const curX = cx ?? saved?.x ?? vw / 2;
       const curY = cy ?? saved?.y ?? vh / 2;

       const slots = [
         { name: 'bottom-center', x: vw / 2, y: vh - 44, top: 'auto', bottom: '28px', left: '50%', right: 'auto', transform: 'translateX(-50%) translateY(0)' },
         { name: 'top-right', x: vw - 160, y: 42, top: '20px', bottom: 'auto', left: 'auto', right: '24px', transform: 'translateY(0)' },
         { name: 'bottom-right', x: vw - 160, y: vh - 44, top: 'auto', bottom: '28px', left: 'auto', right: '24px', transform: 'translateY(0)' },
         { name: 'top-center', x: vw / 2, y: 42, top: '20px', bottom: 'auto', left: '50%', right: 'auto', transform: 'translateX(-50%) translateY(0)' }
       ];

       const isSlotBusy = (slot) => {
         if (Math.abs(curX - slot.x) < 210 && Math.abs(curY - slot.y) < 64) return true;
         for (const dx of [-80, 0, 80]) {
           const els = document.elementsFromPoint(slot.x + dx, slot.y);
           for (const el of els) {
             if (el.id === 'demo-step-badge' || el.id === 'demo-cursor') continue;
             if (el.closest('button, a, input, select, textarea, [role="button"], [role="tab"]')) return true;
           }
         }
         return false;
       };

       const chosen = slots.find((s) => !isSlotBusy(s)) || slots[0];
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
           badge.style.cssText = [
             'position:fixed',
             'bottom:28px',
             'left:50%',
             'transform:translateX(-50%) translateY(0)',
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
             'transition:opacity 0.25s ease, transform 0.25s ease, top 0.25s ease, bottom 0.25s ease, left 0.25s ease, right 0.25s ease'
           ].join(';');
           document.documentElement.appendChild(badge);
         }
         badge.textContent = text;
         badge.style.opacity = '1';
         window.__checkBadgeCollision();
         return;
       }

       // Default: 'static-bar' mode
       let bar = document.getElementById('demo-step-bar');
       let badge = document.getElementById('demo-step-badge');
       if (!bar) {
         if (badge) badge.remove();
         bar = document.createElement('div');
         bar.id = 'demo-step-bar';
         bar.style.cssText = [
           'position:fixed',
           'left:0',
           'right:0',
           'bottom:0',
           `height:${BAR_HEIGHT}px`,
           'background:#0f172a',
           'border-top:1px solid rgba(255, 255, 255, 0.12)',
           'display:flex',
           'align-items:center',
           'justify-content:center',
           'pointer-events:none',
           'z-index:999998'
         ].join(';');

         badge = document.createElement('div');
         badge.id = 'demo-step-badge';
         badge.style.cssText = [
           'padding:6px 18px',
           'background:rgba(30, 41, 59, 0.95)',
           'color:#f8fafc',
           'border:1px solid rgba(255, 255, 255, 0.18)',
           'border-radius:9999px',
           'font:600 14px/1.4 system-ui, -apple-system, sans-serif',
           'letter-spacing:0.01em',
           'box-shadow:0 4px 14px rgba(0, 0, 0, 0.3)',
           'transition:opacity 0.2s ease'
         ].join(';');
         bar.appendChild(badge);
         document.documentElement.appendChild(bar);
       }
       bar.style.display = 'flex';
       badge.textContent = text;
       badge.style.opacity = '1';
     };

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
         cursor.style.cssText = `position:fixed;top:${startY}px;left:${startX}px;pointer-events:none;z-index:999999;transform-origin:0 0;transform:scale(1);transition:transform 0.06s ease;will-change:left, top, transform;`;
         cursor.innerHTML = ICONS[currentState] || ICONS.default;
         document.documentElement.appendChild(cursor);
       }

       const savedStep = sessionStorage.getItem('__demoStep');
       const savedMode = sessionStorage.getItem('__demoStepMode') || 'static-bar';
       if (savedStep) {
         window.__renderStepBadge(savedStep, savedMode);
       }

       window.addEventListener('mousemove', (e) => {
         cursor.style.left = `${e.clientX}px`;
         cursor.style.top = `${e.clientY}px`;

         const el = document.elementFromPoint(e.clientX, e.clientY);
         if (el) {
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
         }
         try {
           sessionStorage.setItem('__demoCursor', JSON.stringify({ x: e.clientX, y: e.clientY, state: currentState }));
         } catch {}
         window.__checkBadgeCollision(e.clientX, e.clientY);
       });

       window.addEventListener('mousedown', () => cursor.style.transform = 'scale(0.85)');
       window.addEventListener('mouseup', () => cursor.style.transform = 'scale(1)');
     };

     if (document.readyState === 'loading') {
       window.addEventListener('DOMContentLoaded', initOverlays);
     } else {
       initOverlays();
     }
   });
   ```

3. Speed Ramping & Natural Pacing Helpers (Default: Active):
   - **Adaptive Typing (`humanType`)**: Short strings ($\le 15$ chars, such as short codes or usernames) type at normal speed (`85ms`/char). Longer strings ($> 15$ chars, such as emails, URLs, or descriptions) automatically ramp up to `1.5x–2x` speed (`40ms`/char) so typing never drags.
   - **Loading / Async Speed Ramping (`withSpeedRamp`)**: Wrap slow network submissions or loading spinners with `withSpeedRamp(async () => { ... }, 1.75)`. It records the exact `[start, end]` timestamps so FFmpeg can accelerate that segment by `1.5x–2x` during post-processing while keeping important UI reveals (modals, theme transitions, toasts) at `1x` speed (`await page.waitForTimeout(800)`).
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
   Smoothly zooms and pans the camera onto compact form controls or toggles within the App Stage area (respecting the `52px` Static Bottom Bar in `'static-bar'` mode or re-checking collision in `'floating'` mode), then resets back to the base stage (`~0.92x` with static bar, or `1x` full screen):
   ```javascript
   async function zoomTo(page, selector, scale = 1.65) {
     const loc = page.locator(selector).first();
     await loc.waitFor({ state: 'visible' });
     await page.evaluate(({ sel, targetScale }) => {
       const el = document.querySelector(sel);
       if (!el) return;
       const cam = window.__demoCamera || { scale: 1, tx: 0, ty: 0, barHeight: 0 };
       const rect = el.getBoundingClientRect();
       // Recover unscaled element center in viewport coordinates
       const cx0 = (rect.left + rect.width / 2 - cam.tx) / cam.scale;
       const cy0 = (rect.top + rect.height / 2 - cam.ty) / cam.scale;
       const vw = window.innerWidth;
       const vh = window.innerHeight;
       const barH = cam.barHeight || (sessionStorage.getItem('__demoStepMode') === 'static-bar' ? 52 : 0);
       const stageH = vh - barH;
       // Clamp translation to App Stage above the bottom bar
       const rawTx = vw / 2 - cx0 * targetScale;
       const rawTy = stageH / 2 - cy0 * targetScale;
       const tx = Math.max(vw * (1 - targetScale), Math.min(0, rawTx));
       const ty = Math.max(stageH - vh * targetScale, Math.min(0, rawTy));
       window.__demoCamera = { scale: targetScale, tx, ty, barHeight: barH };
       document.body.style.transform = `translate(${tx}px, ${ty}px) scale(${targetScale})`;
     }, { sel: selector, targetScale: scale });
     await page.waitForTimeout(520); // Wait for smooth camera zoom transition
     await page.evaluate(() => window.__checkBadgeCollision && window.__checkBadgeCollision());
   }

   async function resetZoom(page) {
     await page.evaluate(() => {
       if (window.__applyBaseStage) {
         window.__applyBaseStage(true);
       }
     });
     await page.waitForTimeout(520);
     await page.evaluate(() => window.__checkBadgeCollision && window.__checkBadgeCollision());
   }
   ```

5. Optional Helper: Step Callout / Visual Narration (Include ONLY when user opts in):
   - Pass `mode: 'static-bar'` (default recommended) or `mode: 'floating'` based on the user's choice in Step 2.
   - **Call Order Rule**: Always call `await showStep(page, 'Langkah X: ...', { mode })` **after** `page.goto()` has loaded and **before** `zoomTo()` or `moveAndClick()` begins:
   ```javascript
   async function showStep(page, stepText, { mode = 'static-bar' } = {}) {
     await page.waitForLoadState('domcontentloaded');
     await page.evaluate(({ text, stepMode }) => {
       const prevMode = sessionStorage.getItem('__demoStepMode');
       try {
         sessionStorage.setItem('__demoStepMode', stepMode);
         sessionStorage.setItem('__demoStep', text);
       } catch {}
       if (prevMode !== stepMode && window.__applyBaseStage) {
         window.__applyBaseStage(false);
       }
       if (window.__renderStepBadge) {
         window.__renderStepBadge(text, stepMode);
       }
     }, { text: stepText, stepMode: mode });
     await page.waitForTimeout(300); // Brief lead-in so viewer reads step before cursor moves
   }

   async function hideStep(page) {
     await page.evaluate(() => {
       try { sessionStorage.removeItem('__demoStep'); } catch {}
       const badge = document.getElementById('demo-step-badge');
       if (badge) {
         badge.style.opacity = '0';
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
- Overlay Scaling & Coordinate Drift during Auto-Zoom: Never append `#demo-cursor` or `#demo-step-badge` to `document.body` if `document.body` is zoomed with CSS `transform`. Always append overlays to `document.documentElement` (`<html>`) and wait (`520ms`) for the zoom transition to finish before calling `boundingBox()` or moving the mouse cursor.
- Cursor Reset to `(0, 0)` on Page Navigation: Always call `await page.mouse.move(VIEWPORT.width / 2, VIEWPORT.height / 2)` right after `context.newPage()` and persist cursor coordinates in `sessionStorage` (`__demoCursor`) so full-page navigations never snap the cursor back to the top-left corner `(0, 0)`.
- Step Bar Layout & Timing: When Step Callout is enabled, `window.__applyBaseStage()` scales `document.body` to `~0.92x` above a dedicated `52px` Static Bottom Bar (`#demo-step-bar`) so the step badge remains stationary at the bottom center without ever colliding with page controls or jumping between corners. Always call `showStep()` **after** `page.goto()` has loaded and **before** `zoomTo()` / `moveAndClick()` so viewers can read the step label while the cursor moves.
- Dynamic Spinners and Hydration: Use `waitForSelector` or `waitForLoadState('networkidle')` instead of arbitrary short sleeps to prevent recordings from capturing incomplete UI states, and wrap unavoidable slow loading waits in `withSpeedRamp()` so they can be accelerated `1.5x–2x`.
- Viewport Mismatch: Set both `viewport` and `recordVideo.size` to the exact same dimensions in `browser.newContext()` to avoid black borders or canvas scaling distortion.
- Headless Environment: Playwright video recording works reliably with `headless: true`. Do not force `headless: false` unless a virtual framebuffer (Xvfb) or active display server is guaranteed.
