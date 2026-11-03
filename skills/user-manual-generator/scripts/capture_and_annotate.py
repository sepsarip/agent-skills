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

try:
    import cairo
    from annotate_cairo import (
        draw_badge_and_arrow as cairo_draw_badge_and_arrow,
        draw_bounding_highlight as cairo_draw_bounding_highlight,
    )
    HAVE_CAIRO = True
except ImportError:
    HAVE_CAIRO = False

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
def cmd_capture(args: argparse.Namespace) -> None:
    """Capture crisp high-DPI screenshot from URL and extract text/element layout coordinates."""
    url = validate_url(args.url)
    out_path = validate_workspace_path(args.output, must_exist=False)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "Error: Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
        )

    mask_selectors = [s.strip() for s in args.mask_selectors.split(",") if s.strip()]
    target_specs = args.target or []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": args.width, "height": args.height},
                device_scale_factor=args.scale,
            )
            page = context.new_page()
            page.set_default_timeout(args.timeout * 1000)
            page.goto(url, wait_until="networkidle")

            if args.wait_ms > 0:
                page.wait_for_timeout(args.wait_ms)

            # Collect element and text node bounding rects in image pixels
            layout_data: Dict[str, Any] = {
                "url": url,
                "scale": args.scale,
                "width": args.width * args.scale,
                "height": args.height * args.scale,
                "text_rects": [],
                "target_boxes": [],
            }

            # Evaluate DOM layout to record obstacle text rectangles
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
                        "x1": r["x"] * args.scale,
                        "y1": r["y"] * args.scale,
                        "x2": (r["x"] + r["w"]) * args.scale,
                        "y2": (r["y"] + r["h"]) * args.scale,
                        "text": r["text"],
                    }
                )

            # Resolve specified target selectors: "1=#button-id" or "selector"
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
                        "x1": bbox["x"] * args.scale,
                        "y1": bbox["y"] * args.scale,
                        "x2": (bbox["x"] + bbox["width"]) * args.scale,
                        "y2": (bbox["y"] + bbox["height"]) * args.scale,
                    }
                )

            # Mask sensitive elements
            mask_locators = [page.locator(sel) for sel in mask_selectors]
            page.screenshot(
                path=out_path,
                full_page=args.full_page,
                mask=mask_locators if mask_locators else None,
            )

            # Write layout sidecar file: <output>.layout.json
            layout_path = f"{os.path.splitext(out_path)[0]}.layout.json"
            with open(layout_path, "w", encoding="utf-8") as f:
                json.dump(layout_data, f, indent=2)

            print(f"[OK] High-DPI screenshot saved to: {out_path}")
            print(f"[OK] Layout map sidecar saved to: {layout_path}")
        finally:
            browser.close()


# ---------------------------------------------------------
# Grid Helper
# ---------------------------------------------------------
def _load_font(size: int) -> Any:
    """Load a clean sans-serif font with graceful fallback."""
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
def rect_intersects_segment(
    rx1: float, ry1: float, rx2: float, ry2: float,
    x1: float, y1: float, x2: float, y2: float, pad: float = 6.0
) -> bool:
    """Check if line segment (x1,y1)-(x2,y2) intersects a padded rectangle."""
    min_x, max_x = min(rx1, rx2) - pad, max(rx1, rx2) + pad
    min_y, max_y = min(ry1, ry2) - pad, max(ry1, ry2) + pad

    if min_x <= x1 <= max_x and min_y <= y1 <= max_y:
        return True
    if min_x <= x2 <= max_x and min_y <= y2 <= max_y:
        return True

    if max(x1, x2) < min_x or min(x1, x2) > max_x:
        return False
    if max(y1, y2) < min_y or min(y1, y2) > max_y:
        return False

    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return False

    for edge_p1, edge_p2 in [
        ((min_x, min_y), (max_x, min_y)),
        ((max_x, min_y), (max_x, max_y)),
        ((max_x, max_y), (min_x, max_y)),
        ((min_x, max_y), (min_x, min_y)),
    ]:
        ex1, ey1 = edge_p1
        ex2, ey2 = edge_p2
        denom = (dy * (ex2 - ex1)) - (dx * (ey2 - ey1))
        if abs(denom) < 1e-6:
            continue
        ua = ((dx * (ey1 - y1)) - (dy * (ex1 - x1))) / denom
        ub = (((ex2 - ex1) * (ey1 - y1)) - ((ey2 - ey1) * (ex1 - x1))) / denom
        if 0.0 <= ua <= 1.0 and 0.0 <= ub <= 1.0:
            return True

    return False


def circle_intersects_rect(
    cx: float, cy: float, radius: float,
    rx1: float, ry1: float, rx2: float, ry2: float
) -> bool:
    """Check if circle at (cx,cy) intersects axis-aligned rectangle."""
    min_x, max_x = min(rx1, rx2), max(rx1, rx2)
    min_y, max_y = min(ry1, ry2), max(ry1, ry2)

    closest_x = max(min_x, min(cx, max_x))
    closest_y = max(min_y, min(cy, max_y))

    dist_x = cx - closest_x
    dist_y = cy - closest_y
    return (dist_x * dist_x + dist_y * dist_y) <= (radius * radius)


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

    badge_radius = max(20, int(stroke_width * 2.5))
    clearance = max(8, stroke_width + 4)

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

    # Compact lengths: prioritize short, direct, readable arrows near element
    candidate_lengths = [45, 65, 85, 110, 140]

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

        head_x = tx + (cos_a * 4)
        head_y = ty + (sin_a * 4)

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

            margin = badge_radius + 8
            if not (margin <= tail_x <= img_width - margin and margin <= tail_y <= img_height - margin):
                continue
            if not (8 <= head_x <= img_width - 8 and 8 <= head_y <= img_height - 8):
                continue

            has_badge_collision = False
            for obs in obstacles:
                if circle_intersects_rect(
                    tail_x, tail_y, badge_radius + clearance,
                    obs["x1"], obs["y1"], obs["x2"], obs["y2"]
                ):
                    has_badge_collision = True
                    break
            if has_badge_collision:
                continue

            has_shaft_collision = False
            for obs in obstacles:
                if obs is target_box:
                    continue
                if rect_intersects_segment(
                    obs["x1"], obs["y1"], obs["x2"], obs["y2"],
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

    # Compact fallback placement (55px instead of 150px)
    fallback_len = 55.0
    if center_x < img_width * 0.3:
        head_x = bx2
        head_y = center_y
        tail_x = min(img_width - badge_radius - 10, head_x + fallback_len)
        tail_y = head_y
    else:
        head_x = bx1
        head_y = center_y
        tail_x = max(badge_radius + 10, head_x - fallback_len)
        tail_y = head_y

    if grid_snap > 1:
        tail_x = round(tail_x / grid_snap) * grid_snap
        tail_y = round(tail_y / grid_snap) * grid_snap

    return (float(tail_x), float(tail_y), float(head_x), float(head_y))


# ---------------------------------------------------------
# Drawing & Annotation
# ---------------------------------------------------------
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
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (x1 - tw / 2, y1 - th / 2 - bbox[1] / 2),
            label,
            fill=(255, 255, 255),
            font=font,
        )


def _cmd_annotate_cairo(
    args: argparse.Namespace,
    in_path: str,
    out_path: str,
    layout_data: Optional[Dict[str, Any]],
) -> None:
    """Render annotations using PyCairo engine."""
    surface = cairo.ImageSurface.create_from_png(in_path)
    width = surface.get_width()
    height = surface.get_height()
    ctx = cairo.Context(surface)

    obstacles: List[Dict[str, float]] = []
    if layout_data and layout_data.get("text_rects"):
        obstacles.extend(layout_data["text_rects"])

    for box_spec in args.box or []:
        parts = [p.strip() for p in box_spec.split(",")]
        if len(parts) != 4:
            raise ValueError(f"Invalid --box format '{box_spec}'. Expected 'x1,y1,x2,y2'.")
        b1, b2, b3, b4 = map(float, parts)
        if b3 > b1 and b4 > b2 and (b3 - b1 > 5 or b4 - b2 > 5):
            bx, by, bw, bh = b1, b2, b3 - b1, b4 - b2
        else:
            bx, by, bw, bh = b1, b2, b3, b4
        cairo_draw_bounding_highlight(ctx, bx, by, bw, bh)

    final_arrows: List[Dict[str, Any]] = []

    if args.auto:
        targets_to_place: List[Dict[str, Any]] = []
        if layout_data and layout_data.get("target_boxes"):
            targets_to_place.extend(layout_data["target_boxes"])

        for t_arg in args.target or []:
            parts = [p.strip() for p in t_arg.split(",")]
            if len(parts) >= 4:
                targets_to_place.append(
                    {
                        "x1": float(parts[0]),
                        "y1": float(parts[1]),
                        "x2": float(parts[2]),
                        "y2": float(parts[3]),
                        "label": parts[4] if len(parts) > 4 else str(len(targets_to_place) + 1),
                    }
                )

        if not targets_to_place and not args.arrow:
            print(
                "[WARNING] --auto specified, but no target boxes found in layout sidecar (.layout.json) or --target flags. No auto arrows were placed."
            )

        for target in targets_to_place:
            lbl = str(target.get("label") or len(final_arrows) + 1)
            ax1, ay1, ax2, ay2 = find_optimal_arrow_placement(
                target,
                lbl,
                obstacles,
                width,
                height,
                stroke_width=args.stroke_width,
                grid_snap=getattr(args, "grid_snap", 10),
            )
            cairo_draw_badge_and_arrow(ctx, ax1, ay1, ax2, ay2, lbl)
            obstacles.append(
                {
                    "x1": min(ax1, ax2) - 15,
                    "y1": min(ay1, ay2) - 15,
                    "x2": max(ax1, ax2) + 15,
                    "y2": max(ay1, ay2) + 15,
                }
            )
            final_arrows.append(
                {"x1": ax1, "y1": ay1, "x2": ax2, "y2": ay2, "label": lbl, "auto": True}
            )

    for arrow_spec in args.arrow or []:
        parts = [p.strip() for p in arrow_spec.split(",")]
        if len(parts) not in (4, 5):
            raise ValueError(
                f"Invalid --arrow format '{arrow_spec}'. Expected 'x1,y1,x2,y2' or 'x1,y1,x2,y2,label'."
            )
        ax1, ay1, ax2, ay2 = map(float, parts[:4])
        label = parts[4] if len(parts) == 5 else ""

        collided = False
        badge_r = max(20, int(args.stroke_width * 2.5))
        for obs in obstacles:
            if circle_intersects_rect(ax1, ay1, badge_r, obs["x1"], obs["y1"], obs["x2"], obs["y2"]):
                collided = True
                break
            if rect_intersects_segment(obs["x1"], obs["y1"], obs["x2"], obs["y2"], ax1, ay1, ax2, ay2):
                collided = True
                break

        if collided and not args.allow_overlap:
            snap = getattr(args, "grid_snap", 10) or 10
            nudge_offsets = [
                (0, -snap), (0, snap), (-snap, 0), (snap, 0),
                (-snap, -snap), (snap, -snap), (-snap, snap), (snap, snap),
                (0, -2 * snap), (0, 2 * snap), (-2 * snap, 0), (2 * snap, 0),
            ]
            resolved_nudge = None
            for dx, dy in nudge_offsets:
                test_x1, test_y1 = ax1 + dx, ay1 + dy
                if not (badge_r <= test_x1 <= width - badge_r and badge_r <= test_y1 <= height - badge_r):
                    continue
                nudge_collided = False
                for obs in obstacles:
                    if circle_intersects_rect(test_x1, test_y1, badge_r + 4, obs["x1"], obs["y1"], obs["x2"], obs["y2"]):
                        nudge_collided = True
                        break
                    if rect_intersects_segment(obs["x1"], obs["y1"], obs["x2"], obs["y2"], test_x1, test_y1, ax2, ay2):
                        nudge_collided = True
                        break
                if not nudge_collided:
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
                    "x1": ax2 - 10,
                    "y1": ay2 - 10,
                    "x2": ax2 + 10,
                    "y2": ax2 + 10,
                }
                new_x1, new_y1, new_x2, new_y2 = find_optimal_arrow_placement(
                    fake_target,
                    label,
                    obstacles,
                    width,
                    height,
                    stroke_width=args.stroke_width,
                    grid_snap=getattr(args, "grid_snap", 10),
                )
                print(
                    f"[AUTO-ADJUST] Arrow '{label}' adjusted from ({ax1:.0f},{ay1:.0f}) to ({new_x1:.0f},{new_y1:.0f}) to avoid text occlusion."
                )
                ax1, ay1, ax2, ay2 = new_x1, new_y1, new_x2, new_y2

        cairo_draw_badge_and_arrow(ctx, ax1, ay1, ax2, ay2, label)
        obstacles.append(
            {
                "x1": min(ax1, ax2) - 15,
                "y1": min(ay1, ay2) - 15,
                "x2": max(ax1, ax2) + 15,
                "y2": max(ay1, ay2) + 15,
            }
        )
        final_arrows.append(
            {"x1": ax1, "y1": ay1, "x2": ax2, "y2": ay2, "label": label, "auto": False}
        )

    surface.write_to_png(out_path)
    arrows_audit = f"{os.path.splitext(out_path)[0]}.arrows.json"
    with open(arrows_audit, "w", encoding="utf-8") as f:
        json.dump({"image": out_path, "arrows": final_arrows, "engine": "cairo"}, f, indent=2)

    print(f"[OK] Annotated screenshot saved via Cairo to: {out_path}")
    print(f"[OK] Arrow coordinate audit saved to: {arrows_audit}")


def cmd_annotate(args: argparse.Namespace) -> None:
    """Draw arrows and callout badges onto a screenshot with text occlusion avoidance."""
    engine_choice = getattr(args, "engine", "auto").lower()
    if engine_choice == "auto":
        resolved_engine = "pillow" if HAVE_PIL else ("cairo" if HAVE_CAIRO else "none")
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

    in_path = validate_workspace_path(args.input, must_exist=True)
    out_path = validate_workspace_path(args.output, must_exist=False)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    layout_file = f"{os.path.splitext(in_path)[0]}.layout.json"
    layout_data: Optional[Dict[str, Any]] = None
    if os.path.exists(layout_file):
        try:
            with open(layout_file, "r", encoding="utf-8") as f:
                layout_data = json.load(f)
        except Exception:
            layout_data = None

    if resolved_engine == "cairo":
        _cmd_annotate_cairo(args, in_path, out_path, layout_data)
        return

    with Image.open(in_path).convert("RGB") as img:
        width, height = img.size
        draw = ImageDraw.Draw(img)

        obstacles: List[Dict[str, float]] = []
        if layout_data and layout_data.get("text_rects"):
            obstacles.extend(layout_data["text_rects"])
        else:
            dense_obstacles = detect_image_dense_obstacles(img)
            obstacles.extend(dense_obstacles)

        for box_spec in args.box or []:
            parts = [p.strip() for p in box_spec.split(",")]
            if len(parts) != 4:
                raise ValueError(f"Invalid --box format '{box_spec}'. Expected 'x1,y1,x2,y2'.")
            bx1, by1, bx2, by2 = map(float, parts)
            draw.rectangle([bx1 - 2, by1 - 2, bx2 + 2, by2 + 2], outline=(255, 255, 255), width=7)
            draw.rectangle([bx1, by1, bx2, by2], outline=(230, 30, 40), width=4)

        final_arrows: List[Dict[str, Any]] = []

        if args.auto:
            targets_to_place: List[Dict[str, Any]] = []
            if layout_data and layout_data.get("target_boxes"):
                targets_to_place.extend(layout_data["target_boxes"])

            for t_arg in args.target or []:
                parts = [p.strip() for p in t_arg.split(",")]
                if len(parts) >= 4:
                    targets_to_place.append(
                        {
                            "x1": float(parts[0]),
                            "y1": float(parts[1]),
                            "x2": float(parts[2]),
                            "y2": float(parts[3]),
                            "label": parts[4] if len(parts) > 4 else str(len(targets_to_place) + 1),
                        }
                    )

            if not targets_to_place and not args.arrow:
                print(
                    "[WARNING] --auto specified, but no target boxes found in layout sidecar (.layout.json) or --target flags. No auto arrows were placed."
                )

            for target in targets_to_place:
                lbl = str(target.get("label") or len(final_arrows) + 1)
                ax1, ay1, ax2, ay2 = find_optimal_arrow_placement(
                    target,
                    lbl,
                    obstacles,
                    width,
                    height,
                    stroke_width=args.stroke_width,
                    grid_snap=getattr(args, "grid_snap", 10),
                )
                _draw_arrow_with_callout(
                    draw, ax1, ay1, ax2, ay2, label=lbl, width=args.stroke_width
                )
                obstacles.append(
                    {
                        "x1": min(ax1, ax2) - 15,
                        "y1": min(ay1, ay2) - 15,
                        "x2": max(ax1, ax2) + 15,
                        "y2": max(ay1, ay2) + 15,
                    }
                )
                final_arrows.append(
                    {"x1": ax1, "y1": ay1, "x2": ax2, "y2": ay2, "label": lbl, "auto": True}
                )

        for arrow_spec in args.arrow or []:
            parts = [p.strip() for p in arrow_spec.split(",")]
            if len(parts) not in (4, 5):
                raise ValueError(
                    f"Invalid --arrow format '{arrow_spec}'. Expected 'x1,y1,x2,y2' or 'x1,y1,x2,y2,label'."
                )
            ax1, ay1, ax2, ay2 = map(float, parts[:4])
            label = parts[4] if len(parts) == 5 else ""

            collided = False
            badge_r = max(20, int(args.stroke_width * 2.5))
            for obs in obstacles:
                if circle_intersects_rect(ax1, ay1, badge_r, obs["x1"], obs["y1"], obs["x2"], obs["y2"]):
                    collided = True
                    break
                if rect_intersects_segment(obs["x1"], obs["y1"], obs["x2"], obs["y2"], ax1, ay1, ax2, ay2):
                    collided = True
                    break

            if collided and not args.allow_overlap:
                snap = getattr(args, "grid_snap", 10) or 10
                nudge_offsets = [
                    (0, -snap), (0, snap), (-snap, 0), (snap, 0),
                    (-snap, -snap), (snap, -snap), (-snap, snap), (snap, snap),
                    (0, -2 * snap), (0, 2 * snap), (-2 * snap, 0), (2 * snap, 0),
                ]
                resolved_nudge = None
                for dx, dy in nudge_offsets:
                    test_x1, test_y1 = ax1 + dx, ay1 + dy
                    if not (badge_r <= test_x1 <= width - badge_r and badge_r <= test_y1 <= height - badge_r):
                        continue
                    nudge_collided = False
                    for obs in obstacles:
                        if circle_intersects_rect(test_x1, test_y1, badge_r + 4, obs["x1"], obs["y1"], obs["x2"], obs["y2"]):
                            nudge_collided = True
                            break
                        if rect_intersects_segment(obs["x1"], obs["y1"], obs["x2"], obs["y2"], test_x1, test_y1, ax2, ay2):
                            nudge_collided = True
                            break
                    if not nudge_collided:
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
                        "x1": ax2 - 10,
                        "y1": ay2 - 10,
                        "x2": ax2 + 10,
                        "y2": ay2 + 10,
                    }
                    new_x1, new_y1, new_x2, new_y2 = find_optimal_arrow_placement(
                        fake_target,
                        label,
                        obstacles,
                        width,
                        height,
                        stroke_width=args.stroke_width,
                        grid_snap=getattr(args, "grid_snap", 10),
                    )
                    print(
                        f"[AUTO-ADJUST] Arrow '{label}' adjusted from ({ax1:.0f},{ay1:.0f}) to ({new_x1:.0f},{new_y1:.0f}) to avoid text occlusion."
                    )
                    ax1, ay1, ax2, ay2 = new_x1, new_y1, new_x2, new_y2

            _draw_arrow_with_callout(
                draw, ax1, ay1, ax2, ay2, label=label, width=args.stroke_width
            )
            obstacles.append(
                {
                    "x1": min(ax1, ax2) - 15,
                    "y1": min(ay1, ay2) - 15,
                    "x2": max(ax1, ax2) + 15,
                    "y2": max(ay1, ay2) + 15,
                }
            )
            final_arrows.append(
                {"x1": ax1, "y1": ay1, "x2": ax2, "y2": ay2, "label": label, "auto": False}
            )

        img.save(out_path, quality=95)

        arrows_audit = f"{os.path.splitext(out_path)[0]}.arrows.json"
        with open(arrows_audit, "w", encoding="utf-8") as f:
            json.dump({"image": out_path, "arrows": final_arrows}, f, indent=2)

        print(f"[OK] Annotated screenshot saved to: {out_path}")
        print(f"[OK] Arrow coordinate audit saved to: {arrows_audit}")


# ---------------------------------------------------------
# CLI Parser Setup
# ---------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe High-DPI Screenshot Capture, Grid Overlay, and Collision-Free Arrow Annotator."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # capture subcommand
    p_cap = sub.add_parser("capture", help="Auto-capture a high-DPI screenshot from a URL.")
    p_cap.add_argument("--url", required=True, help="Target http:// or https:// URL.")
    p_cap.add_argument("--output", required=True, help="Output image path inside workspace.")
    p_cap.add_argument("--width", type=int, default=1440, help="Viewport width (default: 1440).")
    p_cap.add_argument("--height", type=int, default=900, help="Viewport height (default: 900).")
    p_cap.add_argument("--scale", type=int, default=2, choices=[1, 2, 3], help="Device scale factor (default: 2).")
    p_cap.add_argument("--full-page", action="store_true", help="Capture full scrollable page.")
    p_cap.add_argument("--wait-ms", type=int, default=500, help="Extra wait time in ms after networkidle.")
    p_cap.add_argument("--timeout", type=int, default=30, help="Navigation timeout in seconds.")
    p_cap.add_argument(
        "--mask-selectors",
        default="input[type='password']",
        help="Comma-separated CSS selectors to mask before screenshot.",
    )
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
    p_ann = sub.add_parser("annotate", help="Draw arrows and callout badges onto a screenshot.")
    p_ann.add_argument("--input", required=True, help="Path to clean screenshot.")
    p_ann.add_argument("--output", required=True, help="Path to output annotated screenshot.")
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
    p_ann.add_argument("--stroke-width", type=int, default=8, help="Arrow line thickness (default: 8).")
    p_ann.add_argument(
        "--grid-snap",
        type=int,
        default=10,
        help="Grid snapping interval in pixels for arrow placement (default: 10).",
    )
    p_ann.add_argument(
        "--engine",
        choices=["auto", "pillow", "cairo"],
        default="auto",
        help="Rendering engine: 'auto' (Pillow if available, else PyCairo), 'pillow', or 'cairo' (default: auto).",
    )
    p_ann.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow arrows to overlap text without auto-adjustment or error.",
    )
    p_ann.set_defaults(func=cmd_annotate)

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
