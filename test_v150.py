"""
Verification suite for the v1.5.0 changes listed in PENDING_WORK.md.

Covers: rename helpers, token slip HTML (no Item row), TokenWindow (no Item
field, minimize button, hidden item), backup core + dialog, and the full
move flow with offscreen Qt UIs.

Run:  python test_v150.py
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # set before any PyQt6 import
if hasattr(sys.stdout, "reconfigure"):        # Windows console may be cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Redirect the data dir to a scratch folder BEFORE importing the app ────────
TMP = Path(tempfile.mkdtemp(prefix="imt_test_"))

import image_analyzer.core.database as database
import image_analyzer.core.backup as backup_mod

_orig_data_dir = database._data_dir
_orig_db_path = database._db_path
database._data_dir = lambda: TMP
backup_mod._data_dir = lambda: TMP
backup_mod._db_path = _orig_db_path          # same function object, uses patched _data_dir

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog

APP = QApplication([])          # required before constructing any widget

from image_analyzer import __version__
from image_analyzer.core.analyzer import analyze_multiple
from image_analyzer.core.database import (
    init_db, save_session, create_token, fetch_tokens, fetch_customers,
    fetch_records_for_session,
)
from image_analyzer.core.token_report import build_token_html
from image_analyzer.core.backup import (
    get_backup_settings, set_backup_settings, create_backup,
    maybe_run_daily_backup, backup_path, BACKUP_FILENAME, OLD_BACKUP_GLOB,
)
from image_analyzer.ui import main_window as mw_mod
from image_analyzer.ui.main_window import (
    MainWindow, _apply_item_prefix, _unique_destination, _clean_item_name,
)
from image_analyzer.ui.token import TokenWindow
from image_analyzer.ui.backup import BackupDialog

PASS = 0
FAIL = 0


def check(label: str, condition: bool, extra: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✔ {label}")
    else:
        FAIL += 1
        print(f"  ✘ {label}  {extra}")


def section(title: str):
    print(f"\n── {title} " + "─" * max(0, 58 - len(title)))


class NoButtons:
    """QMessageBox stand-in: every question answers Yes, boxes never block."""
    StandardButton = QMessageBox.StandardButton

    @staticmethod
    def question(*a, **k):
        return QMessageBox.StandardButton.Yes

    @staticmethod
    def information(*a, **k):
        return QMessageBox.StandardButton.Ok

    @staticmethod
    def warning(*a, **k):
        return QMessageBox.StandardButton.Ok

    @staticmethod
    def critical(*a, **k):
        return QMessageBox.StandardButton.Ok


# ══════════════════════════════════════════════════════════════════════════════
def test_version_and_naming_helpers():
    section("Version + rename helpers (Requirement 3)")
    check("package version is 1.5.1", __version__ == "1.5.1", __version__)

    check("IMG_001.jpg + Sharma-House -> Sharma-House_IMG_001.jpg",
          _apply_item_prefix("IMG_001.jpg", "Sharma-House") ==
          "Sharma-House_IMG_001.jpg")
    check("original file name and extension are kept",
          _apply_item_prefix("photo.JPG", "Site-A") == "Site-A_photo.JPG")
    check("empty Item keeps the original name",
          _apply_item_prefix("IMG_001.jpg", "") == "IMG_001.jpg")
    check("whitespace Item keeps the original name",
          _apply_item_prefix("IMG_001.jpg", "   ") == "IMG_001.jpg")
    check("invalid filename characters are cleaned",
          _apply_item_prefix("a.png", 'a/b\\c:d*e?f"g<h>|') ==
          "a_b_c_d_e_f_g_h___a.png",
          _apply_item_prefix("a.png", 'a/b\\c:d*e?f"g<h>|'))

    work = TMP / "unique_dest"
    work.mkdir()
    check("no conflict keeps the name",
          _unique_destination(work, "Sharma-House.jpg").name == "Sharma-House.jpg")
    (work / "Sharma-House.jpg").write_bytes(b"x")
    check("existing file gets _1",
          _unique_destination(work, "Sharma-House.jpg").name == "Sharma-House_1.jpg")
    (work / "Sharma-House_1.jpg").write_bytes(b"x")
    check("both taken gets _2",
          _unique_destination(work, "Sharma-House.jpg").name == "Sharma-House_2.jpg")


def test_token_html():
    section("Token slip HTML (Requirements 1 & 2)")
    token = {
        "token_no": "TKN-000001",
        "created_at": "2026-11-11 10:30:00",
        "customer_name": "Ravi Kumar",
        "customer_mobile": "9876543210",
        "file_count": 2,
        "files": [
            {"file_name": "Sharma-House.jpg", "color_mode": "RGB",
             "width_inch": 24, "height_inch": 18},
            {"file_name": "Sharma-House_1.jpg", "color_mode": "CMYK",
             "width_inch": 12, "height_inch": 6},
        ],
    }
    for fmt in ("a4", "a5", "thermal"):
        html = build_token_html(token, fmt)
        check(f"[{fmt}] no Item row in the header",
              "<b>Item</b>" not in html and ">Item<" not in html)
        check(f"[{fmt}] Token No shown", "TKN-000001" in html)
        check(f"[{fmt}] customer + mobile shown",
              "Ravi Kumar" in html and "9876543210" in html)
        check(f"[{fmt}] file names shown",
              "Sharma-House.jpg" in html and "Sharma-House_1.jpg" in html)
        check(f"[{fmt}] inches + decimal feet shown (24in -> 2.0 ft)",
              "24.0" in html and "2.0 ft" in html and "18.0" in html)
        check(f"[{fmt}] colour modes shown", "RGB" in html and "CMYK" in html)


def test_token_window():
    section("TokenWindow offscreen (Requirements 1, 2 & 4)")
    w = TokenWindow(user={"id": 1, "username": "admin",
                          "display_name": "Admin", "is_admin": True})
    check("window constructs offscreen", True)
    check("no Item field on the form (ed_item removed)",
          not hasattr(w, "ed_item"))
    from PyQt6.QtWidgets import QLabel
    check("no form row is labelled Item",
          not any(l.text().strip().lower().startswith("item")
                  for l in w.findChildren(QLabel)))
    check("minimize button enabled",
          bool(w.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint))

    entries = [
        {"file_name": "Sharma-House.jpg", "color_mode": "RGB",
         "width_inch": 24, "height_inch": 18, "moved_to": "d/Sharma-House.jpg"},
        {"file_name": "Sharma-House_1.jpg", "color_mode": "CMYK",
         "width_inch": 12, "height_inch": 6, "moved_to": "d/Sharma-House_1.jpg"},
    ]
    w.add_files(entries, item="Sharma-House", session_id=7, show=False)
    check("both files appended", len(w._entries) == 2)
    check("hidden item stored from the move batch",
          w._current_item == "Sharma-House")
    check("session id stored", w._session_id == 7)
    check("table shows both rows", w.tbl.rowCount() == 2)

    w.add_files(entries, item="Sharma-House", show=False)
    check("duplicate files are skipped", len(w._entries) == 2)

    # Token generation stores the hidden item and selected files.
    w.ed_name.setText("Ravi Kumar")
    w.ed_mobile.setText("9876543210")
    w.showNormal()
    with mock.patch.object(sys.modules["image_analyzer.ui.token"],
                           "TokenPreviewDialog") as preview:
        preview.return_value = QDialog()
        preview.return_value.exec = lambda: 0
        w._generate()
    tokens = fetch_tokens()
    check("token saved in the database", len(tokens) == 1)
    t = tokens[0]
    check("token record keeps the item", t.get("item") == "Sharma-House",
          str(t.get("item")))
    check("token record keeps 2 files", t.get("file_count") == 2)
    check("generated files leave the window", len(w._entries) == 0)
    check("customer saved for reuse",
          any(c["name"] == "Ravi Kumar" for c in fetch_customers()))
    cust_label = " ".join(f"{c['name']} — {c['mobile']}"
                          for c in fetch_customers())
    check("customer dropdown shows name + mobile only",
          "Ravi Kumar" in cust_label and "Sharma-House" not in cust_label,
          cust_label)

    # A later batch with a different item updates the hidden item, but the
    # item name must never leak into the customer dropdown.
    w.add_files([{"file_name": "Other.jpg", "color_mode": "RGB",
                  "width_inch": 1, "height_inch": 1,
                  "moved_to": "d/Other.jpg"}],
                item="TopSecret-Item", show=False)
    check("later batch updates the hidden item",
          w._current_item == "TopSecret-Item")
    combo_text = " ".join(w.cmb_customer.itemText(i)
                          for i in range(w.cmb_customer.count()))
    check("item name never appears in the customer dropdown",
          "TopSecret-Item" not in combo_text, combo_text)
    w.close()


def test_backup_core():
    section("Backup core (Requirement 5)")
    check("default settings are empty",
          get_backup_settings() == {"backup_dir": "", "auto_backup": False,
                                    "last_backup_date": ""})

    bdir = TMP / "backups"
    settings = set_backup_settings(str(bdir), True)
    check("folder + auto flag round-trip",
          settings["backup_dir"] == str(bdir) and settings["auto_backup"])
    check("changing the folder clears last_backup_date",
          settings["last_backup_date"] == "")

    init_db()                       # create the temp database + tables
    # Put something real in the DB so the backup is non-trivial.
    save_session([])
    create_token(None, "Backup Tester", "9000000001", None, "tester", [],
                 item="Backup-Item")

    path = create_backup(str(bdir))
    check("backup file created", path.exists() and path.name == BACKUP_FILENAME)
    con = sqlite3.connect(path)
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    n_tables = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    con.close()
    check("backup passes integrity check", str(ok).lower() == "ok", str(ok))
    check("backup contains the database schema", n_tables > 0, str(n_tables))
    check("last backup date recorded",
          get_backup_settings()["last_backup_date"] == date.today().isoformat())

    # Fake an old date-stamped backup from a previous version.
    legacy = bdir / "ImageMeasurementTool_Data_Backup_2025-01-01.db"
    legacy.write_bytes(b"old")
    stamp = (path.stat().st_mtime) - 5
    os.utime(path, (stamp, stamp))

    path2 = create_backup(str(bdir))
    check("second backup replaces the first (only one kept)",
          path2 == path and len(list(bdir.glob("*.db"))) == 1,
          str(list(bdir.glob("*.db"))))
    check("old date-stamped backups cleaned up", not legacy.exists())
    check("temp file cleaned up", not (bdir / (BACKUP_FILENAME + ".tmp")).exists())

    check("daily backup skips when already done today",
          maybe_run_daily_backup() is None)
    # Simulate 'not backed up today': clear the date, keep the file.
    st = get_backup_settings()
    st["last_backup_date"] = ""
    from image_analyzer.core.backup import save_settings
    save_settings(st)
    check("daily backup runs when the date is old",
          maybe_run_daily_backup() is not None)
    check("auto backup disabled does nothing",
          set_backup_settings("", False) is not None and
          maybe_run_daily_backup() is None)
    try:
        create_backup("")
        check("no folder raises ValueError", False)
    except ValueError:
        check("no folder raises ValueError", True)


def test_backup_dialog():
    section("BackupDialog offscreen (Requirement 5)")
    set_backup_settings("", False)
    dlg = BackupDialog()
    check("dialog constructs offscreen", True)
    check("starts with no folder", dlg.ed_folder.text() == "")
    check("auto checkbox unticked without folder", not dlg.chk_auto.isChecked())
    check("status explains no folder", "No backup folder" in dlg.lbl_status.text())

    bdir = TMP / "dlg_backups"
    dlg.ed_folder.setText(str(bdir))
    dlg.chk_auto.setChecked(True)
    with mock.patch.object(sys.modules["image_analyzer.ui.backup"],
                           "QMessageBox", NoButtons):
        dlg._save_and_close()
    s = get_backup_settings()
    check("Save persists folder + auto flag",
          s["backup_dir"] == str(bdir) and s["auto_backup"])
    check("closing saved the choice", dlg.result() == QDialog.DialogCode.Accepted)

    dlg2 = BackupDialog()
    check("dialog reloads saved settings",
          dlg2.ed_folder.text() == str(bdir) and dlg2.chk_auto.isChecked())
    with mock.patch.object(sys.modules["image_analyzer.ui.backup"],
                           "QMessageBox", NoButtons):
        dlg2._backup_now()
    check("Backup Now creates a verified copy",
          backup_path(bdir).exists())
    check("status shows latest backup",
          BACKUP_FILENAME in dlg2.lbl_status.text())

    # Auto without a folder must be refused.
    set_backup_settings("", False)
    dlg3 = BackupDialog()
    dlg3.chk_auto.setChecked(True)
    with mock.patch.object(sys.modules["image_analyzer.ui.backup"],
                           "QMessageBox", NoButtons):
        saved = dlg3._save()
    check("auto without folder is refused", saved is False)
    check("auto flag not persisted without folder",
          get_backup_settings()["auto_backup"] is False)


def test_custom_paper_size():
    section("Custom paper size (token slip)")
    token = {
        "token_no": "TKN-000009",
        "created_at": "2026-11-11 09:00:00",
        "customer_name": "Ravi Kumar",
        "customer_mobile": "9876543210",
        "file_count": 1,
        "files": [
            {"file_name": "Sharma-House_IMG_001.jpg", "color_mode": "RGB",
             "width_inch": 12, "height_inch": 6},
        ],
    }

    # Layout mapping: >=170mm -> A4, >=100mm -> A5, narrower -> thermal.
    a4 = build_token_html(token, "a4")
    a5 = build_token_html(token, "a5")
    th = build_token_html(token, "thermal")
    for w, like, label in ((210.0, a4, "210 mm"), (130.0, a5, "130 mm"),
                           (80.0, th, "80 mm")):
        html = build_token_html(token, "custom", custom_width_mm=w)
        check(f"custom {label} uses the matching hand-tuned layout",
              html == like)

    # Unknown width falls back to the compact thermal layout.
    check("custom without width uses the thermal layout",
          build_token_html(token, "custom") == th)

    # Dialog behaviour.
    from image_analyzer.ui.token import TokenPreviewDialog
    from PyQt6.QtCore import QSizeF
    from PyQt6.QtGui import QPageSize
    from PyQt6.QtPrintSupport import QPrinter

    dlg = TokenPreviewDialog(token, None)
    labels = [dlg.cmb_format.itemText(i)
              for i in range(dlg.cmb_format.count())]
    check("'Custom size' offered in the print-size dropdown",
          "Custom size" in labels, str(labels))
    check("custom fields disabled while A4 is selected",
          not dlg.spn_custom_w.isEnabled() and not dlg.spn_custom_h.isEnabled())

    idx = dlg.cmb_format.findData("custom")
    dlg.cmb_format.setCurrentIndex(idx)
    check("custom fields enabled when Custom size is selected",
          dlg.spn_custom_w.isEnabled() and dlg.spn_custom_h.isEnabled())
    check("defaults are 100 x 150 mm",
          dlg.spn_custom_w.value() == 100.0 and dlg.spn_custom_h.value() == 150.0)

    ps = dlg._page_size()
    size_mm = ps.size(QPageSize.Unit.Millimeter)
    check("page size uses the entered width x height",
          abs(size_mm.width() - 100.0) < 0.01 and
          abs(size_mm.height() - 150.0) < 0.01, str(size_mm))
    check("preview html receives the custom width",
          dlg._html_kwargs() == {"custom_width_mm": 100.0})
    check("preview rendered for custom size",
          "TKN-000009" in dlg.browser.toPlainText())

    # Page setup on a PDF printer: exact page + margins (12 mm when wide).
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    dlg._apply_page_setup(printer)
    from PyQt6.QtGui import QPageLayout
    pl = printer.pageLayout()
    pl_size = pl.pageSize().size(QPageSize.Unit.Millimeter)
    m = pl.margins(QPageLayout.Unit.Millimeter)
    check("printer page uses the custom size",
          abs(pl_size.width() - 100.0) < 0.01 and
          abs(pl_size.height() - 150.0) < 0.01, str(pl_size))
    check("wide custom paper gets normal margins", abs(m.left() - 12.0) < 0.01,
          str(m))

    dlg.spn_custom_w.setValue(80.0)     # narrow paper -> thermal-like margins
    dlg._apply_page_setup(printer)
    m2 = printer.pageLayout().margins(QPageLayout.Unit.Millimeter)
    check("narrow custom paper gets thermal margins",
          abs(m2.left() - 3.0) < 0.01, str(m2))
    check("narrow custom width switches the slip layout",
          "font-size:13pt" in dlg.browser.toHtml())

    dlg.cmb_format.setCurrentIndex(dlg.cmb_format.findData("a4"))
    check("switching back to A4 disables custom fields",
          not dlg.spn_custom_w.isEnabled())
    dlg.close()


def test_full_move_flow():
    section("Full move flow — Item-prefixed names")
    from PIL import Image

    # Two different files that both happen to be called IMG_001.jpg, so the
    # duplicate-name handling (_1 suffix) is exercised as well.
    src1 = TMP / "src1"; src1.mkdir()
    src2 = TMP / "src2"; src2.mkdir()
    p1, p2 = src1 / "IMG_001.jpg", src2 / "IMG_001.jpg"
    Image.new("RGB", (1200, 900), (200, 30, 30)).save(
        p1, format="JPEG", dpi=(100, 100))
    Image.new("RGB", (600, 450), (30, 30, 200)).save(
        p2, format="JPEG", dpi=(100, 100))

    mw = MainWindow(user={"id": 1, "username": "admin",
                          "display_name": "Admin", "is_admin": True})
    check("MainWindow constructs offscreen", True)
    check("backup toolbar button exists",
          any(getattr(b, "text", lambda: "")().find("Backup") >= 0
              for b in mw.findChildren(type(mw.btn_move))))
    check("item tooltip mentions the prefixed renaming",
          "in front" in mw.item_edit.toolTip(), mw.item_edit.toolTip())

    results = analyze_multiple([str(p1), str(p2)])
    check("both images analysed OK",
          len(results) == 2 and all(r.status == "OK" for r in results))
    check("measurements extracted",
          all(r.width_inch and r.height_inch for r in results))

    mw._results = results
    mw._file_paths = [str(p1), str(p2)]
    mw._session_id = save_session(results)

    dest = TMP / "moved"
    mw.dest_edit.setText(str(dest))
    mw.item_edit.setText("Sharma-House")
    session_id = mw._session_id      # _clear() resets this after the move

    with mock.patch.object(mw_mod, "QMessageBox", NoButtons):
        mw._move_files()

    check("Item added in front of the original name",
          (dest / "Sharma-House_IMG_001.jpg").exists(),
          str(list(dest.glob("*"))))
    check("same-name duplicate got _1 suffix",
          (dest / "Sharma-House_IMG_001_1.jpg").exists(),
          str(list(dest.glob("*"))))
    check("originals deleted after moving", not p1.exists() and not p2.exists())
    check("analysis list cleared for the next batch",
          mw._results == [] and mw.table.rowCount() == 0)

    tw = mw._token_window
    check("token window opened automatically", tw is not None)
    check("token window received both renamed files",
          tw is not None and len(tw._entries) == 2)
    check("token window received the item",
          tw is not None and tw._current_item == "Sharma-House")
    check("token window linked to the session",
          tw is not None and tw._session_id == session_id)

    rows = fetch_records_for_session(session_id)
    check("database records updated with new names",
          sorted(r["file_name"] for r in rows) ==
          ["Sharma-House_IMG_001.jpg", "Sharma-House_IMG_001_1.jpg"],
          str([r["file_name"] for r in rows]))
    check("database records point into the destination",
          all(r.get("moved_to", "").startswith(str(dest)) for r in rows),
          str([r.get("moved_to") for r in rows]))

    # Moving a second batch into the same folder keeps growing the suffix.
    src3 = TMP / "src3"; src3.mkdir()
    p3 = src3 / "IMG_001.jpg"
    Image.new("RGB", (300, 200), (0, 150, 0)).save(
        p3, format="JPEG", dpi=(100, 100))
    r3 = analyze_multiple([str(p3)])
    mw._results = r3
    mw._file_paths = [str(p3)]
    mw.btn_move.setEnabled(True)
    with mock.patch.object(mw_mod, "QMessageBox", NoButtons):
        mw._move_files()
    check("second batch gets the next free suffix",
          (dest / "Sharma-House_IMG_001_2.jpg").exists(),
          str(list(dest.glob("*"))))
    check("second batch appended to the same token window",
          len(mw._token_window._entries) == 3)
    mw.close()


def main():
    print(f"Scratch data dir: {TMP}")
    try:
        test_version_and_naming_helpers()
        test_token_html()
        init_db()
        test_token_window()
        test_backup_core()
        test_backup_dialog()
        test_custom_paper_size()
        test_full_move_flow()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

    print(f"\n{'=' * 64}")
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print('=' * 64)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
