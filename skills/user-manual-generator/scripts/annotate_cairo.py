#!/usr/bin/env python3
"""
Custom high-resolution arrow, badge, and rounded bounding box annotator using PyCairo.
Draws crisp, anti-aliased arrows and circular numbered badges pointing to target UI
elements without occluding on-screen text.
Part of user-manual-generator agent skill.
"""

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import cairo
    HAVE_CAIRO = True
except ImportError:
    HAVE_CAIRO = False


def validate_workspace_path(target_path: str, must_exist: bool = False) -> str:
    """Ensure the target path resides within the current working directory."""
    cwd = os.path.realpath(os.getcwd())
    real_target = os.path.realpath(target_path)
    if not (real_target == cwd or real_target.startswith(cwd + os.sep)):
        raise ValueError(
            f"Security Error: Path '{target_path}' escapes the active workspace '{cwd}'."
        )
    if must_exist and not os.path.isfile(real_target):
        raise FileNotFoundError(f"Input file not found: {real_target}")
    parent_dir = os.path.dirname(real_target)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
    return real_target


def draw_badge_and_arrow(
    ctx: "cairo.Context",
    badge_x: float,
    badge_y: float,
    target_x: float,
    target_y: float,
    number_str: str,
    color: Tuple[float, float, float] = (0.145, 0.388, 0.922),
    badge_radius: float = 16.0,
) -> None:
    """
    badge_x, badge_y: center of the circular badge.
    target_x, target_y: point where the arrow tip lands.
    number_str: text inside badge ('1', '2', etc.).
    color: RGB tuple (0.0 .. 1.0).
    """
    # 1. Calculate angle from badge to target
    dx = target_x - badge_x
    dy = target_y - badge_y
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return

    ux = dx / dist
    uy = dy / dist

    start_x = badge_x + ux * badge_radius
    start_y = badge_y + uy * badge_radius

    # 2. Draw Arrow Line Shadow
    ctx.save()
    ctx.set_line_width(5.0)
    ctx.set_source_rgba(0.0, 0.0, 0.0, 0.25)
    ctx.move_to(start_x + 1.5, start_y + 1.5)
    ctx.line_to(target_x + 1.5, target_y + 1.5)
    ctx.stroke()
    ctx.restore()

    # 3. Draw Arrow Line White Glow / Outline
    ctx.save()
    ctx.set_line_width(4.5)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.move_to(start_x, start_y)
    ctx.line_to(target_x, target_y)
    ctx.stroke()
    ctx.restore()

    # 4. Draw Arrow Line Main Color
    ctx.save()
    ctx.set_line_width(2.5)
    ctx.set_source_rgb(*color)
    ctx.move_to(start_x, start_y)
    ctx.line_to(target_x, target_y)
    ctx.stroke()
    ctx.restore()

    # 5. Draw Arrow Head (Triangle)
    arrow_len = 13.0
    arrow_half_w = 5.5

    base_x = target_x - ux * arrow_len
    base_y = target_y - uy * arrow_len
    norm_x = -uy
    norm_y = ux

    left_x = base_x + norm_x * arrow_half_w
    left_y = base_y + norm_y * arrow_half_w
    right_x = base_x - norm_x * arrow_half_w
    right_y = base_y - norm_y * arrow_half_w

    # Arrow head outline & fill
    ctx.save()
    ctx.set_line_width(1.5)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.move_to(target_x, target_y)
    ctx.line_to(left_x, left_y)
    ctx.line_to(right_x, right_y)
    ctx.close_path()
    ctx.stroke_preserve()
    ctx.set_source_rgb(*color)
    ctx.fill()
    ctx.restore()

    # 6. Draw Badge Shadow
    ctx.save()
    ctx.arc(badge_x + 1.5, badge_y + 1.5, badge_radius, 0, 2 * math.pi)
    ctx.set_source_rgba(0.0, 0.0, 0.0, 0.3)
    ctx.fill()
    ctx.restore()

    # 7. Draw Badge Body (Circle)
    ctx.save()
    ctx.arc(badge_x, badge_y, badge_radius, 0, 2 * math.pi)
    ctx.set_source_rgb(*color)
    ctx.fill_preserve()
    # White ring border
    ctx.set_line_width(2.5)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.stroke()
    ctx.restore()

    # 8. Draw Number Text
    ctx.save()
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(15.0)
    ctx.set_source_rgb(1.0, 1.0, 1.0)

    extents = ctx.text_extents(str(number_str))
    text_x = badge_x - (extents.width / 2.0 + extents.x_bearing)
    text_y = badge_y - (extents.height / 2.0 + extents.y_bearing)
    ctx.move_to(text_x, text_y)
    ctx.show_text(str(number_str))
    ctx.restore()


def draw_bounding_highlight(
    ctx: "cairo.Context",
    x: float,
    y: float,
    w: float,
    h: float,
    color: Tuple[float, float, float] = (0.145, 0.388, 0.922),
    radius: float = 6.0,
    pad: float = 4.0,
) -> None:
    """Draw a neat rounded dashed rectangle around the target element."""
    rx = x - pad
    ry = y - pad
    rw = max(1.0, w + pad * 2.0)
    rh = max(1.0, h + pad * 2.0)
    rad = min(radius, rw / 2.0, rh / 2.0)

    ctx.save()
    ctx.set_line_width(2.0)
    ctx.set_dash([6.0, 4.0])
    ctx.set_source_rgba(color[0], color[1], color[2], 0.85)

    # Rounded rectangle path
    ctx.new_sub_path()
    ctx.arc(rx + rw - rad, ry + rad, rad, -math.pi / 2, 0)
    ctx.arc(rx + rw - rad, ry + rh - rad, rad, 0, math.pi / 2)
    ctx.arc(rx + rad, ry + rh - rad, rad, math.pi / 2, math.pi)
    ctx.arc(rx + rad, ry + rad, rad, math.pi, 3 * math.pi / 2)
    ctx.close_path()

    ctx.stroke()
    ctx.restore()


def annotate_image(
    raw_path: str,
    final_path: str,
    annotations: List[Dict[str, Any]],
    color: Tuple[float, float, float] = (0.145, 0.388, 0.922),
) -> bool:
    """
    annotations: list of dicts:
      {
        'num': '1',
        'badge': (badge_x, badge_y),
        'target': (target_x, target_y),
        'box': (x, y, w, h) [optional]
      }
    """
    if not HAVE_CAIRO:
        print("[ERROR] PyCairo ('cairo') is not installed in the Python environment.")
        return False

    try:
        valid_raw = validate_workspace_path(raw_path, must_exist=True)
        valid_final = validate_workspace_path(final_path, must_exist=False)
    except Exception as err:
        print(f"[ERROR] Path validation failed: {err}")
        return False

    try:
        surface = cairo.ImageSurface.create_from_png(valid_raw)
        ctx = cairo.Context(surface)

        for item in annotations:
            box = item.get("box")
            if box:
                # If box is [x1, y1, x2, y2], convert to (x, y, w, h)
                if len(box) == 4:
                    bx, by, b3, b4 = box
                    # Detect if 3rd and 4th are coordinates x2,y2 or width,height
                    if b3 > bx and b4 > by and (b3 - bx > 50 or b4 - by > 50) and "is_coords" in item:
                        bw = b3 - bx
                        bh = b4 - by
                    else:
                        bw = b3
                        bh = b4
                    draw_bounding_highlight(ctx, bx, by, bw, bh, color=color)

            badge = item.get("badge")
            target = item.get("target")
            num = str(item.get("num", ""))
            if badge and target:
                draw_badge_and_arrow(
                    ctx,
                    badge[0],
                    badge[1],
                    target[0],
                    target[1],
                    num,
                    color=color,
                )

        out_dir = os.path.dirname(valid_final)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        surface.write_to_png(valid_final)
        print(f"[OK] Cairo annotated: {valid_final}")
        return True
    except Exception as err:
        print(f"[ERROR] annotate_image failed: {err}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="High-resolution arrow and callout badge annotator using PyCairo."
    )
    parser.add_argument("--input", "-i", required=True, help="Input raw PNG screenshot.")
    parser.add_argument("--output", "-o", required=True, help="Output annotated PNG path.")
    parser.add_argument(
        "--arrow",
        action="append",
        help="Arrow spec 'badge_x,badge_y,target_x,target_y,label'. Can be specified multiple times.",
    )
    parser.add_argument(
        "--box",
        action="append",
        help="Bounding box 'x,y,w,h'. Can be specified multiple times.",
    )
    parser.add_argument(
        "--spec-json",
        help="JSON file containing list of annotation dicts with 'num', 'badge', 'target', and 'box'.",
    )
    args = parser.parse_args()

    if not HAVE_CAIRO:
        sys.exit("Error: PyCairo ('cairo') is required. Install python3-cairo or pycairo.")

    annotations: List[Dict[str, Any]] = []

    if args.spec_json:
        valid_spec = validate_workspace_path(args.spec_json, must_exist=True)
        with open(valid_spec, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                annotations.extend(data)
            elif isinstance(data, dict) and "annotations" in data:
                annotations.extend(data["annotations"])

    for b_arg in args.box or []:
        parts = [float(p.strip()) for p in b_arg.split(",")]
        if len(parts) == 4:
            annotations.append({"box": tuple(parts)})

    for a_arg in args.arrow or []:
        parts = [p.strip() for p in a_arg.split(",")]
        if len(parts) >= 4:
            bx, by, tx, ty = map(float, parts[:4])
            lbl = parts[4] if len(parts) > 4 else str(len(annotations) + 1)
            annotations.append({
                "num": lbl,
                "badge": (bx, by),
                "target": (tx, ty),
            })

    success = annotate_image(args.input, args.output, annotations)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

