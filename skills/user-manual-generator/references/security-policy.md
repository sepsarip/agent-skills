# Security Policy for user-manual-generator

This policy governs how the agent and bundled Python scripts interact with the user's system, browser, and files.

---

## 1. Sandbox-First & Virtual Environment Isolation

- **Standard Sandbox Mode**: All script executions must run inside Standard Sandbox Mode (`BypassSandbox: false`) whenever possible.
- **Isolated Virtual Environment**: If required dependencies (`Pillow`, `python-docx`, `playwright`, `pypdf`) are not installed on the system, scripts must be run inside a dedicated local virtual environment located inside the project workspace (e.g. `.venv-manual/`).
- **No Global System Pollution**: Never execute `sudo apt install`, global `pip install`, or bypass package management with `--break-system-packages` on the user's host OS.
- **Non-Destructive File Operations**: Scripts never run recursive directory deletions (`rm -rf` or `shutil.rmtree`) on workspace data. Output updates automatically archive previous versions to `docs/manual_book/archive/<basename>_<timestamp>/`.

---

## 2. File System & Path Traversal Protection

- **Workspace Containment**: All file read and write operations in `capture_and_annotate.py`, `build_manual.py`, and `manual_state.py` validate paths using `os.path.realpath`. Any path escaping the active workspace triggers an immediate error.
- **Restricted Extensions**: Image processing scripts only accept `.png`, `.jpg`, `.jpeg`, and `.webp` files. Document builders only write `.md` and `.docx` files.
- **Atomic File Writes**: Metadata and progress updates (`manual_progress.json`, `manual_spec.json`) use temporary files with `os.replace` to prevent corrupted states during unexpected terminations.

---

## 3. Browser Automation & Network Protocols

- **Supported Protocols**: `capture_and_annotate.py` permits standard `http://` and `https://` URLs, with full first-class support for `localhost` and local dev server addresses (e.g. `http://localhost:3000`, `http://127.0.0.1:8000`). Dangerous local file schemes such as `file://`, `javascript:`, and `data:` are rejected immediately.
- **Bounded Timeouts**: Browser navigation and screenshot actions enforce strict timeouts (default 30 seconds) and automatically close headless browser contexts.

---

## 4. Subprocess & Renderer Safety

- **Zero Shell Evaluation**: All invocations (including LibreOffice PDF export in `build_manual.py`) use strict argument lists via `subprocess.run(..., shell=False)` with explicit timeouts.
- **Isolated User Profiles**: Headless LibreOffice conversions use isolated, temporary user profiles (`-env:UserInstallation=file:///tmp/lo_prof_*`) that are cleaned up after execution, preventing collision with user desktop LibreOffice instances.
- **Image Bomb Protection**: Pillow's `Image.MAX_IMAGE_PIXELS` limit remains enabled (capped at 80 million pixels) to prevent decompression bomb attacks on untrusted images.
