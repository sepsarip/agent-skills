# Copywriting & Layout Standards for End-User Manuals

Use these guidelines when writing content for `manual_spec.json` to ensure the manual book is easy to scan, accurate, beautifully formatted, and easily understandable for non-technical end users.

---

## 1. Language, Tone of Voice, & Non-Technical Copywriting

### Audience & Tone
- **Audience**: General employees, administrative staff, operations teams, and everyday business users. They want to accomplish tasks smoothly without encountering software engineering jargon.
- **Tone**: Direct, instructional, courteous, and practical.
- **Default Language**: **English (`"en"`)** by default. Switch to Bahasa Indonesia (`"id"`) or another language when requested by the user.

### Strict Ban on Technical Developer Jargon
Never use developer, database, or network architecture terms in the manual book text. Always translate system behavior into user actions and visible on-screen elements:

| ❌ Forbidden Technical Term | ✅ Recommended Non-Technical Alternative (English) | ✅ Alternatif Bahasa Awam (Indonesia) |
|---|---|---|
| API endpoint / REST route | The page / The feature | Halaman / Fitur terkait |
| POST / PUT / mutation request | Saving data / Submitting the form | Menyimpan data / Mengirimkan formulir |
| JSON payload / request body | Form details / Input data | Data yang dimasukkan / Formulir |
| Bearer token / auth header | Active login session | Sesi login Anda |
| 401 / 403 Unauthorized | Session expired / Insufficient permissions | Sesi login berakhir / Akun tidak memiliki hak akses |
| Database record / SQL query | Saved item / Data list | Data yang tersimpan / Daftar data |
| DOM element / CSS selector | On-screen field, button, or menu | Kolom input, tombol, atau menu pada layar |
| Frontend rendering / client-side | The application displays... | Sistem menampilkan... |
| Backend exception / stack trace | System notification message | Pesan pemberitahuan dari sistem |

### Formatting Rules
- **UI Elements**: Wrap exact interface labels, button names, menus, and field names in **Bold** (for example: Klik tombol **Simpan**, lalu pilih menu **Unduh Laporan**).
- **Paragraph & Bullet Alignment**: All body text paragraphs and step-by-step bullet points must be **Justified** (rata kiri-kanan).
- **Punctuation**: Do not use em-dashes (`—`) or en-dashes (`–`). Use commas, colons, periods, or parentheses.

---

## 2. Chapter-Based Citation & Caption System

Every screenshot must be anchored to the text through a strict citation and caption pair:

1. **In-Text Citation**: Introduce the context before showing the image and include an explicit reference in parentheses.
   - *English Default*: `To access your workspace, open the authentication page and enter your registered credentials (See Figure 1.1).`
   - *Bahasa Indonesia*: `Untuk masuk ke dalam sistem, buka halaman utama dan masukkan data akun yang telah terdaftar (Lihat Gambar 1.1).`
2. **Figure Caption & Alignment**: Place the numbered caption immediately below the screenshot using the format `Figure <ChapterNumber>.<SequenceNumber>: <Short Description>` (or `Gambar <NomorBab>.<NomorUrut>: <Deskripsi Singkat>` in Indonesian).
   - *English Default*: `Figure 1.1: User Authentication and Login Screen`
   - *Bahasa Indonesia*: `Gambar 1.1: Halaman Login dan Autentikasi Pengguna`
   - **Alignment & Sizing**: Both the image and the figure caption must be center-aligned (`align center`). Images are scaled to fit comfortably within standard A4 paper margins (maximum 5.8 inches wide and 5.2 inches high) so they never overflow paper boundaries or push captions onto orphaned pages.

---

## 3. Concise Bullet-Point Explanations & Arrow Placement

Immediately following each figure caption, explain the screen elements or step-by-step actions using concise bullet points:

- **Limit**: 2 to 5 bullet points per screenshot. If a workflow has more than 5 steps, split it into two screenshots so visual arrows do not clutter the screen.
- **Structure per Bullet**: `**[Arrow Number / Element Name]**: [Concise action instruction] -> [Expected outcome].`
- **Text Alignment**: All bullet points are styled as **Justified** (rata kiri-kanan).
- **Avoid Text Occlusion**:
  - Never place arrowhead tips or callout badges directly over button text, input labels, or instructions.
  - Arrows point to the border or corner of the target element.
  - The tail badge starts in clean whitespace outside the UI control.
  - Use `scripts/capture_and_annotate.py annotate --auto` or `scripts/annotate_cairo.py` to draw crisp, anti-aliased arrows and badges.

---

## 4. Table of Contents & Pagination Hierarchy

### Front Matter vs. Main Content Pagination
- **Cover Page (1 Full Page)**:
  - Must occupy its own standalone full page with a strict page break before the Table of Contents.
  - Contains:
    1. **Logo Placeholder**: Visual dashed box `[ LOGO APLIKASI ]` (or real logo image if `"logo_path"` is specified in `manual_spec.json`).
    2. **Title**: Primary manual book title in large bold font (26pt).
    3. **Subtitle**: Clear, descriptive subtitle explaining the target user role.
    4. **Metadata**: Version (`Versi`) and Generation / Update Date (`Tanggal Pembaruan`).
  - Contains **no page number** in the footer.
- **Front Matter (Page 2: Table of Contents)**:
  - Table of Contents (*Daftar Isi*) occupies Page 2. List of Figures (*Daftar Gambar*) is omitted/not required.
  - Numbered using lowercase Roman numerals (`i`, `ii`...).
  - Followed by a strict page break so Chapter 1 begins on a brand new page.
- **Main Content (Page 3+: Chapters 1..N)**:
  - Numbered using Arabic numerals starting at `1` (`1`, `2`, `3`...).
  - **Chapter 1** always starts on a fresh page immediately after the Table of Contents.
  - Each subsequent Chapter begins on a new page.
  - Paragraphs and bullet points are formatted as **Justified** (rata kiri-kanan).
  - Bold text (`**text**`) is rendered as true native bold formatting in Word documents and PDFs.

### Page Margins, Header, & Footer Standards
- **A4 Paper Dimensions**: Standard A4 (210mm x 297mm / 8.27" x 11.69").
- **Page Margins**: Standard 1.0 inch (2.54 cm / 1440 dxa) on all sides (Top, Bottom, Left, Right).
- **Header & Footer Distance**: 0.5 inches (1.27 cm / 720 dxa) from the paper edge.
- **Header Content**: Clean blank header (preserving clean whitespace) across all sections.
- **Footer Content**:
  - Cover page: No footer.
  - Front matter (TOC): Lowercase Roman numerals (`i`, `ii`...).
  - Main chapters: Arabic numerals (`1`, `2`, `3`...).
- **Strict Content Boundary Rules**: Content must strictly stay within the 1.0-inch margins. TOC dot-leader tab stops align at the printable margin boundary (9029 dxa / 6.27 inches for A4) and images are constrained to a maximum of 5.8 inches wide and 5.2 inches high so no elements overflow.

---

## 5. JSON Specification Schema (`manual_spec.json`)

Pass a JSON file with this exact structure to `scripts/build_manual.py`:

```json
{
  "title": "Smart Inventory Application User Manual",
  "subtitle": "Step-by-Step Guide for Warehouse Staff and Administrators",
  "version": "1.0.0",
  "date": "2026-10-30",
  "language": "en",
  "logo_path": "docs/manual_book/assets/raw/app_logo.png",
  "chapters": [
    {
      "number": 1,
      "title": "System Access and Authentication",
      "intro": "This chapter explains how to sign in to the application securely and manage your session.",
      "sections": [
        {
          "number": "1.1",
          "title": "Signing In to the Application",
          "body": "Open your web browser and navigate to the application URL. Verify that you are on the official login portal before entering your account credentials (See Figure 1.1).",
          "covers": ["auth-login"],
          "figures": [
            {
              "id": "1.1",
              "title": "Main Login Interface",
              "image_path": "docs/manual_book/assets/final/login_screen.png",
              "source": {
                "url": "http://localhost:3000/login",
                "raw": "docs/manual_book/assets/raw/login_screen.png",
                "targets": [
                  "1=input[type='email']",
                  "2=input[type='password']",
                  "3=button[type='submit']"
                ]
              },
              "bullets": [
                "**1. Work Email Field**: Enter your official company email address.",
                "**2. Password Field**: Enter your account password.",
                "**3. Sign In Button**: Click to authenticate and open the Main Dashboard."
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
