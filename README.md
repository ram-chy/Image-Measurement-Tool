# Image Measurement & Report Tool

Desktop app that analyses image metadata (DPI, pixel size, physical size, colour
mode), keeps a date-wise SQLite history, exports Excel reports, and can move the
analysed files to a destination folder. It also includes a multi-user login,
customer records, and printable token slips.

Highlights:

- **Multi-user login** with an administrator account; admins can add users,
  reset passwords and delete accounts.
- **Customer details** (name, mobile) are saved and can be reused.
- **Item-prefixed file names:** enter an Item name before Move Files and every
  moved file keeps its original name with the Item added in front
  (e.g. `IMG_001.jpg` + Item `Sharma-House` → `Sharma-House_IMG_001.jpg`;
  name clashes become `Sharma-House_IMG_001_1.jpg`, `_2`, …).
- **Separate Token Generation window** (with a **minimize button**): after a
  successful move the renamed file list is sent there and the analysis list
  clears automatically for the next batch. New batches are appended to the same
  token window. The Item name is carried automatically with the moved files —
  there is no separate Item field to type.
- **Token picking:** each file has a tick box plus a **Select all** option, so
  only the chosen files go on the slip; the rest stay for the next token.
- **Token slips** show the customer, mobile, file names, each file's
  **width × height in feet and inches**, and colour modes — printable on
  **A4, A5, 80 mm thermal paper, or a custom size** (width × height in mm),
  or saved as PDF.
- **Token records:** every generated token is stored in the database (with its
  Item name) and can be re-opened, printed or exported later from
  **Token Records**.
- **Backup:** choose a backup folder and let the app save a verified copy of the
  database once a day. The previous backup is replaced automatically, so only
  the latest backup is kept.
- Drag & drop images **or folders anywhere in the window** (not just the dashed box).
- Large, readable **14 pt minimum** UI font throughout.
- Double-click any row (main table or History) to open an **image preview** with
  its measurements.
- History window: **Refresh Locations** re-checks every file on disk — found
  files show their real status, missing ones show **Moved ✔**.
- History window: **Export** the current view to a formatted **Excel** or **CSV**
  file.
- Date-wise history search, Excel reports, and move-with-verification.

## Install (end users)

Run **`installer/ImageMeasureTool_Setup_v1.5.1.exe`** and follow the wizard.

- Installs to `C:\Program Files\Image Measurement Tool`
- Start Menu shortcut (and optional Desktop shortcut)
- Uninstall via *Settings → Apps* or the Start Menu shortcut
- Measurement history is kept in `%LOCALAPPDATA%\ImageMeasurementTool\image_reports.db`
  (survives uninstall; delete that folder manually to wipe it)

The installer needs administrator rights (it writes to Program Files) and runs
the app as the logged-in user afterwards.

On first launch the app asks you to create the **administrator account**
(display name, username, password). Sign in with it afterwards. Additional users
can be created from the **Users** button (administrators only).

## Run from source

```bat
pip install -r requirements.txt
python main.py
```

Verify the current feature set with the regression suite (runs offscreen,
uses a scratch data dir, needs no display):

```bat
python test_v150.py
```

## Rebuild the installer

Requirements: Python 3.10+ with the packages from `requirements.txt`,
PyInstaller, and [Inno Setup 6](https://jrsoftware.org/isdl.php).

```powershell
powershell -ExecutionPolicy Bypass -File .\build_installer.ps1
```

The script builds `dist\ImageMeasureTool.exe` (PyInstaller, one-file, no console)
and then compiles `installer\ImageMeasureTool_Setup_v1.5.1.exe`.

## Project layout

| Path | Purpose |
| --- | --- |
| `main.py` | App entry point + login flow |
| `test_v150.py` | Offscreen verification suite for the v1.5.0 feature set |
| `image_analyzer/core/analyzer.py` | Pillow-based metadata extraction |
| `image_analyzer/core/database.py` | SQLite history, users, customers, tokens |
| `image_analyzer/core/reporter.py` | Excel report generation |
| `image_analyzer/core/token_report.py` | Token-slip HTML (print/PDF) |
| `image_analyzer/core/backup.py` | Database backup (verified copy, latest kept) |
| `image_analyzer/ui/main_window.py` | PyQt6 UI |
| `image_analyzer/ui/login.py` | Login, first-run setup, user management |
| `image_analyzer/ui/token.py` | Token entry, preview, printing, PDF export |
| `image_analyzer/ui/preview.py` | Image preview dialog |
| `image_analyzer/ui/backup.py` | Backup settings dialog |
| `ImageMeasureTool.spec` | PyInstaller build spec (icon + version info) |
| `ImageMeasureTool_Setup.iss` | Inno Setup installer script |
| `assets/app.ico` | App/installer icon (`assets/make_icon.py` regenerates it) |

---

© 2026 Ram Chowdhury  •  +91 9123754092
