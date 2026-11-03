#!/usr/bin/env python3
"""
Embed external linked images into DOCX archive, convert r:link to r:embed,
and constrain image dimensions to fit within A4 paper margins.
Part of user-manual-generator agent skill.
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
import zipfile
from typing import Optional


def validate_workspace_path(target_path: str, must_exist: bool = False) -> str:
    """Verify that target_path stays within the active workspace directory."""
    cwd = os.path.realpath(os.getcwd())
    real_target = os.path.realpath(target_path)
    if not (real_target == cwd or real_target.startswith(cwd + os.sep)):
        raise ValueError(
            f"Security Error: Path '{target_path}' escapes the active workspace '{cwd}'."
        )
    if must_exist and not os.path.isfile(real_target):
        raise FileNotFoundError(f"File not found: {real_target}")
    return real_target


def embed_images_in_docx(
    docx_path: str, max_w_inches: float = 5.8, max_h_inches: float = 5.2
) -> bool:
    """
    Post-process a .docx file:
    - Inspect word/_rels/document.xml.rels for image relationships.
    - Copy local image files into word/media/.
    - Convert r:link="rId..." to r:embed="rId..." in word/document.xml.
    - Constrain <wp:extent> and <a:ext> width to max_w_inches (default 5.8) and height to max_h_inches (default 5.2).
    - Ensure [Content_Types].xml includes image extension definitions.
    """
    try:
        valid_docx = validate_workspace_path(docx_path, must_exist=True)
    except Exception as err:
        print(f"[ERROR] {err}")
        return False

    max_cx = int(max_w_inches * 914400)  # 1 inch = 914400 EMUs
    max_cy = int(max_h_inches * 914400)

    temp_dir = tempfile.mkdtemp(prefix="lo_docx_embed_", dir="/tmp")
    try:
        with zipfile.ZipFile(valid_docx, "r") as zin:
            zin.extractall(temp_dir)

        rels_file = os.path.join(temp_dir, "word", "_rels", "document.xml.rels")
        doc_file = os.path.join(temp_dir, "word", "document.xml")

        if not os.path.isfile(rels_file) or not os.path.isfile(doc_file):
            print(f"[NOTICE] {docx_path}: rels or document.xml not found")
            return False

        with open(rels_file, "r", encoding="utf-8") as f:
            rels_content = f.read()

        with open(doc_file, "r", encoding="utf-8") as f:
            doc_content = f.read()

        media_dir = os.path.join(temp_dir, "word", "media")
        os.makedirs(media_dir, exist_ok=True)

        image_rids = set()
        pattern = re.compile(
            r'<Relationship\s+([^>]*?)Id="([^"]+)"([^>]*?)Target="([^"]+)"([^>]*?)/>'
        )

        count = 0
        added_extensions = set()

        def rels_repl(match):
            nonlocal count
            attr1 = match.group(1)
            rid = match.group(2)
            attr2 = match.group(3)
            target = match.group(4)
            attr3 = match.group(5)
            full = match.group(0)

            if "relationships/image" not in full:
                return full

            image_rids.add(rid)
            count += 1

            if target.startswith("file://"):
                local_path = urllib.parse.unquote(target[7:])
            elif target.startswith("media/"):
                local_path = os.path.join(temp_dir, "word", target)
            else:
                local_path = target

            ext = os.path.splitext(local_path)[1].lower() or ".png"
            added_extensions.add(ext.lstrip("."))
            media_name = f"image_{count}{ext}"
            media_dest = os.path.join(media_dir, media_name)

            if os.path.isfile(local_path):
                if os.path.abspath(local_path) != os.path.abspath(media_dest):
                    shutil.copy2(local_path, media_dest)
                print(f"[EMBED] Image {rid}: {local_path} -> word/media/{media_name}")
            else:
                print(f"[WARN] Local image not found: {local_path}")
                return full

            clean_attrs = f"{attr1} {attr2} {attr3}"
            clean_attrs = re.sub(r'\s*TargetMode="[^"]*"', "", clean_attrs)
            clean_attrs = re.sub(r"\s+", " ", clean_attrs).strip()

            return f'<Relationship {clean_attrs} Id="{rid}" Target="media/{media_name}"/>'

        new_rels = pattern.sub(rels_repl, rels_content)
        with open(rels_file, "w", encoding="utf-8") as f:
            f.write(new_rels)

        # 1. Convert r:link to r:embed
        for rid in image_rids:
            doc_content = doc_content.replace(f'r:link="{rid}"', f'r:embed="{rid}"')

        # 2. Constrain image dimensions so they never exceed A4 margins
        def resize_extent(match):
            tag = match.group(1)
            cx = int(match.group(2))
            cy = int(match.group(3))
            rest = match.group(4) or ""
            scale_w = max_cx / cx if cx > max_cx else 1.0
            scale_h = max_cy / cy if cy > max_cy else 1.0
            scale = min(scale_w, scale_h)
            if scale < 1.0:
                new_cx = int(cx * scale)
                new_cy = int(cy * scale)
                print(
                    f"[RESIZE] {tag}: {cx}x{cy} -> {new_cx}x{new_cy} EMUs "
                    f'({new_cx / 914400:.2f}" x {new_cy / 914400:.2f}")'
                )
                return f'<{tag} cx="{new_cx}" cy="{new_cy}"{rest}/>'
            return match.group(0)

        # Match <wp:extent cx="..." cy="..." ... /> and <a:ext cx="..." cy="..." ... />
        doc_content = re.sub(
            r'<((?:wp:extent|a:ext))\s+cx="(\d+)"\s+cy="(\d+)"([^>]*?)/>',
            resize_extent,
            doc_content,
        )

        with open(doc_file, "w", encoding="utf-8") as f:
            f.write(doc_content)

        # 3. Update [Content_Types].xml for image extensions
        ct_file = os.path.join(temp_dir, "[Content_Types].xml")
        if os.path.isfile(ct_file):
            with open(ct_file, "r", encoding="utf-8") as f:
                ct_content = f.read()

            content_type_map = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
                "gif": "image/gif",
            }
            extra_types = ""
            for ext in added_extensions or ["png"]:
                mime = content_type_map.get(ext, f"image/{ext}")
                if f'Extension="{ext}"' not in ct_content:
                    extra_types += f'<Default Extension="{ext}" ContentType="{mime}"/>'

            if extra_types:
                ct_content = ct_content.replace("</Types>", f"{extra_types}</Types>")
                with open(ct_file, "w", encoding="utf-8") as f:
                    f.write(ct_content)

        # 4. Re-pack the docx archive safely
        temp_docx = valid_docx + ".tmp.docx"
        with zipfile.ZipFile(temp_docx, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, temp_dir)
                    zout.write(full_p, rel_p)

        shutil.move(temp_docx, valid_docx)
        print(f"[SUCCESS] Updated {docx_path} with embedded images & A4 bounded dimensions.")
        return True
    except Exception as err:
        print(f"[ERROR] embed_images_in_docx failed: {err}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed external linked images into DOCX archive and constrain dimensions to A4 margins."
    )
    parser.add_argument(
        "--docx",
        "-d",
        required=True,
        help="Path to the .docx document to post-process.",
    )
    parser.add_argument(
        "--max-width",
        "-w",
        type=float,
        default=5.8,
        help="Maximum image width in inches (default: 5.8 for A4 with 1-inch margins).",
    )
    parser.add_argument(
        "--max-height",
        type=float,
        default=5.2,
        help="Maximum image height in inches (default: 5.2 for A4 with 1-inch margins).",
    )
    args = parser.parse_args()

    success = embed_images_in_docx(
        args.docx, max_w_inches=args.max_width, max_h_inches=args.max_height
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

