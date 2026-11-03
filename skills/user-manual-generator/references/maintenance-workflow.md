# Maintenance, Resume, & Update Workflow

This guide details how to maintain, resume, and extend existing user manuals with `user-manual-generator`.

---

## 1. Task Continuation & Resume Workflow

If the agent process stops abruptly during capture, annotation, or drafting, you can resume immediately without repeating completed work.

Run `manual_state.py status`:
```bash
python3 scripts/manual_state.py status \
  --spec "docs/manual_book/manual_spec.json" \
  --out-dir "docs/manual_book" \
  --basename "Application_User_Manual"
```

The script inspects filesystem timestamps and `docs/manual_book/manual_progress.json` to identify:
1. Figures with raw screenshots already captured.
2. Figures with layout coordinates saved (`.layout.json`).
3. Figures with final annotations completed (`.png` and `.arrows.json`).
4. Figures awaiting visual verification (`verified: true`).
5. Output documents (`.md` and `.docx`) needing compilation or refresh.

It outputs the exact `NEXT ACTION` command to run.

### Marking Visual Verification
After inspecting an annotated image, record its verification milestone:
```bash
python3 scripts/manual_state.py mark \
  --progress "docs/manual_book/manual_progress.json" \
  --figure "1.1" --verified
```

---

## 2. Feature Discovery & Gap Analysis

When updating an existing manual or documenting a newly updated application, compare the codebase against the manual using `manual_state.py coverage`.

### Step 2.1: Extract Feature Inventory from Code
Scan the target application's routes, menus, or navigation bars. Supported code patterns:
- **React / Next.js**: App router (`app/**/page.tsx`), React Router routes (`<Route path="..." />`), sidebar navigation arrays (`navItems = [...]`).
- **Vue / Nuxt**: `pages/**/*.vue`, `router/index.ts`.
- **Laravel / PHP**: `routes/web.php`, Blade navigation menus.
- **Django / Python**: `urls.py`, view route definitions.
- **HTML / Template**: Navigation anchors `<nav>`, `<a href="...">`.

Save the extracted inventory as `docs/manual_book/feature_inventory.json`:
```json
{
  "project": "InventoryApp",
  "version": "2.1.0",
  "features": [
    {
      "id": "auth-login",
      "name": "User Authentication & Sign In",
      "route": "/login",
      "description": "Allows staff to sign in with email and password."
    },
    {
      "id": "item-barcode-scan",
      "name": "Barcode Scanner Ingestion",
      "route": "/items/scan",
      "description": "Scan incoming inventory parcels using connected barcode reader."
    }
  ]
}
```

### Step 2.2: Run Gap Analysis
```bash
python3 scripts/manual_state.py coverage \
  --spec "docs/manual_book/manual_spec.json" \
  --inventory "docs/manual_book/feature_inventory.json" \
  --report "docs/manual_book/manual_gap_report.md"
```

The report categorizes features into:
- **Covered**: Features documented in chapters/sections (mapped via `"covers": ["feature-id"]` or route URL).
- **Missing**: New application features not yet documented in the manual book.
- **Stale**: Features documented in the manual that have been deleted or deprecated from the application.

Present this report to the user to choose which new features to document.

---

## 3. Importing Existing Manuals

To update a manual book created previously without a `manual_spec.json`:

### From Markdown (.md)
Converts headings (H1 title, H2 chapter, H3 section), images, and bullets into a clean `manual_spec.json`, automatically stripping old TOCs and page footers:
```bash
python3 scripts/manual_state.py import-md \
  --input "legacy_manual.md" \
  --spec-out "docs/manual_book/manual_spec.json"
```

### From Word (.docx)
Inspects headings and figure captions directly from a Word document for gap comparison:
```bash
python3 scripts/manual_state.py outline-docx \
  --input "legacy_manual.docx"
```

---

## 4. Renumbering Chapters, Figures, & In-Text Citations

When inserting a new chapter or section in the middle of a manual, manual figure IDs and text citations can easily become misaligned.

Run `manual_state.py renumber`:
```bash
python3 scripts/manual_state.py renumber \
  --spec "docs/manual_book/manual_spec.json"
```

The renumber command:
1. Re-indexes chapters sequentially (`1`, `2`, ...).
2. Re-indexes sections (`1.1`, `1.2`, ...).
3. Re-indexes figures (`Figure 1.1`, `Figure 1.2`, etc.).
4. Uses a two-phase replacement pipeline (UUID tokens) to safely update all in-text citations (`Figure X.Y`, `See Figure X.Y`, `Gambar X.Y`, `Lihat Gambar X.Y`) in section bodies, chapter intros, and bullets without cascading ID collisions.

---

## 5. Output Archiving & Non-Destructive Builds

When running `build_manual.py`, previous versions of `.md` and `.docx` are automatically copied to `docs/manual_book/archive/<basename>_<timestamp>/` before being overwritten. No previous manual books are deleted.

