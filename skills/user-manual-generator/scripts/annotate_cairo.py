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


def detect_cairo_surface_obstacles(
    surface: "cairo.ImageSurface", cell_size: int = 20
) -> List[Dict[str, float]]:
    """
    Detect text, icons, and high-contrast UI borders directly from a Cairo ImageSurface
    pixel buffer using pure Python stdlib (no Pillow required).
    """
    width = surface.get_width()
    height = surface.get_height()
    if width < cell_size or height < cell_size:
        return []

    stride = surface.get_stride()
    buf = memoryview(surface.get_data())
    cols = max(1, width // cell_size)
    rows = max(1, height // cell_size)
    sample_offsets = (2, 6, 10, 14, 17) if cell_size >= 20 else (1, cell_size // 2)

    dense_rects: List[Dict[str, float]] = []
    for r in range(rows):
        y0 = r * cell_size
        for c in range(cols):
            x0 = c * cell_size
            horiz_hits = 0
            vert_hits = 0
            for dy in sample_offsets:
                y = y0 + dy
                if y + 2 >= height:
                    continue
                row_off = y * stride
                next_row_off = (y + 2) * stride
                for dx in sample_offsets:
                    x = x0 + dx
                    if x + 2 >= width:
                        continue
                    idx = row_off + x * 4
                    idx_r = row_off + (x + 2) * 4
                    idx_d = next_row_off + x * 4
                    horiz = (
                        abs(buf[idx] - buf[idx_r])
                        + abs(buf[idx + 1] - buf[idx_r + 1])
                        + abs(buf[idx + 2] - buf[idx_r + 2])
                    )
                    vert = (
                        abs(buf[idx] - buf[idx_d])
                        + abs(buf[idx + 1] - buf[idx_d + 1])
                        + abs(buf[idx + 2] - buf[idx_d + 2])
                    )
                    if horiz > 90:
                        horiz_hits += 1
                    if vert > 90:
                        vert_hits += 1
                    if horiz_hits >= 1 and vert_hits >= 1 and (horiz_hits + vert_hits) >= 3:
                        break
                if horiz_hits >= 1 and vert_hits >= 1 and (horiz_hits + vert_hits) >= 3:
                    break
            if horiz_hits >= 1 and vert_hits >= 1 and (horiz_hits + vert_hits) >= 3:
                dense_rects.append(
                    {
                        "x1": float(x0),
                        "y1": float(y0),
                        "x2": float(min(width, x0 + cell_size)),
                        "y2": float(min(height, y0 + cell_size)),
                    }
                )
    return dense_rects


def circle_intersects_rect(
    cx: float, cy: float, radius: float,
    rx1: float, ry1: float, rx2: float, ry2: float,
) -> bool:
    min_x, max_x = min(rx1, rx2), max(rx1, rx2)
    min_y, max_y = min(ry1, ry2), max(ry1, ry2)
    closest_x = max(min_x, min(cx, max_x))
    closest_y = max(min_y, min(cy, max_y))
    dx = cx - closest_x
    dy = cy - closest_y
    return (dx * dx + dy * dy) <= (radius * radius)


def rect_intersects_segment(
    rx1: float, ry1: float, rx2: float, ry2: float,
    x1: float, y1: float, x2: float, y2: float, pad: float = 4.0,
) -> bool:
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
    for (ex1, ey1), (ex2, ey2) in [
        ((min_x, min_y), (max_x, min_y)),
        ((max_x, min_y), (max_x, max_y)),
        ((max_x, max_y), (min_x, max_y)),
        ((min_x, max_y), (min_x, min_y)),
    ]:
        denom = (dy * (ex2 - ex1)) - (dx * (ey2 - ey1))
        if abs(denom) < 1e-6:
            continue
        ua = ((dx * (ey1 - y1)) - (dy * (ex1 - x1))) / denom
        ub = (((ex2 - ex1) * (ey1 - y1)) - ((ey2 - ey1) * (ex1 - x1))) / denom
        if 0.0 <= ua <= 1.0 and 0.0 <= ub <= 1.0:
            return True
    return False


_circle_intersects_rect = circle_intersects_rect
_rect_intersects_segment = rect_intersects_segment


def _obs_near_point(obs: Dict[str, float], px: float, py: float, tol: float = 14.0) -> bool:
    return (obs["x1"] - tol) <= px <= (obs["x2"] + tol) and (obs["y1"] - tol) <= py <= (obs["y2"] + tol)


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
    dx = target_x - badge_x
    dy = target_y - badge_y
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return

    ux = dx / dist
    uy = dy / dist

    start_x = badge_x + ux * badge_radius
    start_y = badge_y + uy * badge_radius

    arrow_len = 13.0
    arrow_half_w = 5.5
    base_x = target_x - ux * arrow_len
    base_y = target_y - uy * arrow_len
    shaft_end_x = target_x - ux * (arrow_len * 0.75)
    shaft_end_y = target_y - uy * (arrow_len * 0.75)

    # 1. Draw Arrow Line Shadow
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(5.0)
    ctx.set_source_rgba(0.0, 0.0, 0.0, 0.25)
    ctx.move_to(start_x + 1.5, start_y + 1.5)
    ctx.line_to(shaft_end_x + 1.5, shaft_end_y + 1.5)
    ctx.stroke()
    ctx.restore()

    # 2. Draw Arrow Line White Glow / Outline
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(4.5)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.move_to(start_x, start_y)
    ctx.line_to(shaft_end_x, shaft_end_y)
    ctx.stroke()
    ctx.restore()

    # 3. Draw Arrow Line Main Color
    ctx.save()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(2.5)
    ctx.set_source_rgb(*color)
    ctx.move_to(start_x, start_y)
    ctx.line_to(shaft_end_x, shaft_end_y)
    ctx.stroke()
    ctx.restore()

    # 4. Draw Arrow Head (Triangle)
    norm_x = -uy
    norm_y = ux

    left_x = base_x + norm_x * arrow_half_w
    left_y = base_y + norm_y * arrow_half_w
    right_x = base_x - norm_x * arrow_half_w
    right_y = base_y - norm_y * arrow_half_w

    ctx.save()
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
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

    # 5. Draw Badge Shadow
    ctx.save()
    ctx.arc(badge_x + 1.5, badge_y + 1.5, badge_radius, 0, 2 * math.pi)
    ctx.set_source_rgba(0.0, 0.0, 0.0, 0.3)
    ctx.fill()
    ctx.restore()

    # 6. Draw Badge Body (Circle)
    ctx.save()
    ctx.arc(badge_x, badge_y, badge_radius, 0, 2 * math.pi)
    ctx.set_source_rgb(*color)
    ctx.fill_preserve()
    ctx.set_line_width(2.5)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.stroke()
    ctx.restore()

    # 7. Draw Number Text
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
    allow_overlap: bool = False,
) -> bool:
    """
    annotations: list of dicts:
      {
        'num': '1',
        'badge': (badge_x, badge_y),
        'target': (target_x, target_y),
        'box': (x, y, w, h) [optional],
        'is_coords': bool [optional, True if box is (x1, y1, x2, y2)]
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
        width = surface.get_width()
        height = surface.get_height()
        obstacles = detect_cairo_surface_obstacles(surface)
        ctx = cairo.Context(surface)

        badge_r = 18.0
        final_arrows: List[Dict[str, Any]] = []
        unresolved_collisions = 0

        for item in annotations:
            box = item.get("box")
            if box and len(box) == 4:
                bx, by, b3, b4 = map(float, box)
                if item.get("is_coords"):
                    bw = max(1.0, b3 - bx)
                    bh = max(1.0, b4 - by)
                else:
                    bw = b3
                    bh = b4
                draw_bounding_highlight(ctx, bx, by, bw, bh, color=color)

            badge = item.get("badge")
            target = item.get("target")
            num = str(item.get("num", ""))
            if badge and target:
                bx_c, by_c = float(badge[0]), float(badge[1])
                tx_c, ty_c = float(target[0]), float(target[1])

                def _has_collision(cand_bx: float, cand_by: float) -> bool:
                    for obs in obstacles:
                        if _circle_intersects_rect(
                            cand_bx, cand_by, badge_r,
                            obs["x1"], obs["y1"], obs["x2"], obs["y2"],
                        ):
                            return True
                        if not _obs_near_point(obs, tx_c, ty_c) and _rect_intersects_segment(
                            obs["x1"], obs["y1"], obs["x2"], obs["y2"],
                            cand_bx, cand_by, tx_c, ty_c, pad=4.0,
                        ):
                            return True
                    return False

                collided = _has_collision(bx_c, by_c)
                if collided and not allow_overlap and width >= 80 and height >= 80:
                    resolved = None
                    for dist_step in (10, 20, 30, 45, 60, 80):
                        for dx, dy in (
                            (0, -dist_step), (0, dist_step), (-dist_step, 0), (dist_step, 0),
                            (-dist_step, -dist_step), (dist_step, -dist_step),
                            (-dist_step, dist_step), (dist_step, dist_step),
                        ):
                            nbx, nby = bx_c + dx, by_c + dy
                            if not (badge_r + 4 <= nbx <= width - badge_r - 4 and badge_r + 4 <= nby <= height - badge_r - 4):
                                continue
                            if math.hypot(tx_c - nbx, ty_c - nby) < 28.0:
                                continue
                            if not _has_collision(nbx, nby):
                                resolved = (nbx, nby)
                                break
                        if resolved:
                            break
                    if resolved:
                        print(
                            f"[GRID-NUDGE] Badge '{num}' nudged from ({bx_c:.0f},{by_c:.0f}) "
                            f"to ({resolved[0]:.0f},{resolved[1]:.0f}) to avoid text occlusion."
                        )
                        bx_c, by_c = resolved
                        collided = False
                    else:
                        unresolved_collisions += 1
                        print(
                            f"[WARNING] Badge/arrow '{num}' at ({bx_c:.0f},{by_c:.0f})->({tx_c:.0f},{ty_c:.0f}) "
                            f"still overlaps detected UI content."
                        )

                draw_badge_and_arrow(ctx, bx_c, by_c, tx_c, ty_c, num, color=color)
                obstacles.append(
                    {
                        "x1": min(bx_c, tx_c) - 16.0,
                        "y1": min(by_c, ty_c) - 16.0,
                        "x2": max(bx_c, tx_c) + 16.0,
                        "y2": max(by_c, ty_c) + 16.0,
                    }
                )
                final_arrows.append(
                    {
                        "x1": bx_c,
                        "y1": by_c,
                        "x2": tx_c,
                        "y2": ty_c,
                        "label": num,
                        "collided": collided,
                    }
                )

        out_dir = os.path.dirname(valid_final)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        surface.write_to_png(valid_final)

        arrows_audit = f"{os.path.splitext(valid_final)[0]}.arrows.json"
        with open(arrows_audit, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "image": valid_final,
                    "engine": "cairo",
                    "unresolved_collisions": unresolved_collisions,
                    "arrows": final_arrows,
                },
                f,
                indent=2,
            )

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
        "--box-coords",
        action="append",
        help="Bounding box 'x1,y1,x2,y2'. Can be specified multiple times.",
    )
    parser.add_argument(
        "--spec-json",
        help="JSON file containing list of annotation dicts with 'num', 'badge', 'target', and 'box'.",
    )
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow manual badge coordinates without auto-nudging away from text.",
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
            annotations.append({"box": tuple(parts), "is_coords": False})

    for bc_arg in args.box_coords or []:
        parts = [float(p.strip()) for p in bc_arg.split(",")]
        if len(parts) == 4:
            annotations.append({"box": tuple(parts), "is_coords": True})

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

    success = annotate_image(
        args.input, args.output, annotations, allow_overlap=args.allow_overlap
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
