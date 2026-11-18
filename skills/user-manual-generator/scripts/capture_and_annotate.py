#!/usr/bin/env python3
"""
Safe High-DPI Screenshot Auto-Capture, Layout Mapping, Coordinate Grid Generator,
and Collision-Free Arrow Annotator with Automatic Text Occlusion Avoidance.
Designed for the user-manual-generator Agent Skill.
"""

import argparse
import json
import math
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    # Protect against decompression bombs
    Image.MAX_IMAGE_PIXELS = 80_000_000
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from annotate_cairo import (
    HAVE_CAIRO,
    circle_intersects_rect,
    compute_annotation_scale,
    detect_cairo_surface_obstacles,
    draw_badge_and_arrow as cairo_draw_badge_and_arrow,
    draw_bounding_highlight as cairo_draw_bounding_highlight,
    rect_intersects_segment,
)
if HAVE_CAIRO:
    import cairo

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def validate_workspace_path(target_path: str, must_exist: bool = False) -> str:
    """Ensure the target path resides within the current working directory."""
    cwd = os.path.realpath(os.getcwd())
    real_target = os.path.realpath(target_path)
    if not (real_target == cwd or real_target.startswith(cwd + os.sep)):
        raise ValueError(
            f"Security Error: Path '{target_path}' escapes the active workspace '{cwd}'."
        )
    ext = os.path.splitext(real_target)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTS and not target_path.endswith(".json"):
        raise ValueError(
            f"Validation Error: Unsupported image extension '{ext}'. Allowed: {sorted(ALLOWED_IMAGE_EXTS)}"
        )
    if must_exist and not os.path.isfile(real_target):
        raise FileNotFoundError(f"Input file not found: {real_target}")
    parent_dir = os.path.dirname(real_target)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
    return real_target


def validate_url(url: str) -> str:
    """Validate that URL uses http or https scheme with a valid host (including localhost)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            f"Validation Error: Only http and https URLs are permitted (e.g. 'http://localhost:3000', 'https://example.com'). Got '{parsed.scheme}'."
        )
    if not (parsed.netloc or parsed.hostname):
        raise ValueError("Validation Error: URL must include a valid host (e.g. 'localhost:3000' or 'example.com').")
    return url


# ---------------------------------------------------------
# Capture & Layout Mapping
# ---------------------------------------------------------
def _find_chromium_executable(playwright_obj: Any) -> Optional[str]:
    """Locate Playwright or system Chromium binary without triggering network downloads."""
    try:
        exec_path = playwright_obj.chromium.executable_path
        if exec_path and os.path.isfile(exec_path):
            return exec_path
    except Exception:
        pass

    cache_roots = [
        os.path.join(os.getcwd(), ".venv-manual", "ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
    ]
    for root in cache_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for cand_name in ("chrome", "chrome-headless-shell", "chromium"):
                if cand_name in filenames:
                    cand = os.path.join(dirpath, cand_name)
                    if os.access(cand, os.X_OK):
                        return cand

    for bin_name in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge"):
        found = shutil.which(bin_name)
        if found:
            return found
    return None


def _resolve_spec_asset(raw_path: str, spec_dir: str, must_exist: bool = False) -> str:
    """Resolve a path from manual_spec.json safely within the workspace."""
    if not raw_path:
        return ""
    norm = raw_path.replace("\\", "/")
    if norm.startswith("assets/"):
        return validate_workspace_path(os.path.join(spec_dir, raw_path), must_exist=must_exist)
    primary = validate_workspace_path(raw_path, must_exist=False)
    if os.path.exists(primary):
        return primary
    assets_idx = norm.find("assets/")
    if assets_idx >= 0:
        cand = validate_workspace_path(os.path.join(spec_dir, norm[assets_idx:]), must_exist=False)
        if os.path.exists(cand) or not must_exist:
            return cand
    return validate_workspace_path(raw_path, must_exist=must_exist)


def _capture_single_page(
    page: Any,
    url: str,
    out_path: str,
    width: int,
    height: int,
    scale: int,
    wait_ms: int,
    full_page: bool,
    mask_selectors: List[str],
    target_specs: List[str],
) -> None:
    """Navigate to url, extract DOM text & target bounding boxes, and save high-DPI screenshot."""
    try:
        page.goto(url, wait_until="networkidle")
    except Exception:
        page.goto(url, wait_until="domcontentloaded")

    if wait_ms > 0:
        page.wait_for_timeout(wait_ms)

    # Lock scroll at top before DOM geometry extraction so boxes align with screenshot
    page.evaluate("() => window.scrollTo(0, 0)")

    layout_data: Dict[str, Any] = {
        "url": url,
        "scale": scale,
        "width": width * scale,
        "height": height * scale,
        "text_rects": [],
        "target_boxes": [],
    }

    js_script = """
    () => {
        const rects = [];
        const walker = document.createTreeWalker(
            document.body,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: (node) => {
                    if (!node.textContent || !node.textContent.trim()) return NodeFilter.FILTER_REJECT;
                    const el = node.parentElement;
                    if (!el) return NodeFilter.FILTER_REJECT;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );

        while (walker.nextNode()) {
            const node = walker.currentNode;
            const range = document.createRange();
            range.selectNodeContents(node);
            const clientRects = range.getClientRects();
            for (let i = 0; i < clientRects.length; i++) {
                const r = clientRects[i];
                if (r.width > 2 && r.height > 2) {
                    rects.push({
                        x: r.left + window.scrollX,
                        y: r.top + window.scrollY,
                        w: r.width,
                        h: r.height,
                        text: node.textContent.trim().slice(0, 30)
                    });
                }
            }
        }
        return rects;
    }
    """
    raw_text_rects = page.evaluate(js_script)
    for r in raw_text_rects:
        layout_data["text_rects"].append(
            {
                "x1": r["x"] * scale,
                "y1": r["y"] * scale,
                "x2": (r["x"] + r["w"]) * scale,
                "y2": (r["y"] + r["h"]) * scale,
                "text": r["text"],
            }
        )

    for t_spec in target_specs:
        label = ""
        selector = t_spec
        if "=" in t_spec:
            parts = t_spec.split("=", 1)
            label = parts[0].strip()
            selector = parts[1].strip()

        loc = page.locator(selector).first
        if loc.count() == 0:
            print(f"[WARNING] Target selector '{selector}' not found in DOM.")
            continue
        bbox = loc.bounding_box()
        if not bbox:
            print(f"[WARNING] Target selector '{selector}' has no bounding box.")
            continue

        layout_data["target_boxes"].append(
            {
                "label": label,
                "selector": selector,
                "x1": bbox["x"] * scale,
                "y1": bbox["y"] * scale,
                "x2": (bbox["x"] + bbox["width"]) * scale,
                "y2": (bbox["y"] + bbox["height"]) * scale,
            }
        )

    mask_locators = [page.locator(sel) for sel in mask_selectors]
    screenshot_kwargs: Dict[str, Any] = {
        "path": out_path,
        "full_page": full_page,
        "mask": mask_locators if mask_locators else None,
        "animations": "disabled",
        "caret": "hide",
        "scale": "device",
    }
    try:
        page.screenshot(**screenshot_kwargs)
    except TypeError:
        page.screenshot(
            path=out_path,
            full_page=full_page,
            mask=mask_locators if mask_locators else None,
        )

    layout_path = f"{os.path.splitext(out_path)[0]}.layout.json"
    with open(layout_path, "w", encoding="utf-8") as f:
        json.dump(layout_data, f, indent=2)

    print(f"[OK] High-DPI screenshot saved to: {out_path}")
    print(f"[OK] Layout map sidecar saved to: {layout_path}")


def _collect_capture_tasks_from_spec(spec_path: str, force: bool = False) -> List[Dict[str, Any]]:
    """Collect figure capture tasks from manual_spec.json."""
    spec_dir = os.path.dirname(spec_path)
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    tasks: List[Dict[str, Any]] = []
    for ch in spec.get("chapters", []):
        for sec in ch.get("sections", []):
            for fig in sec.get("figures", []):
                src = fig.get("source") or {}
                url = str(src.get("url", "")).strip()
                raw_rel = str(src.get("raw", "")).strip()
                if not url or not raw_rel:
                    continue
                out_path = _resolve_spec_asset(raw_rel, spec_dir, must_exist=False)
                if os.path.isfile(out_path) and not force:
                    continue
                tasks.append(
                    {
                        "id": str(fig.get("id", "")),
                        "url": validate_url(url),
                        "output": out_path,
                        "targets": [str(t) for t in src.get("targets", [])],
                    }
                )
    return tasks


def cmd_capture(args: argparse.Namespace) -> None:
    """Capture crisp high-DPI screenshot(s) from URL or manual_spec.json."""
    mask_selectors = [s.strip() for s in args.mask_selectors.split(",") if s.strip()]

    if getattr(args, "spec", ""):
        spec_path = validate_workspace_path(args.spec, must_exist=True)
        tasks = _collect_capture_tasks_from_spec(spec_path, force=getattr(args, "force", False))
        if not tasks:
            print("[OK] No pending URL screenshots to capture from spec (use --force to recapture).")
            return
    else:
        if not args.url or not args.output:
            raise ValueError("Validation Error: Provide either --spec or both --url and --output.")
        tasks = [
            {
                "id": "",
                "url": validate_url(args.url),
                "output": validate_workspace_path(args.output, must_exist=False),
                "targets": args.target or [],
            }
        ]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "Error: Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
        )

    with sync_playwright() as p:
        launch_kwargs: Dict[str, Any] = {"headless": True}
        default_exec = getattr(p.chromium, "executable_path", "")
        if not (default_exec and os.path.isfile(default_exec)):
            found_exec = _find_chromium_executable(p)
            if found_exec:
                launch_kwargs["executable_path"] = found_exec

        browser = p.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(
                viewport={"width": args.width, "height": args.height},
                device_scale_factor=args.scale,
            )
            page = context.new_page()
            page.set_default_timeout(args.timeout * 1000)

            for item in tasks:
                out_dir = os.path.dirname(item["output"])
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                _capture_single_page(
                    page=page,
                    url=item["url"],
                    out_path=item["output"],
                    width=args.width,
                    height=args.height,
                    scale=args.scale,
                    wait_ms=args.wait_ms,
                    full_page=args.full_page,
                    mask_selectors=mask_selectors,
                    target_specs=item["targets"],
                )
        finally:
            browser.close()


# ---------------------------------------------------------
# Grid Helper
# ---------------------------------------------------------
def _load_font(size: int) -> Any:
    """Load a clean sans-serif font with scalable Pillow 10.1+ fallback."""
    if not HAVE_PIL:
        return None
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ]
    for path in font_candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def cmd_grid(args: argparse.Namespace) -> None:
    """Create a temporary coordinate grid overlay image for accurate arrow placement."""
    if not HAVE_PIL:
        sys.exit(
            "Error: Pillow (PIL) is required for grid generation.\n"
            "Install Pillow via pip, or inspect coordinates via image viewer."
        )
    in_path = validate_workspace_path(args.input, must_exist=True)
    out_path = validate_workspace_path(args.output, must_exist=False)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with Image.open(in_path).convert("RGBA") as base:
        width, height = base.size
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        step = max(25, args.step)
        half_step = step // 2
        font = _load_font(max(14, step // 6))

        for x in range(0, width, half_step):
            draw.line([(x, 0), (x, height)], fill=(0, 180, 255, 70), width=1)
        for y in range(0, height, half_step):
            draw.line([(0, y), (width, y)], fill=(0, 180, 255, 70), width=1)

        for x in range(0, width, step):
            draw.line([(x, 0), (x, height)], fill=(255, 50, 50, 160), width=2)
        for y in range(0, height, step):
            draw.line([(0, y), (width, y)], fill=(255, 50, 50, 160), width=2)

        for x in range(0, width, step):
            for y in range(0, height, step):
                if x == 0 and y == 0:
                    continue
                label = f"{x},{y}"
                bbox = draw.textbbox((x + 4, y + 4), label, font=font)
                draw.rectangle(
                    [bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1],
                    fill=(0, 0, 0, 175),
                )
                draw.text((x + 4, y + 4), label, fill=(255, 255, 0, 255), font=font)

        combined = Image.alpha_composite(base, overlay).convert("RGB")
        combined.save(out_path, quality=95)
        print(f"[OK] Grid helper image ({width}x{height}px) saved to: {out_path}")


# ---------------------------------------------------------
# Collision Detection & Arrow Geometry
# ---------------------------------------------------------
def detect_image_dense_obstacles(img: Any) -> List[Dict[str, float]]:
    """Detect textual/content regions from screenshot pixels using edge filtering."""
    if not HAVE_PIL:
        return []
    gray = img.convert("L").filter(ImageFilter.FIND_EDGES)
    width, height = gray.size
    cell_size = 30
    cols = max(1, width // cell_size)
    rows = max(1, height // cell_size)

    # Downsample edge image to grid resolution for instant density analysis
    grid_map = gray.resize((cols, rows), Image.Resampling.BILINEAR)
    grid_bytes = grid_map.tobytes()

    dense_rects: List[Dict[str, float]] = []
    threshold = 24

    for r in range(rows):
        row_offset = r * cols
        for c in range(cols):
            val = grid_bytes[row_offset + c]
            if val > threshold:
                dense_rects.append(
                    {
                        "x1": float(c * cell_size),
                        "y1": float(r * cell_size),
                        "x2": float(min(width, (c + 1) * cell_size)),
                        "y2": float(min(height, (r + 1) * cell_size)),
                    }
                )
    return dense_rects


def find_optimal_arrow_placement(
    target_box: Dict[str, float],
    label: str,
    obstacles: List[Dict[str, float]],
    img_width: int,
    img_height: int,
    stroke_width: int = 8,
    grid_snap: int = 10,
) -> Tuple[float, float, float, float]:
    """
    Search candidate angles and compact lengths to find a collision-free arrow.
    Points to target boundary; tail and badge reside in clear whitespace, snapped to grid.
    """
    bx1, by1 = target_box["x1"], target_box["y1"]
    bx2, by2 = target_box["x2"], target_box["y2"]
    center_x = (bx1 + bx2) / 2.0
    center_y = (by1 + by2) / 2.0

    scale = compute_annotation_scale(img_width, img_height)
    eff_stroke = max(stroke_width, int(round(stroke_width * scale)))
    badge_radius = max(int(round(20 * scale)), int(eff_stroke * 2.5))
    clearance = max(int(round(8 * scale)), eff_stroke + int(round(4 * scale)))

    preferred_angles = [
        math.pi,          # Left (180 deg)
        0.0,              # Right (0 deg)
        -math.pi / 2,     # Top (270 deg)
        math.pi / 2,      # Bottom (90 deg)
        math.pi * 0.85,
        math.pi * 1.15,
        -math.pi * 0.15,
        math.pi * 0.15,
        -math.pi * 0.4,
        -math.pi * 0.6,
        math.pi * 0.4,
        math.pi * 0.6,
        math.pi * 0.75,
        math.pi * 1.25,
        -math.pi * 0.25,
        math.pi * 0.25,
    ]

    # Compact lengths scaled to image resolution so arrows stay proportional on Retina captures
    candidate_lengths = [int(round(L * scale)) for L in (45, 65, 85, 110, 140)]

    best_cand = None
    min_penalty = float("inf")

    for angle in preferred_angles:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        tx = center_x
        ty = center_y
        if abs(cos_a) > 1e-4:
            x_edge = bx1 if cos_a < 0 else bx2
            t_edge = (x_edge - center_x) / cos_a
            y_at_edge = center_y + t_edge * sin_a
            if by1 <= y_at_edge <= by2:
                tx = x_edge
                ty = y_at_edge

        if tx == center_x:
            y_edge = by1 if sin_a < 0 else by2
            t_edge = (y_edge - center_y) / sin_a if abs(sin_a) > 1e-4 else 0
            x_at_edge = center_x + t_edge * cos_a
            tx = x_at_edge
            ty = y_edge

        head_x = tx + (cos_a * 4.0 * scale)
        head_y = ty + (sin_a * 4.0 * scale)

        for length in candidate_lengths:
            raw_tail_x = head_x + (cos_a * length)
            raw_tail_y = head_y + (sin_a * length)

            # Snap tail coordinates to guide grid
            if grid_snap > 1:
                tail_x = round(raw_tail_x / grid_snap) * grid_snap
                tail_y = round(raw_tail_y / grid_snap) * grid_snap
            else:
                tail_x = raw_tail_x
                tail_y = raw_tail_y

            margin = badge_radius + int(round(8 * scale))
            if not (margin <= tail_x <= img_width - margin and margin <= tail_y <= img_height - margin):
                continue
            if not (8 <= head_x <= img_width - 8 and 8 <= head_y <= img_height - 8):
                continue

            if circle_intersects_rect(tail_x, tail_y, badge_radius + 4 * scale, bx1, by1, bx2, by2):
                continue

            has_badge_collision = False
            for obs in obstacles:
                if obs is target_box:
                    continue
                ox1, oy1 = min(obs["x1"], obs["x2"]), min(obs["y1"], obs["y2"])
                ox2, oy2 = max(obs["x1"], obs["x2"]), max(obs["y1"], obs["y2"])
                if ox1 <= bx1 + 2 and oy1 <= by1 + 2 and ox2 >= bx2 - 2 and oy2 >= by2 - 2:
                    continue
                if circle_intersects_rect(
                    tail_x, tail_y, badge_radius + clearance,
                    ox1, oy1, ox2, oy2
                ):
                    has_badge_collision = True
                    break
            if has_badge_collision:
                continue

            has_shaft_collision = False
            for obs in obstacles:
                if obs is target_box:
                    continue
                ox1, oy1 = min(obs["x1"], obs["x2"]), min(obs["y1"], obs["y2"])
                ox2, oy2 = max(obs["x1"], obs["x2"]), max(obs["y1"], obs["y2"])
                if ox1 <= bx1 + 2 and oy1 <= by1 + 2 and ox2 >= bx2 - 2 and oy2 >= by2 - 2:
                    continue
                # Ignore obstacles located inside the target element itself
                if ox1 >= bx1 - 6 and ox2 <= bx2 + 6 and oy1 >= by1 - 6 and oy2 <= by2 + 6:
                    continue
                # Ignore small pixel-density cells straddling the arrow tip on the target border
                if (ox2 - ox1) <= 35 and (oy2 - oy1) <= 35:
                    if (ox1 - 8 * scale) <= head_x <= (ox2 + 8 * scale) and (oy1 - 8 * scale) <= head_y <= (oy2 + 8 * scale):
                        continue
                if rect_intersects_segment(
                    ox1, oy1, ox2, oy2,
                    tail_x, tail_y, head_x, head_y,
                    pad=clearance
                ):
                    has_shaft_collision = True
                    break
            if has_shaft_collision:
                continue

            dir_penalty = 0.0 if abs(sin_a) < 0.3 else (15.0 if abs(cos_a) < 0.3 else 30.0)
            # Power penalty strongly favors shortest clean arrow
            penalty = (length ** 1.3) + dir_penalty

            if penalty < min_penalty:
                min_penalty = penalty
                best_cand = (float(tail_x), float(tail_y), float(head_x), float(head_y))

    if best_cand:
        return best_cand

    # Compact fallback placement scaled to image resolution
    fallback_len = 55.0 * scale
    if center_x < img_width * 0.3:
        head_x = bx2
        head_y = center_y
        tail_x = min(img_width - badge_radius - 10 * scale, head_x + fallback_len)
        tail_y = head_y
    else:
        head_x = bx1
        head_y = center_y
        tail_x = max(badge_radius + 10 * scale, head_x - fallback_len)
        tail_y = head_y

    if grid_snap > 1:
        tail_x = round(tail_x / grid_snap) * grid_snap
        tail_y = round(tail_y / grid_snap) * grid_snap

    return (float(tail_x), float(tail_y), float(head_x), float(head_y))


# ---------------------------------------------------------
# Drawing & Annotation
# ---------------------------------------------------------
def _draw_pillow_highlight_box(
    draw: Any,
    bx1: float,
    by1: float,
    bx2: float,
    by2: float,
    color: Tuple[int, int, int] = (230, 30, 40),
    pad: float = 4.0,
    scale: float = 1.0,
) -> None:
    """Draw a rounded highlight box with white contrast border using Pillow."""
    scaled_pad = pad * scale
    rad = max(2, int(round(6 * scale)))
    w_outer = max(3, int(round(5 * scale)))
    w_inner = max(2, int(round(3 * scale)))
    outer = [bx1 - scaled_pad - 1, by1 - scaled_pad - 1, bx2 + scaled_pad + 1, by2 + scaled_pad + 1]
    inner = [bx1 - scaled_pad, by1 - scaled_pad, bx2 + scaled_pad, by2 + scaled_pad]
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(outer, radius=rad, outline=(255, 255, 255), width=w_outer)
        draw.rounded_rectangle(inner, radius=rad, outline=color, width=w_inner)
    else:
        draw.rectangle(outer, outline=(255, 255, 255), width=w_outer)
        draw.rectangle(inner, outline=color, width=w_inner)


def _draw_arrow_with_callout(
    draw: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    label: str = "",
    color: Tuple[int, int, int] = (230, 30, 40),
    width: int = 8,
) -> None:
    """Draw a high-contrast arrow with a white border and optional numbered badge at tail."""
    angle = math.atan2(y2 - y1, x2 - x1)
    head_len = max(24, width * 3.5)
    head_angle = math.pi / 6

    shaft_end_x = x2 - (head_len * 0.7) * math.cos(angle)
    shaft_end_y = y2 - (head_len * 0.7) * math.sin(angle)

    p1 = (x2, y2)
    p2 = (
        x2 - head_len * math.cos(angle - head_angle),
        y2 - head_len * math.sin(angle - head_angle),
    )
    p3 = (
        x2 - head_len * math.cos(angle + head_angle),
        y2 - head_len * math.sin(angle + head_angle),
    )

    draw.line([(x1, y1), (shaft_end_x, shaft_end_y)], fill=(255, 255, 255), width=width + 6)
    draw.polygon([p1, p2, p3], fill=(255, 255, 255), outline=(255, 255, 255))

    draw.line([(x1, y1), (shaft_end_x, shaft_end_y)], fill=color, width=width)
    draw.polygon([p1, p2, p3], fill=color)

    if label:
        radius = max(20, int(width * 2.5))
        draw.ellipse(
            [x1 - radius - 3, y1 - radius - 3, x1 + radius + 3, y1 + radius + 3],
            fill=(255, 255, 255),
        )
        draw.ellipse(
            [x1 - radius, y1 - radius, x1 + radius, y1 + radius],
            fill=color,
        )
        font = _load_font(int(radius * 1.2))
        try:
            draw.text((x1, y1), label, fill=(255, 255, 255), font=font, anchor="mm")
        except ValueError:
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text(
                (x1 - tw / 2, y1 - th / 2 - bbox[1] / 2),
                label,
                fill=(255, 255, 255),
                font=font,
            )


def _arrow_hits_obstacles(
    ax1: float,
    ay1: float,
    ax2: float,
    ay2: float,
    badge_r: float,
    obstacles: List[Dict[str, float]],
    target_box: Optional[Dict[str, float]] = None,
) -> bool:
    """Return True if badge or shaft collides with non-target UI obstacles."""
    for obs in obstacles:
        ox1, oy1 = min(obs["x1"], obs["x2"]), min(obs["y1"], obs["y2"])
        ox2, oy2 = max(obs["x1"], obs["x2"]), max(obs["y1"], obs["y2"])
        if target_box is not None:
            if obs is target_box:
                continue
            bx1, by1 = min(target_box["x1"], target_box["x2"]), min(target_box["y1"], target_box["y2"])
            bx2, by2 = max(target_box["x1"], target_box["x2"]), max(target_box["y1"], target_box["y2"])
            if ox1 <= bx1 + 2 and oy1 <= by1 + 2 and ox2 >= bx2 - 2 and oy2 >= by2 - 2:
                continue
        if circle_intersects_rect(ax1, ay1, badge_r, ox1, oy1, ox2, oy2):
            return True
        if target_box is not None:
            if ox1 >= bx1 - 6 and ox2 <= bx2 + 6 and oy1 >= by1 - 6 and oy2 <= by2 + 6:
                continue
        if (ox2 - ox1) <= 35 and (oy2 - oy1) <= 35:
            if (ox1 - 8) <= ax2 <= (ox2 + 8) and (oy1 - 8) <= ay2 <= (oy2 + 8):
                continue
        if rect_intersects_segment(ox1, oy1, ox2, oy2, ax1, ay1, ax2, ay2, pad=6.0):
            return True
    return False


def _parse_boxes(args: argparse.Namespace) -> List[Tuple[float, float, float, float]]:
    """Parse --box (x1,y1,x2,y2) and --box-xywh (x,y,w,h) into normalized (x1,y1,x2,y2) tuples."""
    parsed: List[Tuple[float, float, float, float]] = []
    for box_spec in getattr(args, "box", None) or []:
        parts = [p.strip() for p in box_spec.split(",")]
        if len(parts) != 4:
            raise ValueError(f"Invalid --box format '{box_spec}'. Expected 'x1,y1,x2,y2'.")
        b1, b2, b3, b4 = map(float, parts)
        parsed.append((min(b1, b3), min(b2, b4), max(b1, b3), max(b2, b4)))
    for xywh_spec in getattr(args, "box_xywh", None) or []:
        parts = [p.strip() for p in xywh_spec.split(",")]
        if len(parts) != 4:
            raise ValueError(f"Invalid --box-xywh format '{xywh_spec}'. Expected 'x,y,w,h'.")
        bx, by, bw, bh = map(float, parts)
        parsed.append((bx, by, bx + max(1.0, bw), by + max(1.0, bh)))
    return parsed


def _parse_numeric_target(t_arg: str, default_label: str) -> Optional[Dict[str, Any]]:
    """Parse 'x1,y1,x2,y2[,label]' into a target box dict; ignore CSS selector strings."""
    parts = [p.strip() for p in t_arg.split(",")]
    if len(parts) < 4:
        return None
    try:
        x1, y1, x2, y2 = map(float, parts[:4])
    except ValueError:
        return None
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "label": parts[4] if len(parts) > 4 else default_label,
    }


def _resolve_annotations(
    args: argparse.Namespace,
    width: int,
    height: int,
    obstacles: List[Dict[str, float]],
    layout_data: Optional[Dict[str, Any]],
    badge_r_check: float,
) -> Tuple[List[Tuple[float, float, float, float]], List[Dict[str, Any]], int]:
    """Compute highlight boxes, collision-free arrows, and unresolved collision counts once."""
    boxes_to_draw: List[Tuple[float, float, float, float]] = list(_parse_boxes(args))
    final_arrows: List[Dict[str, Any]] = []
    unresolved_collisions = 0
    snap = getattr(args, "grid_snap", 10) or 10
    scale = compute_annotation_scale(width, height)
    obs_pad = 15.0 * scale
    step_unit = max(snap, int(round(snap * scale)))

    if getattr(args, "auto", False):
        targets_to_place: List[Dict[str, Any]] = []
        if layout_data and layout_data.get("target_boxes"):
            targets_to_place.extend(layout_data["target_boxes"])

        for t_arg in getattr(args, "target", None) or []:
            parsed = _parse_numeric_target(t_arg, str(len(targets_to_place) + 1))
            if parsed:
                targets_to_place.append(parsed)

        if not targets_to_place and not getattr(args, "arrow", None):
            print(
                "[WARNING] --auto specified, but no target boxes found in layout sidecar (.layout.json) or --target flags. No auto arrows were placed."
            )

        obstacles.extend(targets_to_place)

        for target in targets_to_place:
            if getattr(args, "draw_target_boxes", False):
                tx1, ty1 = min(target["x1"], target["x2"]), min(target["y1"], target["y2"])
                tx2, ty2 = max(target["x1"], target["x2"]), max(target["y1"], target["y2"])
                boxes_to_draw.append((tx1, ty1, tx2, ty2))

            lbl = str(target.get("label") or len(final_arrows) + 1)
            ax1, ay1, ax2, ay2 = find_optimal_arrow_placement(
                target,
                lbl,
                obstacles,
                width,
                height,
                stroke_width=args.stroke_width,
                grid_snap=snap,
            )
            still_collides = (not args.allow_overlap) and _arrow_hits_obstacles(
                ax1, ay1, ax2, ay2, badge_r_check, obstacles, target_box=target
            )
            if still_collides:
                unresolved_collisions += 1
                print(
                    f"[WARNING] Auto arrow '{lbl}' at ({ax1:.0f},{ay1:.0f})->({ax2:.0f},{ay2:.0f}) still overlaps UI obstacles."
                )
            obstacles.append(
                {
                    "x1": min(ax1, ax2) - obs_pad,
                    "y1": min(ay1, ay2) - obs_pad,
                    "x2": max(ax1, ax2) + obs_pad,
                    "y2": max(ay1, ay2) + obs_pad,
                }
            )
            final_arrows.append(
                {
                    "x1": ax1,
                    "y1": ay1,
                    "x2": ax2,
                    "y2": ay2,
                    "label": lbl,
                    "auto": True,
                    "collided": still_collides,
                }
            )

    for arrow_spec in getattr(args, "arrow", None) or []:
        parts = [p.strip() for p in arrow_spec.split(",")]
        if len(parts) not in (4, 5):
            raise ValueError(
                f"Invalid --arrow format '{arrow_spec}'. Expected 'x1,y1,x2,y2' or 'x1,y1,x2,y2,label'."
            )
        ax1, ay1, ax2, ay2 = map(float, parts[:4])
        label = parts[4] if len(parts) == 5 else ""

        badge_r = max(int(round(20 * scale)), int(round(args.stroke_width * 2.5 * scale)))
        if _arrow_hits_obstacles(ax1, ay1, ax2, ay2, badge_r, obstacles) and not args.allow_overlap:
            nudge_offsets = [
                (0, -step_unit), (0, step_unit), (-step_unit, 0), (step_unit, 0),
                (-step_unit, -step_unit), (step_unit, -step_unit), (-step_unit, step_unit), (step_unit, step_unit),
                (0, -2 * step_unit), (0, 2 * step_unit), (-2 * step_unit, 0), (2 * step_unit, 0),
            ]
            resolved_nudge = None
            for dx, dy in nudge_offsets:
                test_x1, test_y1 = ax1 + dx, ay1 + dy
                if not (badge_r <= test_x1 <= width - badge_r and badge_r <= test_y1 <= height - badge_r):
                    continue
                if not _arrow_hits_obstacles(test_x1, test_y1, ax2, ay2, badge_r + 4 * scale, obstacles):
                    resolved_nudge = (test_x1, test_y1)
                    break

            if resolved_nudge:
                new_x1, new_y1 = resolved_nudge
                print(
                    f"[GRID-NUDGE] Arrow '{label}' nudged along grid from ({ax1:.0f},{ay1:.0f}) to ({new_x1:.0f},{new_y1:.0f}) to avoid occlusion."
                )
                ax1, ay1 = new_x1, new_y1
            else:
                fake_target = {
                    "x1": ax2 - 10 * scale,
                    "y1": ay2 - 10 * scale,
                    "x2": ax2 + 10 * scale,
                    "y2": ay2 + 10 * scale,
                }
                new_x1, new_y1, new_x2, new_y2 = find_optimal_arrow_placement(
                    fake_target,
                    label,
                    obstacles,
                    width,
                    height,
                    stroke_width=args.stroke_width,
                    grid_snap=snap,
                )
                print(
                    f"[AUTO-ADJUST] Arrow '{label}' adjusted from ({ax1:.0f},{ay1:.0f}) to ({new_x1:.0f},{new_y1:.0f}) to avoid text occlusion."
                )
                ax1, ay1, ax2, ay2 = new_x1, new_y1, new_x2, new_y2

        still_collides = (not args.allow_overlap) and _arrow_hits_obstacles(
            ax1, ay1, ax2, ay2, badge_r_check, obstacles
        )
        if still_collides:
            unresolved_collisions += 1
            print(
                f"[WARNING] Arrow '{label}' at ({ax1:.0f},{ay1:.0f})->({ax2:.0f},{ay2:.0f}) still overlaps UI obstacles."
            )

        obstacles.append(
            {
                "x1": min(ax1, ax2) - obs_pad,
                "y1": min(ay1, ay2) - obs_pad,
                "x2": max(ax1, ax2) + obs_pad,
                "y2": max(ay1, ay2) + obs_pad,
            }
        )
        final_arrows.append(
            {
                "x1": ax1,
                "y1": ay1,
                "x2": ax2,
                "y2": ay2,
                "label": label,
                "auto": False,
                "collided": still_collides,
            }
        )

    return boxes_to_draw, final_arrows, unresolved_collisions


def _write_arrows_audit(
    out_path: str,
    engine_name: str,
    unresolved_collisions: int,
    final_arrows: List[Dict[str, Any]],
) -> None:
    arrows_audit = f"{os.path.splitext(out_path)[0]}.arrows.json"
    with open(arrows_audit, "w", encoding="utf-8") as f:
        json.dump(
            {
                "image": out_path,
                "engine": engine_name,
                "unresolved_collisions": unresolved_collisions,
                "arrows": final_arrows,
            },
            f,
            indent=2,
        )
    print(f"[OK] Annotated screenshot saved via {engine_name} to: {out_path}")
    print(f"[OK] Arrow coordinate audit saved to: {arrows_audit}")


def _annotate_single_image(args: argparse.Namespace, in_raw: str, out_raw: str) -> None:
    """Resolve rendering engine, plan collision-free annotations, and draw a single figure."""
    in_path = validate_workspace_path(in_raw, must_exist=True)
    out_path = validate_workspace_path(out_raw, must_exist=False)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    engine_choice = getattr(args, "engine", "auto").lower()
    is_png = in_path.lower().endswith(".png")
    if engine_choice == "auto":
        if HAVE_CAIRO and is_png:
            resolved_engine = "cairo"
        elif HAVE_PIL:
            resolved_engine = "pillow"
        elif HAVE_CAIRO:
            resolved_engine = "cairo"
        else:
            resolved_engine = "none"
    elif engine_choice == "pillow":
        if not HAVE_PIL:
            sys.exit("Error: Pillow (PIL) is not installed.")
        resolved_engine = "pillow"
    elif engine_choice == "cairo":
        if not HAVE_CAIRO:
            sys.exit("Error: PyCairo ('cairo') is not installed.")
        resolved_engine = "cairo"
    else:
        sys.exit(f"Error: Unknown annotation engine '{engine_choice}'. Choose 'auto', 'pillow', or 'cairo'.")

    if resolved_engine == "none":
        sys.exit(
            "Error: Neither Pillow (PIL) nor PyCairo (cairo) is installed.\n"
            "Install Pillow via pip, or pycairo (e.g. apt install python3-cairo), or place pre-annotated screenshots directly into docs/manual_book/assets/final/."
        )

    layout_file = f"{os.path.splitext(in_path)[0]}.layout.json"
    layout_data: Optional[Dict[str, Any]] = None
    if os.path.exists(layout_file):
        try:
            with open(layout_file, "r", encoding="utf-8") as f:
                layout_data = json.load(f)
        except Exception:
            layout_data = None

    if resolved_engine == "cairo":
        surface = cairo.ImageSurface.create_from_png(in_path)
        width, height = surface.get_width(), surface.get_height()
        scale = compute_annotation_scale(width, height)
        ctx = cairo.Context(surface)
        obstacles = (
            list(layout_data["text_rects"])
            if layout_data and layout_data.get("text_rects")
            else detect_cairo_surface_obstacles(surface)
        )
        boxes_to_draw, final_arrows, unresolved = _resolve_annotations(
            args, width, height, obstacles, layout_data, badge_r_check=18.0 * scale
        )
        for bx1, by1, bx2, by2 in boxes_to_draw:
            cairo_draw_bounding_highlight(
                ctx, bx1, by1, max(1.0, bx2 - bx1), max(1.0, by2 - by1), scale=scale
            )
        for arr in final_arrows:
            cairo_draw_badge_and_arrow(
                ctx, arr["x1"], arr["y1"], arr["x2"], arr["y2"], arr["label"], scale=scale
            )
        surface.write_to_png(out_path)
        _write_arrows_audit(out_path, "cairo", unresolved, final_arrows)
        return

    with Image.open(in_path).convert("RGB") as img:
        width, height = img.size
        scale = compute_annotation_scale(width, height)
        eff_stroke = max(args.stroke_width, int(round(args.stroke_width * scale)))
        draw = ImageDraw.Draw(img)
        obstacles = (
            list(layout_data["text_rects"])
            if layout_data and layout_data.get("text_rects")
            else detect_image_dense_obstacles(img)
        )
        badge_r_check = max(int(round(20 * scale)), int(eff_stroke * 2.5))
        boxes_to_draw, final_arrows, unresolved = _resolve_annotations(
            args, width, height, obstacles, layout_data, badge_r_check=badge_r_check
        )
        for bx1, by1, bx2, by2 in boxes_to_draw:
            _draw_pillow_highlight_box(draw, bx1, by1, bx2, by2, scale=scale)
        for arr in final_arrows:
            _draw_arrow_with_callout(
                draw, arr["x1"], arr["y1"], arr["x2"], arr["y2"], label=arr["label"], width=eff_stroke
            )
        img.save(out_path, quality=95)
        _write_arrows_audit(out_path, "pillow", unresolved, final_arrows)


def cmd_annotate(args: argparse.Namespace) -> None:
    """Draw arrows and callout badges onto single screenshot or all figures in manual_spec.json."""
    if not getattr(args, "spec", ""):
        if not args.input or not args.output:
            raise ValueError("Validation Error: Provide either --spec or both --input and --output.")
        _annotate_single_image(args, args.input, args.output)
        return

    spec_path = validate_workspace_path(args.spec, must_exist=True)
    spec_dir = os.path.dirname(spec_path)
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    annotated_count = 0
    for ch in spec.get("chapters", []):
        for sec in ch.get("sections", []):
            for fig in sec.get("figures", []):
                src = fig.get("source") or {}
                raw_rel = str(src.get("raw", "")).strip()
                final_rel = str(fig.get("image_path", "")).strip()
                if not raw_rel or not final_rel:
                    continue
                raw_path = _resolve_spec_asset(raw_rel, spec_dir, must_exist=False)
                final_path = _resolve_spec_asset(final_rel, spec_dir, must_exist=False)
                if not os.path.isfile(raw_path):
                    print(f"[WARNING] Figure {fig.get('id', '?')}: raw screenshot missing at {raw_path}; skipping.")
                    continue
                if (
                    not getattr(args, "force", False)
                    and os.path.isfile(final_path)
                    and os.path.getmtime(final_path) >= os.path.getmtime(raw_path)
                ):
                    continue

                fig_args = argparse.Namespace(**vars(args))
                spec_targets = [str(t) for t in src.get("targets", [])]
                fig_args.target = list(args.target or []) + spec_targets
                if not fig_args.auto and not fig_args.arrow:
                    fig_args.auto = True
                _annotate_single_image(fig_args, raw_path, final_path)
                annotated_count += 1

    print(f"[OK] Batch annotate completed ({annotated_count} figure(s) processed).")


def cmd_batch(args: argparse.Namespace) -> None:
    """Run batch capture (for missing URL screenshots) and batch auto-annotation from manual_spec.json."""
    spec_path = validate_workspace_path(args.spec, must_exist=True)
    pending_captures = _collect_capture_tasks_from_spec(spec_path, force=getattr(args, "force", False))
    if pending_captures:
        cmd_capture(args)
    else:
        print("[OK] Capture skipped: all spec figures with URLs already exist (use --force to recapture).")
    ann_args = argparse.Namespace(**vars(args))
    ann_args.auto = True
    ann_args.target = None
    ann_args.arrow = None
    ann_args.box = None
    ann_args.box_xywh = None
    cmd_annotate(ann_args)


# ---------------------------------------------------------
# CLI Parser Setup
# ---------------------------------------------------------
def _add_capture_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--width", type=int, default=1440, help="Viewport width (default: 1440).")
    p.add_argument("--height", type=int, default=900, help="Viewport height (default: 900).")
    p.add_argument("--scale", type=int, default=2, choices=[1, 2, 3], help="Device scale factor (default: 2).")
    p.add_argument("--full-page", action="store_true", help="Capture full scrollable page.")
    p.add_argument("--wait-ms", type=int, default=500, help="Extra wait time in ms after networkidle.")
    p.add_argument("--timeout", type=int, default=30, help="Navigation timeout in seconds.")
    p.add_argument(
        "--mask-selectors",
        default="input[type='password']",
        help="Comma-separated CSS selectors to mask before screenshot.",
    )


def _add_annotate_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--draw-target-boxes",
        action="store_true",
        help="Draw highlight boxes around --target elements when using --auto.",
    )
    p.add_argument("--stroke-width", type=int, default=8, help="Arrow line thickness (default: 8).")
    p.add_argument(
        "--grid-snap",
        type=int,
        default=10,
        help="Grid snapping interval in pixels for arrow placement (default: 10).",
    )
    p.add_argument(
        "--engine",
        choices=["auto", "pillow", "cairo"],
        default="auto",
        help="Rendering engine: 'auto' (PyCairo for PNG if available, else Pillow), 'pillow', or 'cairo'.",
    )
    p.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow arrows to overlap text without auto-adjustment or error.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe High-DPI Screenshot Capture, Grid Overlay, and Collision-Free Arrow Annotator."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # capture subcommand
    p_cap = sub.add_parser("capture", help="Auto-capture high-DPI screenshot(s) from a URL or manual_spec.json.")
    p_cap.add_argument("--url", help="Target http:// or https:// URL.")
    p_cap.add_argument("--output", help="Output image path inside workspace.")
    p_cap.add_argument("--spec", help="Batch capture all figures with source.url from manual_spec.json.")
    p_cap.add_argument("--force", action="store_true", help="Recapture existing raw screenshots when using --spec.")
    _add_capture_args(p_cap)
    p_cap.add_argument(
        "--target",
        action="append",
        help="Target element to record: 'label=css_selector' or 'css_selector'. Can be specified multiple times.",
    )
    p_cap.set_defaults(func=cmd_capture)

    # grid subcommand
    p_grid = sub.add_parser("grid", help="Generate a coordinate grid overlay on a screenshot.")
    p_grid.add_argument("--input", required=True, help="Path to clean screenshot.")
    p_grid.add_argument("--output", required=True, help="Path to output grid helper image.")
    p_grid.add_argument("--step", type=int, default=100, help="Major grid interval in pixels (default: 100).")
    p_grid.set_defaults(func=cmd_grid)

    # annotate subcommand
    p_ann = sub.add_parser("annotate", help="Draw arrows and callout badges onto a screenshot or manual_spec.json.")
    p_ann.add_argument("--input", help="Path to clean screenshot.")
    p_ann.add_argument("--output", help="Path to output annotated screenshot.")
    p_ann.add_argument("--spec", help="Batch annotate all figures from manual_spec.json.")
    p_ann.add_argument("--force", action="store_true", help="Re-annotate existing final screenshots when using --spec.")
    p_ann.add_argument(
        "--auto",
        action="store_true",
        help="Automatically place arrows on targets avoiding text occlusion.",
    )
    p_ann.add_argument(
        "--target",
        action="append",
        help="Manual target box 'x1,y1,x2,y2[,label]'. Can be specified multiple times.",
    )
    p_ann.add_argument(
        "--arrow",
        action="append",
        help="Arrow spec 'x1,y1,x2,y2[,label]'. Can be specified multiple times.",
    )
    p_ann.add_argument(
        "--box",
        action="append",
        help="Highlight box spec 'x1,y1,x2,y2'. Can be specified multiple times.",
    )
    p_ann.add_argument(
        "--box-xywh",
        action="append",
        help="Highlight box spec 'x,y,w,h'. Can be specified multiple times.",
    )
    _add_annotate_args(p_ann)
    p_ann.set_defaults(func=cmd_annotate)

    # batch subcommand
    p_batch = sub.add_parser("batch", help="Run batch capture and auto-annotation across manual_spec.json.")
    p_batch.add_argument(
        "--spec",
        default="docs/manual_book/manual_spec.json",
        help="Path to manual_spec.json (default: docs/manual_book/manual_spec.json).",
    )
    p_batch.add_argument("--force", action="store_true", help="Force recapture and re-annotation of existing assets.")
    _add_capture_args(p_batch)
    _add_annotate_args(p_batch)
    p_batch.set_defaults(func=cmd_batch)

    return parser


def main() -> None:
    cli_parser = build_parser()
    parsed_args = cli_parser.parse_args()
    try:
        parsed_args.func(parsed_args)
    except Exception as err:
        sys.exit(f"[ERROR] {err}")


if __name__ == "__main__":
    main()
