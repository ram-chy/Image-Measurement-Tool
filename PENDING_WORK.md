# Work log

## v1.5.2 — 12 Nov 2026 — ✅ COMPLETE

Token-slip refinements requested by the user:

- Added the **user name** to the token-slip header (stored `created_by_name`).
- Removed the footer note ("Please keep this token slip…").
- Reduced slip fonts to an average of ~9 pt with minimal line spacing.
- The item is now asked for the **paper size before generating** a token
  (`PaperSizeDialog`); the chosen size is preselected in the preview/print
  dialog.
- Version bumped 1.5.1 → **1.5.2** in `image_analyzer\__init__.py`,
  `version_info.txt`, `ImageMeasureTool_Setup.iss`, README.

## v1.5.1 — 11 Nov 2026 — ✅ COMPLETE


User-requested corrections on top of v1.5.0:

### 1. Item-prefixed file names (rename correction)
- Moved files now **keep their original name** with the Item added in front:
  `IMG_001.jpg` + Item `Sharma-House` → `Sharma-House_IMG_001.jpg`.
- Name clashes still get `_1`, `_2` … (`Sharma-House_IMG_001_1.jpg`).
- `image_analyzer\ui\main_window.py` — `_apply_item_prefix()`, the move
  confirmation text, the no-item question text and the Item tooltip.
- `README.md` rename-format section updated.

### 2. Custom paper size for token slips
- New **Custom size** option in the token preview's print-size dropdown,
  with **W × H fields in millimetres** (defaults 100 × 150 mm).
- `image_analyzer\core\token_report.py` — `build_token_html(..., fmt,
  custom_width_mm=...)`: custom widths ≥170 mm use the A4 layout, ≥100 mm
  the A5 layout, narrower ones the compact thermal layout.
- `image_analyzer\ui\token.py` — `TokenPreviewDialog` gains the W/H spin
  boxes; the chosen size is applied to printing and PDF export; paper
  narrower than 100 mm gets the small thermal margins (3 mm, else 12 mm).

### 3. Bug fix found while testing (same-name files in one batch)
- `update_moved_to()` matched records by session + file name only, so when
  a batch contained two files with the same original name the History
  records pointed at the wrong destination. It now also matches the
  original file path (optional `orig_path`, backwards compatible), and
  `_move_files()` passes it. No other behaviour changed.

### 4. Version
- Bumped 1.5.0 → **1.5.1** in `image_analyzer\__init__.py`,
  `version_info.txt`, `ImageMeasureTool_Setup.iss`, README.

### Verification
- `python test_v150.py` → **102 passed, 0 failed** (rename helpers, token
  HTML, TokenWindow, backup, custom paper size incl. printer page setup,
  full move flow with same-name duplicates).
- Built `dist\ImageMeasureTool.exe` and
  `installer\ImageMeasureTool_Setup_v1.5.1.exe` via `build_installer.ps1`.
- Copied the installer to the desktop; EXE launch verified (login window
  shows Version 1.5.1).

## v1.5.0 — 10 Nov 2026 — ✅ COMPLETE

- Item-only file names (`Item.ext`), Item field removed from the token
  window (item carried internally + stored with the token), Item row
  removed from the token slip, minimize button on the Token window, new
  Backup feature (verified daily copy, only the latest kept). See the git
  history / README for details.

## Remaining manual step (end user)

- Run `ImageMeasureTool_Setup_v1.5.1.exe` from the desktop and install it
  over the old v1.4.x/v1.5.0 installation (data is kept in
  `%LOCALAPPDATA%\ImageMeasurementTool`). Old installers on the desktop
  (`…_v1.4.1.exe`, `…_v1.5.0.exe`) can be deleted afterwards.
