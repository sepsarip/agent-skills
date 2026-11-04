# Record Web Demo Skill

> Automated screen recording for web applications using Playwright with humanized pacing, dynamic cursor simulation, and multi-format transcoding (MP4, WebM, GIF).

---

## 📌 Overview

Automated browser tests execute at machine speed: mouse coordinates teleport instantly, forms fill in milliseconds, and the operating system cursor is completely invisible in headless mode. While efficient for CI tests, these recordings are disorienting and unwatchable for human product demos, visual documentation, release changelogs, and GitHub READMEs.

The **`record-web-demo`** skill gives AI coding agents a deterministic, polished workflow to record web application walkthroughs. It injects dynamic, high-contrast vector cursors, applies humanized pacing with natural cursor trajectories, stages execution inside an isolated temporary directory, and transcodes raw captures into production-ready MP4 or GIF formats.

---

## ✨ Key Features

- **Dynamic Vector Cursors**: Injects MIT-licensed Tabler vector cursors into the browser DOM that dynamically switch between standard arrow, interactive pointer hand, and text I-beam with calibrated hotspots and click feedback (`scale(0.85)`).
- **Dual-Tone High Contrast**: Cursors feature white fills with dark borders and drop shadows, ensuring clear visibility across light, dark, and mixed application themes.
- **Humanized Interaction Pacing**: Simulates realistic human interactions using stepped cursor curves (`steps: 25`), character-by-character typing delays (`90ms`), and settle pauses (`800ms`) after state transitions or modals.
- **Isolated Atomic Staging**: Colocates transient runner scripts and raw video buffers inside `recordings/.temp/`, ensuring a clean workspace that purges completely in a single `rm -rf` command.
- **Multi-Format Export Pipeline**:
  - **Native WebM**: Direct Playwright video output without transcoding overhead.
  - **Optimized MP4**: H.264 video with `yuv420p` pixel format and `+faststart` flags for universal browser and mobile playback.
  - **Two-Pass Palettegen GIF**: High-fidelity animated GIFs utilizing Bayer dithering to eliminate color banding while minimizing file size for GitHub READMEs.
- **Headless-First Reliability**: Records full-fidelity video in headless environments without requiring a physical monitor or virtual framebuffer (Xvfb).

---

## 📂 Skill Architecture

```text
skills/record-web-demo/
├── SKILL.md                          # Core agent instructions, cursor SVGs & execution workflow
└── README.md                         # Human-readable documentation & reference guide
```

---

## 🔄 The 6-Step Recording Workflow

```mermaid
flowchart TD
    Step1["Step 1: Pre-flight Verification\n(Node.js, Playwright, ffmpeg)"] --> Step2["Step 2: Define Scenario & Destination\n(Resolution, Format, Output Path)"]
    Step2 --> Step3["Step 3: Generate Runner Script\n(Dynamic Cursors & Pacing in recordings/.temp/)"]
    Step3 --> Step4["Step 4: Execute Headless Recording\n(Capture Raw WebM Buffer)"]
    Step4 --> Step5["Step 5: Post-Processing & Transcoding\n(ffmpeg MP4 / GIF Conversion)"]
    Step5 --> Step6["Step 6: Atomic Cleanup & Verification\n(Purge .temp, Verify File Size)"]
```

### Step 1: Pre-flight Verification
Checks necessary runtime dependencies:
- Node.js environment (`node -v`)
- Playwright runner & Chromium browser (`npx -y playwright install chromium`)
- FFmpeg availability for transcoding (`ffmpeg -version`)

### Step 2: Define Scenario & Parameters
Establishes recording parameters before generating code:
- **Target URL**: Dev server (e.g. `http://localhost:3000`) or production deployment.
- **Dimensions**: 1280x720 (720p 16:9 standard for READMEs) or 1920x1080 (1080p).
- **Target Format**: WebM, MP4, or GIF.
- **Output Destination**: Standardized under `recordings/<scenario-name>.<ext>` (avoids generic `demo.mp4` collisions).

### Step 3: Script Generation with Dynamic Vector Cursors
Generates a self-contained runner script directly inside `recordings/.temp/runner.mjs`. Injects adaptive SVG cursors:
- **Default Arrow**: Calibrated at hotspot `(-4px, -4px)`.
- **Pointer Hand**: Automatically triggered when hovering over `button`, `a`, `[role="button"]`, or elements with `cursor: pointer`.
- **Text I-Beam**: Automatically triggered over inputs, textareas, and contenteditable elements.
- **Click Feedback**: Scales cursor to `0.85` on `mousedown` and restores to `1.0` on `mouseup`.

### Step 4: Execute Recording
Runs the headless script via Node.js, capturing the raw WebM buffer:
```bash
node recordings/.temp/runner.mjs
```

### Step 5: Post-Processing & Transcoding
Converts the raw WebM buffer to the requested target format:

- **Web-Optimized MP4**:
  ```bash
  ffmpeg -y -i recordings/.temp/<raw>.webm -c:v libx264 -pix_fmt yuv420p -movflags +faststart recordings/<scenario-name>.mp4
  ```

- **Optimized Two-Pass GIF**:
  ```bash
  ffmpeg -y -i recordings/.temp/<raw>.webm -filter_complex "[0:v] fps=15,scale=1280:-1:flags=lanczos,split [a][b];[a] palettegen=stats_mode=diff [p];[b][p] paletteuse=dither=bayer:bayer_scale=3" recordings/<scenario-name>.gif
  ```

### Step 6: Atomic Cleanup & Delivery
Purges the staging folder completely to leave zero transient artifacts:
```bash
rm -rf recordings/.temp
```
Verifies output file size and delivers the relative/absolute path to the user.

---

## 🛠️ Requirements & Prerequisites

| Requirement | Purpose | Recommended Version |
|---|---|---|
| **Node.js** | Script execution runtime | Node.js 18+ (LTS) |
| **Playwright** | Headless browser automation & video recording | `@playwright/test` or `playwright` |
| **Chromium** | Browser binary | Installed via `npx playwright install chromium` |
| **FFmpeg** | Video transcoding to MP4 and optimized GIF | 4.x / 5.x / 6.x (optional for native WebM) |

---

## 💡 Best Practices & Gotchas

- **Video Buffer Flush**: Playwright writes video frames asynchronously. Always await `context.close()` and `browser.close()` before moving or converting video files, otherwise files will be 0 bytes.
- **Viewport Synchronization**: Always match `viewport` and `recordVideo.size` in `browser.newContext()` to identical dimensions (e.g. `1280x720`) to prevent black borders or distortion.
- **Dynamic Selectors vs. Hardcoded Sleep**: Use `waitForSelector` or `waitForLoadState('networkidle')` before initiating interactions rather than arbitrary short sleeps.
- **Zero Directory Pollution**: Never place temporary scripts in root or create separate `scripts/` or `tmp/` folders in the target project. Keep transient assets confined to `recordings/.temp/`.
- **Git Hygiene**: Add `recordings/.temp/` and `recordings/` to `.gitignore` to avoid checking large video binaries into version control.

---

## 📄 License

This skill is distributed under the [MIT License](../../LICENSE).
Dynamic cursors are based on [Tabler Icons](https://github.com/tabler/tabler-icons) under the MIT License.
