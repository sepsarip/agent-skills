#!/usr/bin/env python3
"""
Comprehensive automated test suite verifying fixes for:
1. A4 image scaling bounds & center alignment for both image and caption.
2. Compact arrow placement, guide grid snapping, and local anti-collision nudging.
3. Offline and no-pip environment resilience in check_env.py.
4. python-docx fallback (LibreOffice conversion & Markdown-only modes) without crashing.
5. Flexible schema validation in manual_state.py coverage (arrays, dicts, strings).
"""

import base64
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SKILLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(SKILLS_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from build_manual import _calc_a4_image_dimensions, run_soffice
from capture_and_annotate import find_optimal_arrow_placement
from embed_images import embed_images_in_docx
from annotate_cairo import annotate_image as cairo_annotate_image


class TestUserManualGeneratorFixes(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix=".test_tmp_", dir=os.getcwd())
        # Generate a minimal 1x1 PNG for image testing
        self.dummy_png = os.path.join(self.tmp_dir, "test.png")
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        with open(self.dummy_png, "wb") as f:
            f.write(png_bytes)

        self.sample_spec = {
            "title": "Test Manual",
            "subtitle": "Automated Test Suite",
            "version": "1.0.0",
            "date": "2026-11-02",
            "language": "en",
            "chapters": [
                {
                    "number": 1,
                    "title": "Introduction",
                    "intro": "Welcome to test manual.",
                    "sections": [
                        {
                            "number": "1.1",
                            "title": "First Section",
                            "body": "This is test body content (See Figure 1.1).",
                            "covers": ["feat1"],
                            "figures": [
                                {
                                    "id": "1.1",
                                    "title": "Sample Screenshot",
                                    "image_path": os.path.relpath(self.dummy_png, os.getcwd()),
                                    "bullets": ["**Step 1**: Click the button."],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.spec_file = os.path.join(self.tmp_dir, "manual_spec.json")
        with open(self.spec_file, "w", encoding="utf-8") as f:
            json.dump(self.sample_spec, f, indent=2)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # 1. Issue 5: Robust Inventory Schema in manual_state.py coverage
    # -------------------------------------------------------------
    def test_coverage_with_json_array(self):
        """Verify manual_state.py coverage handles top-level array [...] without 'list' has no attribute 'get'."""
        array_inv = [
            {"id": "feat1", "name": "Feature 1", "route": "/feat1"},
            {"id": "feat2", "name": "Feature 2", "route": "/feat2"},
        ]
        inv_file = os.path.join(self.tmp_dir, "inventory_array.json")
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(array_inv, f)

        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "manual_state.py"),
            "coverage",
            "--spec",
            self.spec_file,
            "--inventory",
            inv_file,
            "--json",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"coverage failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data["total_inventory_features"], 2)
        self.assertEqual(data["covered_count"], 1)
        self.assertEqual(data["missing_count"], 1)

    def test_coverage_with_dict_and_string_items(self):
        """Verify manual_state.py coverage handles object format and list of strings."""
        dict_inv = {"features": ["feat1", "feat_string_only"]}
        inv_file = os.path.join(self.tmp_dir, "inventory_strings.json")
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(dict_inv, f)

        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "manual_state.py"),
            "coverage",
            "--spec",
            self.spec_file,
            "--inventory",
            inv_file,
            "--json",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"coverage failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data["total_inventory_features"], 2)
        self.assertEqual(data["covered_count"], 1)
        self.assertEqual(data["missing_count"], 1)

    # -------------------------------------------------------------
    # 2. Issue 1: A4 Paper Boundaries & Align Center (Image + Caption)
    # -------------------------------------------------------------
    def test_a4_image_dimensions_bounds(self):
        """Verify _calc_a4_image_dimensions keeps images strictly within A4 limits."""
        # Create a tall dummy PNG header: 1000px wide x 2500px tall
        tall_png = os.path.join(self.tmp_dir, "tall.png")
        # Minimal PNG header with 1000x2500 resolution
        import struct
        png_head = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 1000, 2500) + b"\x08\x02\x00\x00\x00"
        with open(tall_png, "wb") as f:
            f.write(png_head + b"\x00" * 64)

        w, h = _calc_a4_image_dimensions(tall_png, max_w=5.8, max_h=5.2)
        self.assertLessEqual(w, 5.8)
        self.assertLessEqual(h, 5.2)
        # For tall 1000x2500 (aspect 0.4), height should hit max 5.2 and width should be ~2.08
        self.assertAlmostEqual(h, 5.2, places=1)
        self.assertAlmostEqual(w, 5.2 * 0.4, places=1)

    def test_build_markdown_centers_image_and_caption(self):
        """Verify build_manual.py centers both image and caption in Markdown."""
        out_dir = os.path.join(self.tmp_dir, "out_md")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "Centered_Manual",
            "--format",
            "md",
            "--verify",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build_manual failed: {res.stderr}")

        md_path = os.path.join(out_dir, "Centered_Manual.md")
        self.assertTrue(os.path.exists(md_path))
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        # Check for centered image and caption div
        self.assertIn('<div align="center">', md_content)
        self.assertIn("<img src=", md_content)
        self.assertIn("<em><b>Figure 1.1: Sample Screenshot</b></em>", md_content)

    # -------------------------------------------------------------
    # 3. Issue 4: python-docx Hard Dependency & Fallback
    # -------------------------------------------------------------
    def test_build_manual_format_md_without_docx(self):
        """Verify --format md builds cleanly without checking or crashing on python-docx."""
        out_dir = os.path.join(self.tmp_dir, "out_md_only")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "MarkdownOnly",
            "--format",
            "md",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Markdown build failed: {res.stderr}")
        self.assertTrue(os.path.exists(os.path.join(out_dir, "MarkdownOnly.md")))
        self.assertFalse(os.path.exists(os.path.join(out_dir, "MarkdownOnly.docx")))

    def test_build_manual_all_format_with_libreoffice_fallback(self):
        """Verify --format all produces both MD and DOCX via LibreOffice fallback without python-docx."""
        out_dir = os.path.join(self.tmp_dir, "out_all")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "FullManual",
            "--format",
            "all",
            "--verify",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Full build failed: {res.stderr}")
        md_file = os.path.join(out_dir, "FullManual.md")
        docx_file = os.path.join(out_dir, "FullManual.docx")
        self.assertTrue(os.path.exists(md_file), "Markdown output missing")
        self.assertTrue(os.path.exists(docx_file), "DOCX output missing from LibreOffice fallback")

        # Verify docx is valid OpenXML zip with working bookmarks & hyperlinks
        import zipfile
        with zipfile.ZipFile(docx_file, "r") as z:
            names = z.namelist()
            self.assertTrue(any("document.xml" in n for n in names))
            doc_xml = z.read("word/document.xml")
            root = ET.fromstring(doc_xml)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            bookmarks = {el.attrib.get(f"{{{ns['w']}}}name") for el in root.iter(f"{{{ns['w']}}}bookmarkStart")}
            hyperlinks = {el.attrib.get(f"{{{ns['w']}}}anchor") for el in root.iter(f"{{{ns['w']}}}hyperlink") if el.attrib.get(f"{{{ns['w']}}}anchor")}
            self.assertGreater(len(hyperlinks), 0, "DOCX has 0 internal hyperlinks")
            self.assertTrue(hyperlinks.issubset(bookmarks), f"Missing bookmarks for hyperlinks: {hyperlinks - bookmarks}")

    # -------------------------------------------------------------
    # 4. Issue 2: Arrow Lengths, Guide Grid Snapping & Anti-Collision
    # -------------------------------------------------------------
    def test_arrow_placement_compact_length_and_grid_snap(self):
        """Verify arrows are compact (<= 90px in open space) and snapped to grid."""
        target = {"x1": 200, "y1": 200, "x2": 300, "y2": 250}
        obstacles = []
        tail_x, tail_y, head_x, head_y = find_optimal_arrow_placement(
            target_box=target,
            label="1",
            obstacles=obstacles,
            img_width=1000,
            img_height=800,
            stroke_width=8,
            grid_snap=10,
        )

        length = math.sqrt((tail_x - head_x) ** 2 + (tail_y - head_y) ** 2)
        # Should be compact, never the old 120-280px
        self.assertLessEqual(length, 90.0, f"Arrow is too long: {length}px")
        # Tail coordinates must be snapped to 10px grid
        self.assertEqual(tail_x % 10, 0, f"tail_x {tail_x} not snapped to 10px grid")
        self.assertEqual(tail_y % 10, 0, f"tail_y {tail_y} not snapped to 10px grid")

    def test_arrow_placement_anti_collision(self):
        """Verify arrow routes around obstacles cleanly."""
        target = {"x1": 200, "y1": 200, "x2": 300, "y2": 250}
        # Place obstacle immediately to the left of target (blocking 180 deg)
        obstacles = [{"x1": 50, "y1": 150, "x2": 195, "y2": 300}]
        tail_x, tail_y, head_x, head_y = find_optimal_arrow_placement(
            target_box=target,
            label="1",
            obstacles=obstacles,
            img_width=1000,
            img_height=800,
            stroke_width=8,
            grid_snap=10,
        )
        # Tail should not be placed inside obstacle
        in_obs = obstacles[0]["x1"] <= tail_x <= obstacles[0]["x2"] and obstacles[0]["y1"] <= tail_y <= obstacles[0]["y2"]
        self.assertFalse(in_obs, f"Arrow tail collided with obstacle: ({tail_x}, {tail_y})")

    # -------------------------------------------------------------
    # 5. Issue 3: check_env.py in Offline / Restricted Environments
    # -------------------------------------------------------------
    def test_check_env_offline_and_profiles(self):
        """Verify check_env.py passes without errors in offline/no-pip environment."""
        # Default run
        res = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "check_env.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"check_env default failed: {res.stderr}")
        self.assertIn("VIABLE FOR CORE WORKFLOW", res.stdout)
        self.assertIn("Word Export (.docx): READY (Engine: libreoffice)", res.stdout)

        # Markdown profile run
        res_md = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "check_env.py"), "--profile", "markdown"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res_md.returncode, 0, "check_env --profile markdown failed")

        # Strict profile run fails as expected when Pillow/Playwright are missing
        res_strict = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "check_env.py"), "--strict"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(res_strict.returncode, 1, "check_env --strict should return 1 when optional pkgs missing")

    # -------------------------------------------------------------
    # 6. DOCX Image Auto-Embedding & A4 Constraint (embed_images.py)
    # -------------------------------------------------------------
    def test_embed_images_in_docx(self):
        """Verify embed_images_in_docx converts r:link to r:embed and constrains extent dimensions."""
        import zipfile
        dummy_docx = os.path.join(self.tmp_dir, "test_embed.docx")

        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<w:body><w:p><w:r>'
            '<w:drawing><wp:inline>'
            '<wp:extent cx="10000000" cy="8000000"/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:blipFill><a:blip r:link="rIdImg1"/></pic:blipFill>'
            '</pic:pic></a:graphicData></a:graphic>'
            '</wp:inline></w:drawing>'
            '</w:r></w:p></w:body></w:document>'
        )
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rIdImg1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="file://{os.path.abspath(self.dummy_png)}" TargetMode="External"/>'
            '</Relationships>'
        )
        ct_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '</Types>'
        )

        with zipfile.ZipFile(dummy_docx, "w") as z:
            z.writestr("word/document.xml", doc_xml)
            z.writestr("word/_rels/document.xml.rels", rels_xml)
            z.writestr("[Content_Types].xml", ct_xml)

        ok = embed_images_in_docx(dummy_docx, max_w_inches=5.8)
        self.assertTrue(ok, "embed_images_in_docx failed on test docx")

        # Inspect modified docx
        with zipfile.ZipFile(dummy_docx, "r") as z:
            mod_doc = z.read("word/document.xml").decode("utf-8")
            mod_rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
            namelist = z.namelist()

            # 1. r:link converted to r:embed
            self.assertIn('r:embed="rIdImg1"', mod_doc)
            self.assertNotIn('r:link="rIdImg1"', mod_doc)

            # 2. Relationship updated to internal media
            self.assertIn('Target="media/image_1.png"', mod_rels)
            self.assertNotIn('TargetMode="External"', mod_rels)

            # 3. File copied into word/media/
            self.assertIn("word/media/image_1.png", namelist)

            # 4. Dimensions constrained: max cx = 5.8 * 914400 = 5303520
            self.assertIn('cx="5303520"', mod_doc)
            self.assertIn('cy="4242816"', mod_doc)

    # -------------------------------------------------------------
    # 7. PyCairo Engine Direct Annotation (annotate_cairo.py)
    # -------------------------------------------------------------
    def test_annotate_cairo(self):
        """Verify annotate_image in annotate_cairo renders arrows, badges, and boxes without errors."""
        out_png = os.path.join(self.tmp_dir, "cairo_annotated.png")
        annotations = [
            {
                "num": "1",
                "badge": (20, 20),
                "target": (80, 80),
                "box": (60, 60, 40, 40),
            }
        ]
        ok = cairo_annotate_image(self.dummy_png, out_png, annotations)
        self.assertTrue(ok, "cairo_annotate_image returned False")
        self.assertTrue(os.path.isfile(out_png), "Output PNG was not created by Cairo annotator")
        self.assertGreater(os.path.getsize(out_png), 0, "Output PNG is empty")

    # -------------------------------------------------------------
    # 8. capture_and_annotate.py Cairo Engine Fallback
    # -------------------------------------------------------------
    def test_capture_and_annotate_cairo_engine(self):
        """Verify capture_and_annotate.py annotate succeeds using Cairo engine."""
        out_png = os.path.join(self.tmp_dir, "cap_cairo_annotated.png")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "capture_and_annotate.py"),
            "annotate",
            "--engine",
            "cairo",
            "--input",
            self.dummy_png,
            "--output",
            out_png,
            "--box",
            "10,10,30,30",
            "--arrow",
            "5,5,15,15,1",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"capture_and_annotate annotate via cairo failed: {res.stderr}")
        self.assertTrue(os.path.isfile(out_png), "Annotated image not generated")
        audit_file = f"{os.path.splitext(out_png)[0]}.arrows.json"
        self.assertTrue(os.path.isfile(audit_file), "Arrows audit file not generated")

    # -------------------------------------------------------------
    # 9. Standarisasi Headless LibreOffice di Sandbox (run_soffice)
    # -------------------------------------------------------------
    def test_run_soffice_sandbox_profile(self):
        """Verify run_soffice executes with isolated temporary user profile in /tmp without failing."""
        res = run_soffice(["--version"], timeout=30)
        self.assertEqual(res.returncode, 0, f"run_soffice failed: {res.stderr}")
        self.assertIn("LibreOffice", res.stdout)

    # -------------------------------------------------------------
    # 10. End-to-End Build with LibreOffice Fallback, Auto-Embed, & PDF Export
    # -------------------------------------------------------------
    def test_build_manual_with_libreoffice_and_embed(self):
        """Verify build_manual.py compiles MD, DOCX (with auto-embedded images), and PDF."""
        out_dir = os.path.join(self.tmp_dir, "manual_build_out")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "TestBuildManual",
            "--format",
            "all",
            "--export-pdf",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build_manual.py failed: {res.stderr}\nOutput: {res.stdout}")

        md_file = os.path.join(out_dir, "TestBuildManual.md")
        docx_file = os.path.join(out_dir, "TestBuildManual.docx")
        pdf_file = os.path.join(out_dir, "TestBuildManual.pdf")

        self.assertTrue(os.path.isfile(md_file), "Markdown output missing")
        self.assertTrue(os.path.isfile(docx_file), "DOCX output missing")
        self.assertTrue(os.path.isfile(pdf_file), "PDF export missing")

        # Check DOCX embedding
        import zipfile
        with zipfile.ZipFile(docx_file, "r") as z:
            namelist = z.namelist()
            media_files = [f for f in namelist if f.startswith("word/media/")]
            self.assertGreaterEqual(len(media_files), 1, "DOCX has no embedded media in word/media/")
            doc_xml = z.read("word/document.xml").decode("utf-8")
            self.assertNotIn("r:link=", doc_xml, "DOCX still contains un-embedded r:link references")

    # -------------------------------------------------------------
    # 11. Cover Page Structure & Logo Placeholder
    # -------------------------------------------------------------
    def test_cover_page_and_logo_placeholder(self):
        """Verify cover page contains title, version, date, and logo placeholder followed by page break."""
        out_dir = os.path.join(self.tmp_dir, "cover_test_out")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "CoverManual",
            "--format",
            "all",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build_manual failed: {res.stderr}")

        # Check Markdown cover
        md_file = os.path.join(out_dir, "CoverManual.md")
        with open(md_file, "r", encoding="utf-8") as f:
            md_text = f.read()
        self.assertIn("[ LOGO APLIKASI ]", md_text)
        self.assertIn("Test Manual", md_text)
        self.assertIn("1.0.0", md_text)
        self.assertIn("2026-11-02", md_text)
        self.assertIn('<div style="page-break-after: always;"></div>', md_text)

        # Check DOCX cover
        import zipfile
        docx_file = os.path.join(out_dir, "CoverManual.docx")
        with zipfile.ZipFile(docx_file, "r") as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")
            self.assertIn("LOGO APLIKASI", doc_xml)
            self.assertIn("Test Manual", doc_xml)
            self.assertIn("1.0.0", doc_xml)

    # -------------------------------------------------------------
    # 12. TOC & Chapter Page Breaks
    # -------------------------------------------------------------
    def test_toc_and_chapter_page_breaks(self):
        """Verify TOC is separated from cover by page break, and Chapter 1 starts on a new page."""
        out_dir = os.path.join(self.tmp_dir, "toc_page_out")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "TOCManual",
            "--format",
            "md",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build_manual md failed: {res.stderr}")

        md_file = os.path.join(out_dir, "TOCManual.md")
        with open(md_file, "r", encoding="utf-8") as f:
            md_text = f.read()

        # Split on page-break-after
        sections = md_text.split('<div style="page-break-after: always;"></div>')
        self.assertGreaterEqual(
            len(sections),
            3,
            "Document should have at least Cover, TOC, and Chapter sections separated by page breaks",
        )
        # Section 0 is Cover
        self.assertIn("Test Manual", sections[0])
        # Section 1 is Table of Contents
        self.assertIn("Table of Contents", sections[1])
        # Section 2 is Chapter 1
        self.assertIn("Chapter 1: Introduction", sections[2])

    # -------------------------------------------------------------
    # 13. Justified Text Alignment (w:jc w:val="both")
    # -------------------------------------------------------------
    def test_justified_text_alignment(self):
        """Verify body text paragraphs and list items are formatted with justified alignment."""
        out_dir = os.path.join(self.tmp_dir, "justify_test_out")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "JustifyManual",
            "--format",
            "docx",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build_manual docx failed: {res.stderr}")

        import zipfile
        docx_file = os.path.join(out_dir, "JustifyManual.docx")
        with zipfile.ZipFile(docx_file, "r") as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")
            self.assertIn('w:val="both"', doc_xml, "DOCX does not contain justified (w:jc both) paragraph alignment")

    # -------------------------------------------------------------
    # 14. Native Bold Formatting in DOCX (No literal **)
    # -------------------------------------------------------------
    def test_markdown_bold_conversion_in_docx(self):
        """Verify markdown **bold** syntax is converted to native Word bold formatting without raw asterisks."""
        spec_copy = dict(self.sample_spec)
        spec_copy["chapters"][0]["sections"][0]["body"] = (
            "Tekan tombol **Simpan** untuk memperbarui data (See Figure 1.1)."
        )
        spec_copy["chapters"][0]["sections"][0]["figures"][0]["bullets"] = [
            "**Langkah 1**: Buka menu **Pengaturan** sistem.",
            "**Langkah 2**: Klik tautan **Ubah Data**.",
        ]
        spec_file = os.path.join(self.tmp_dir, "bold_spec.json")
        with open(spec_file, "w", encoding="utf-8") as f:
            json.dump(spec_copy, f)

        out_dir = os.path.join(self.tmp_dir, "bold_test_out")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "BoldManual",
            "--format",
            "docx",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build_manual docx failed: {res.stderr}")

        import zipfile
        docx_file = os.path.join(out_dir, "BoldManual.docx")
        with zipfile.ZipFile(docx_file, "r") as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")
            self.assertTrue("<w:b/>" in doc_xml or "<w:b " in doc_xml, "DOCX has no bold runs")
            self.assertNotIn("**", doc_xml, "DOCX contains literal ** markdown asterisks")

    # -------------------------------------------------------------
    # 8. Default Output Directory: docs/manual_book
    # -------------------------------------------------------------
    def test_default_out_dir_build_manual(self):
        """Verify build_manual.py defaults --out-dir to docs/manual_book."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--basename",
            "DefaultDirManual",
            "--format",
            "md",
        ]
        res = subprocess.run(cmd, cwd=self.tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build_manual failed: {res.stderr}")
        expected_doc = os.path.join(self.tmp_dir, "docs", "manual_book", "DefaultDirManual.md")
        self.assertTrue(os.path.exists(expected_doc), f"Expected file not found at {expected_doc}")

    def test_default_out_dir_manual_state(self):
        """Verify manual_state.py status parser defaults --out-dir to docs/manual_book."""
        from manual_state import build_parser
        parser = build_parser()
        args = parser.parse_args(["status", "--spec", self.spec_file])
        self.assertEqual(args.out_dir, "docs/manual_book")

    # -------------------------------------------------------------
    # 9. Default Paths and docs/manual_book Unified Structure
    # -------------------------------------------------------------
    def test_default_spec_build_manual(self):
        """Verify build_manual.py parser defaults --spec to docs/manual_book/manual_spec.json."""
        import argparse
        from build_manual import main
        # Test argparse configuration by inspecting build_manual parser arguments
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--help",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("docs/manual_book/manual_spec.json", res.stdout)

    def test_default_paths_manual_state_parser(self):
        """Verify manual_state.py subcommands default to docs/manual_book paths."""
        from manual_state import build_parser
        parser = build_parser()

        # status defaults
        s_args = parser.parse_args(["status"])
        self.assertEqual(s_args.spec, "docs/manual_book/manual_spec.json")
        self.assertEqual(s_args.out_dir, "docs/manual_book")

        # mark defaults
        m_args = parser.parse_args(["mark", "--phase", "outline-approved"])
        self.assertEqual(m_args.progress, "docs/manual_book/manual_progress.json")

        # coverage defaults
        c_args = parser.parse_args(["coverage"])
        self.assertEqual(c_args.spec, "docs/manual_book/manual_spec.json")
        self.assertEqual(c_args.inventory, "docs/manual_book/feature_inventory.json")
        self.assertEqual(c_args.report, "docs/manual_book/manual_gap_report.md")

        # import-md defaults
        i_args = parser.parse_args(["import-md", "--input", "test.md"])
        self.assertEqual(i_args.spec_out, "docs/manual_book/manual_spec.json")

        # renumber defaults
        r_args = parser.parse_args(["renumber"])
        self.assertEqual(r_args.spec, "docs/manual_book/manual_spec.json")

    def test_end_to_end_docs_manual_book_structure(self):
        """Verify complete workflow inside docs/manual_book/ with clean relative image paths."""
        docs_dir = os.path.join(self.tmp_dir, "docs", "manual_book")
        raw_assets = os.path.join(docs_dir, "assets", "raw")
        final_assets = os.path.join(docs_dir, "assets", "final")
        os.makedirs(raw_assets, exist_ok=True)
        os.makedirs(final_assets, exist_ok=True)

        # Place raw image and copy to final
        sample_raw = os.path.join(raw_assets, "sample_screen.png")
        sample_final = os.path.join(final_assets, "sample_screen.png")
        shutil.copy2(self.dummy_png, sample_raw)
        shutil.copy2(self.dummy_png, sample_final)

        # Create docs/manual_book/manual_spec.json
        spec_content = {
            "title": "Clean Structure Manual",
            "version": "1.0.0",
            "date": "2026-11-02",
            "language": "en",
            "chapters": [
                {
                    "number": 1,
                    "title": "Authentication",
                    "intro": "Access guide.",
                    "sections": [
                        {
                            "number": "1.1",
                            "title": "Login Screen",
                            "body": "Enter credentials (See Figure 1.1).",
                            "covers": ["feat-auth"],
                            "figures": [
                                {
                                    "id": "1.1",
                                    "title": "Main Login Screen",
                                    "image_path": "docs/manual_book/assets/final/sample_screen.png",
                                    "source": {
                                        "raw": "docs/manual_book/assets/raw/sample_screen.png",
                                        "url": "http://localhost:3000/login",
                                    },
                                    "bullets": ["**Step 1**: Enter email."],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        spec_file = os.path.join(docs_dir, "manual_spec.json")
        with open(spec_file, "w", encoding="utf-8") as f:
            json.dump(spec_content, f, indent=2)

        # 1. Run mark with default --progress
        cmd_mark = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "manual_state.py"),
            "mark",
            "--progress",
            "docs/manual_book/manual_progress.json",
            "--phase",
            "outline-approved",
        ]
        res_mark = subprocess.run(cmd_mark, cwd=self.tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res_mark.returncode, 0, f"mark failed: {res_mark.stderr}")
        self.assertTrue(os.path.exists(os.path.join(docs_dir, "manual_progress.json")))

        # 2. Run build_manual with default --spec and default --out-dir
        cmd_build = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--basename",
            "AppManual",
            "--format",
            "md",
        ]
        res_build = subprocess.run(cmd_build, cwd=self.tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res_build.returncode, 0, f"build failed: {res_build.stderr}")

        # Verify output markdown exists in docs/manual_book/AppManual.md
        md_file = os.path.join(docs_dir, "AppManual.md")
        self.assertTrue(os.path.exists(md_file), f"AppManual.md not found at {md_file}")

        # Check clean relative path in Markdown: assets/final/sample_screen.png (no workspace/ or ../../)
        with open(md_file, "r", encoding="utf-8") as f:
            md_text = f.read()
        self.assertIn("assets/final/sample_screen.png", md_text)
        self.assertNotIn("workspace/", md_text)

        # 3. Create feature inventory and run coverage with defaults
        inventory = {
            "features": [
                {"id": "feat-auth", "name": "Login Feature", "route": "/login"},
                {"id": "feat-extra", "name": "Extra Feature", "route": "/extra"},
            ]
        }
        inv_file = os.path.join(docs_dir, "feature_inventory.json")
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2)

        cmd_cov = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "manual_state.py"),
            "coverage",
        ]
        res_cov = subprocess.run(cmd_cov, cwd=self.tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res_cov.returncode, 0, f"coverage failed: {res_cov.stderr}")

        # Verify gap report created at docs/manual_book/manual_gap_report.md
        report_file = os.path.join(docs_dir, "manual_gap_report.md")
        self.assertTrue(os.path.exists(report_file), f"manual_gap_report.md not found at {report_file}")
        with open(report_file, "r", encoding="utf-8") as f:
            report_text = f.read()
        self.assertIn("feat-auth", report_text)
        self.assertIn("feat-extra", report_text)

    # -------------------------------------------------------------
    # 7. Elimination of Daftar Gambar & Paper Margins / Header & Footer
    # -------------------------------------------------------------
    def test_no_list_of_figures_in_markdown(self):
        """Verify build_manual.py does not generate List of Figures / Daftar Gambar in Markdown."""
        out_dir = os.path.join(self.tmp_dir, "out_no_lof_md")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "NoLofManual",
            "--format",
            "md",
            "--verify",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build failed: {res.stderr}")
        md_file = os.path.join(out_dir, "NoLofManual.md")
        self.assertTrue(os.path.exists(md_file))
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("List of Figures", content)
        self.assertNotIn("Daftar Gambar", content)
        self.assertIn("Table of Contents", content)

    def test_no_list_of_figures_in_docx(self):
        """Verify build_manual.py does not generate List of Figures / Daftar Gambar in DOCX."""
        out_dir = os.path.join(self.tmp_dir, "out_no_lof_docx")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "build_manual.py"),
            "--spec",
            self.spec_file,
            "--out-dir",
            out_dir,
            "--basename",
            "NoLofDocx",
            "--format",
            "all",
            "--verify",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"build failed: {res.stderr}")
        docx_file = os.path.join(out_dir, "NoLofDocx.docx")
        self.assertTrue(os.path.exists(docx_file))

        import zipfile
        with zipfile.ZipFile(docx_file, "r") as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")
        self.assertNotIn("List of Figures", doc_xml)
        self.assertNotIn("Daftar Gambar", doc_xml)
        self.assertIn("Table of Contents", doc_xml)

    def test_apply_a4_page_setup_margins_and_distances(self):
        """Verify _apply_a4_page_setup sets 1-inch margins and 0.5-inch header/footer distance."""
        from build_manual import _apply_a4_page_setup

        class DummySection:
            page_width = None
            page_height = None
            top_margin = None
            bottom_margin = None
            left_margin = None
            right_margin = None
            header_distance = None
            footer_distance = None

        sec = DummySection()
        _apply_a4_page_setup(sec)
        self.assertAlmostEqual(sec.page_width.inches, 8.27, places=2)
        self.assertAlmostEqual(sec.page_height.inches, 11.69, places=2)
        self.assertAlmostEqual(sec.top_margin.inches, 1.0, places=2)
        self.assertAlmostEqual(sec.bottom_margin.inches, 1.0, places=2)
        self.assertAlmostEqual(sec.left_margin.inches, 1.0, places=2)
        self.assertAlmostEqual(sec.right_margin.inches, 1.0, places=2)
        self.assertAlmostEqual(sec.header_distance.inches, 0.5, places=2)
        self.assertAlmostEqual(sec.footer_distance.inches, 0.5, places=2)

    def test_embed_images_constrains_height_and_width(self):
        """Verify embed_images_in_docx constrains both width (<= 5.8in) and height (<= 5.2in)."""
        # Create a mock docx containing an oversized image (both wide and tall)
        import zipfile
        mock_docx = os.path.join(self.tmp_dir, "oversized.docx")
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<w:body>'
            '<w:p><w:r><w:drawing>'
            '<wp:inline><wp:extent cx="10000000" cy="12000000"/><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:blipFill><a:blip r:link="rIdImg1"/></pic:blipFill>'
            '</pic:pic></a:graphicData></a:graphic></wp:inline>'
            '</w:drawing></w:r></w:p>'
            '</w:body></w:document>'
        )
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rIdImg1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="file://{self.dummy_png}" TargetMode="External"/>'
            '</Relationships>'
        )
        types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '</Types>'
        )
        with zipfile.ZipFile(mock_docx, "w") as z:
            z.writestr("word/document.xml", doc_xml)
            z.writestr("word/_rels/document.xml.rels", rels_xml)
            z.writestr("[Content_Types].xml", types_xml)

        res = embed_images_in_docx(mock_docx, max_w_inches=5.8, max_h_inches=5.2)
        self.assertTrue(res)

        with zipfile.ZipFile(mock_docx, "r") as z:
            updated_xml = z.read("word/document.xml").decode("utf-8")

        # Extract cx and cy
        import re
        m = re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"', updated_xml)
        self.assertIsNotNone(m)
        cx, cy = int(m.group(1)), int(m.group(2))
        self.assertLessEqual(cx, int(5.8 * 914400))
        self.assertLessEqual(cy, int(5.2 * 914400))


if __name__ == "__main__":
    unittest.main()
