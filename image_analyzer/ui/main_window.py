"""
Main window — Image Measurement & Report Tool  v4
Changes: v1.5.0 — Item-only moved file names, Token window minimize +
no Item field, daily database backup (folder + auto switch)
"""

import os
import shutil
from dataclasses import asdict
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QMessageBox, QFrame, QSizePolicy,
    QAbstractItemView, QStatusBar, QDialog,
    QDialogButtonBox, QComboBox, QDateEdit, QGroupBox,
    QRadioButton, QButtonGroup, QMenu,
)
from PyQt6.QtCore import Qt, QDate, QStandardPaths, QTimer
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor, QFont

from image_analyzer import __version__, __copyright__
from image_analyzer.core.worker   import AnalysisWorker
from image_analyzer.core.reporter import (
    generate_excel_report,
    export_history_excel,
    export_history_csv,
    format_history_record,
    HISTORY_COLUMNS,
)
from image_analyzer.core.analyzer import ImageInfo
from image_analyzer.core.database import (
    init_db, save_session, update_moved_to,
    fetch_available_dates, fetch_sessions_by_date,
    fetch_records_for_session, fetch_records_by_date,
    refresh_record_locations,
)
from image_analyzer.ui.preview import ImagePreviewDialog
from image_analyzer.ui.login import UserManagementDialog
from image_analyzer.ui.token import TokenWindow
from image_analyzer.ui.backup import BackupDialog
from image_analyzer.core.backup import maybe_run_daily_backup

# ── Palette ───────────────────────────────────────────────────────────────────
C_PRIMARY = "#1565C0"
C_SUCCESS = "#2E7D32"
C_ERROR   = "#C62828"
C_MOVE    = "#6A1B9A"
C_BG      = "#F5F5F5"
C_CARD    = "#FFFFFF"
C_BORDER  = "#E0E0E0"
C_TEXT    = "#212121"
C_SUBTEXT = "#757575"

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff",
                  ".bmp", ".gif", ".webp", ".ico", ".psd",
                  ".eps", ".pdf"}


def _running_as_admin() -> bool:
    """Windows blocks Explorer drag & drop into elevated apps."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

TABLE_COLUMNS = [
    "File Name", "File Format", "DPI (X × Y)",
    "Color Mode", "Width (in)", "Height (in)",
    "Width (ft)", "Height (ft)", "Status",
]

# Characters Windows does not allow in a file name
_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def _clean_item_name(item: str) -> str:
    """Make the Item safe to use as a file-name prefix."""
    text = (item or "").strip()
    for ch in _INVALID_FILENAME_CHARS:
        text = text.replace(ch, "_")
    # Windows also dislikes trailing dots/spaces
    return text.rstrip(" .")


def _apply_item_prefix(file_name: str, item: str) -> str:
    """
    Return the moved file name with the Item added at the start.

    The original file name (with its extension) is kept and the Item name is
    put in front of it, e.g. ``IMG_001.jpg`` with Item ``Sharma-House``
    becomes ``Sharma-House_IMG_001.jpg``.  Duplicate names are handled later
    by ``_unique_destination`` (``Sharma-House_IMG_001_1.jpg``, ...).
    """
    prefix = _clean_item_name(item)
    if not prefix:
        return file_name
    return f"{prefix}_{file_name}"


def _unique_destination(folder: Path, file_name: str) -> Path:
    """Return a path inside `folder` that does not overwrite anything."""
    candidate = folder / file_name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(file_name).stem, Path(file_name).suffix
    counter = 1
    while True:
        candidate = folder / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ═══════════════════════════════════════════════════════════════════════════════
#  Drag-and-drop zone
# ═══════════════════════════════════════════════════════════════════════════════
class DropZone(QFrame):
    _STYLE_IDLE = """
        #DropZone { border:2px dashed #90CAF9; border-radius:10px; background:#E3F2FD; }
        #DropZone:hover { border-color:#1565C0; background:#BBDEFB; }
    """
    _STYLE_ACTIVE = """
        #DropZone { border:2px solid #0D47A1; border-radius:10px; background:#90CAF9; }
    """

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._cb = callback
        self.setAcceptDrops(True)
        self.setObjectName("DropZone")
        self.setMinimumHeight(95)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(self._STYLE_IDLE)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico = QLabel("📂"); ico.setFont(QFont("Segoe UI Emoji", 24))
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt = QLabel("Drag & drop image files or folders anywhere in this window\n"
                     "— or click  Browse  to add files")
        txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        # Let drag events reach the frame instead of being swallowed by the labels
        for child in (ico, txt):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(ico); lay.addWidget(txt)

    def _set_active(self, active: bool):
        self.setStyleSheet(self._STYLE_ACTIVE if active else self._STYLE_IDLE)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_active(True)
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._set_active(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e: QDropEvent):
        self._set_active(False)
        mime = e.mimeData()
        paths = []
        if mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        # Fallback for some Windows shells / PyInstaller
        if not paths and mime.hasText():
            for line in mime.text().splitlines():
                line = line.strip().strip('"').strip("'")
                if line:
                    from pathlib import Path as _P
                    if _P(line).exists():
                        paths.append(line)
        if paths:
            e.acceptProposedAction()
            self._cb(paths)
        else:
            e.ignore()


# ═══════════════════════════════════════════════════════════════════════════════
#  DB History Dialog  — date-wise with search
# ═══════════════════════════════════════════════════════════════════════════════
class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📅  Database History — Date-wise Search")
        self.resize(1240, 740)
        self._sessions: list[dict] = []
        self._records:  list[dict] = []
        self._build_ui()
        self._refresh_dates()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # ── Search bar ────────────────────────────────────────────────────────
        search_box = QGroupBox("🔍  Search / Filter")
        search_box.setStyleSheet(
            "QGroupBox { font-weight:bold; border:1px solid #E0E0E0; "
            "border-radius:6px; margin-top:6px; padding:4px; } "
            "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
        )
        sh = QVBoxLayout(search_box)
        sh.setSpacing(8)

        # Radio: by date / all
        self.rb_date = QRadioButton("By Date")
        self.rb_all  = QRadioButton("All Records")
        self.rb_date.setChecked(True)
        bg = QButtonGroup(self); bg.addButton(self.rb_date); bg.addButton(self.rb_all)
        self.rb_date.toggled.connect(self._on_mode_toggle)

        # Date picker
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd-MMM-yyyy")
        self.date_edit.setFixedWidth(160)

        # Available dates combo
        self.date_combo = QComboBox()
        self.date_combo.setMinimumWidth(190)
        self.date_combo.setToolTip("Pick from dates that have records")

        self.btn_search = QPushButton("🔍  Search")
        self.btn_search.setObjectName("BtnPrimary")
        self.btn_search.setFixedHeight(38)
        self.btn_search.clicked.connect(self._do_search)

        self.btn_all = QPushButton("Show All")
        self.btn_all.setObjectName("BtnSecondary")
        self.btn_all.setFixedHeight(38)
        self.btn_all.clicked.connect(self._show_all)

        # Two rows so the large font still fits on smaller screens
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self.rb_date)
        row1.addWidget(QLabel("Pick date:"))
        row1.addWidget(self.date_edit)
        row1.addWidget(QLabel("or from list:"))
        row1.addWidget(self.date_combo)
        row1.addStretch()

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(self.rb_all)
        row2.addWidget(self.btn_search)
        row2.addWidget(self.btn_all)
        row2.addStretch()

        sh.addLayout(row1)
        sh.addLayout(row2)

        # Session selector
        sh2 = QHBoxLayout()
        sh2.addWidget(QLabel("Session:"))
        self.session_combo = QComboBox()
        self.session_combo.setMinimumWidth(420)
        self.session_combo.addItem("— All sessions for selected date —", None)
        self.session_combo.currentIndexChanged.connect(self._load_records)
        sh2.addWidget(self.session_combo, stretch=1)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        sh2.addWidget(self.lbl_summary)

        lay.addWidget(search_box)
        lay.addLayout(sh2)

        # ── Records table ─────────────────────────────────────────────────────
        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.verticalHeader().setDefaultSectionSize(30)
        self.tbl.setStyleSheet("""
            QTableWidget { border:1px solid #E0E0E0; border-radius:6px; }
            QHeaderView::section { background:#1F3864; color:white;
                font-weight:bold; padding:4px; border:none; }
        """)
        self.tbl.setToolTip("Double-click a row to preview the image")
        self.tbl.cellDoubleClicked.connect(self._preview_row)
        lay.addWidget(self.tbl)

        # ── Actions row ───────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.btn_refresh = QPushButton("🔄  Refresh Locations")
        self.btn_refresh.setObjectName("BtnSecondary")
        self.btn_refresh.setFixedHeight(38)
        self.btn_refresh.setToolTip(
            "Re-check every listed file on disk: found → OK, missing → Moved"
        )
        self.btn_refresh.clicked.connect(self._refresh_locations)
        actions.addWidget(self.btn_refresh)

        self.btn_export = QPushButton("📤  Export")
        self.btn_export.setObjectName("BtnSecondary")
        self.btn_export.setFixedHeight(38)
        export_menu = QMenu(self.btn_export)
        export_menu.addAction("Export to Excel (.xlsx)", self._export_excel)
        export_menu.addAction("Export to CSV (.csv)", self._export_csv)
        self.btn_export.setMenu(export_menu)
        actions.addWidget(self.btn_export)
        actions.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        actions.addWidget(btns)
        lay.addLayout(actions)

    def _on_mode_toggle(self, checked):
        self.date_edit.setEnabled(checked)
        self.date_combo.setEnabled(checked)
        self.btn_search.setEnabled(checked)

    def _refresh_dates(self):
        dates = fetch_available_dates()
        self.date_combo.clear()
        for d in dates:
            # Format for display: YYYY-MM-DD → dd-MMM-YYYY
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                label = dt.strftime("%d %b %Y")
            except Exception:
                label = d
            self.date_combo.addItem(label, d)
        if dates:
            # Pre-select the most recent date in date_edit too
            try:
                latest = QDate.fromString(dates[0], "yyyy-MM-dd")
                self.date_edit.setDate(latest)
            except Exception:
                pass
        self._do_search()

    def _do_search(self):
        """Search by the chosen date."""
        # Prefer the combo selection if it matches, else use date_edit
        idx = self.date_combo.currentIndex()
        if idx >= 0 and self.date_combo.currentData():
            date_str = self.date_combo.currentData()
        else:
            date_str = self.date_edit.date().toString("yyyy-MM-dd")

        self._load_sessions_for_date(date_str)

    def _show_all(self):
        self._load_sessions_for_date(None)

    def _load_sessions_for_date(self, date_str: str | None):
        self._sessions = fetch_sessions_by_date(date_str)
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        self.session_combo.addItem(
            f"— All sessions{' on ' + date_str if date_str else ''} —", None
        )
        for s in self._sessions:
            try:
                dt = datetime.strptime(s["analysis_date"], "%Y-%m-%d")
                date_label = dt.strftime("%d %b %Y")
            except Exception:
                date_label = s["analysis_date"]
            self.session_combo.addItem(
                f"#{s['id']}  {date_label}  {s['created_at'][11:19]}  "
                f"({s['total_files']} files, {s['ok_files']} OK)",
                s["id"]
            )
        self.session_combo.blockSignals(False)
        self.lbl_summary.setText(f"{len(self._sessions)} session(s) found")
        self._load_records(0)   # load all records for this date

    def _load_records(self, idx):
        session_id = self.session_combo.currentData()

        if session_id is None:
            # Show all records for the searched date
            date_str_data = self.date_combo.currentData()
            if date_str_data and self.rb_date.isChecked():
                records = fetch_records_by_date(date_str_data)
            else:
                # All — concatenate from all sessions
                records = []
                for s in self._sessions:
                    records += fetch_records_for_session(s["id"])
        else:
            records = fetch_records_for_session(session_id)

        self._records = records

        cols = [label for label, _ in HISTORY_COLUMNS]
        self.tbl.setColumnCount(len(cols))
        self.tbl.setHorizontalHeaderLabels(cols)
        self.tbl.setRowCount(len(records))

        for row, rec in enumerate(records):
            vals = format_history_record(rec)
            status = vals[-2]
            if status == "Moved ✔":
                bg = QColor("#F3E5F5")
            elif status != "OK":
                bg = QColor("#FFEBEE")
            else:
                bg = QColor("#E8F5E9") if row % 2 == 0 else QColor("#F5F5F5")

            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setBackground(bg)
                self.tbl.setItem(row, col, item)

        self.tbl.resizeColumnsToContents()
        self.lbl_summary.setText(
            f"{len(self._sessions)} session(s)  |  {len(records)} record(s)"
        )

    # ── Row actions ───────────────────────────────────────────────────────────
    def _preview_row(self, row: int, _col: int = 0):
        if not (0 <= row < len(self._records)):
            return
        rec = self._records[row]
        path = rec.get("moved_to") or rec.get("file_path")
        if not path:
            QMessageBox.information(
                self, "No Preview",
                "This record has no stored file path (created by an older version).",
            )
            return
        ImagePreviewDialog(path, rec, self).exec()

    def _refresh_locations(self):
        if not self._records:
            QMessageBox.information(self, "Refresh", "No records to check.")
            return
        try:
            changed = refresh_record_locations(self._records)
        except Exception as exc:
            QMessageBox.critical(self, "Refresh Failed", str(exc))
            return

        self._load_records(self.session_combo.currentIndex())
        self.lbl_summary.setText(
            f"{len(self._sessions)} session(s)  |  {len(self._records)} record(s)"
            f"  |  {changed} status change(s)"
        )

    # ── Export ────────────────────────────────────────────────────────────────
    def _export_excel(self):
        self._export("xlsx")

    def _export_csv(self):
        self._export("csv")

    def _export(self, kind: str):
        if not self._records:
            QMessageBox.warning(self, "Nothing to Export",
                                "There are no records in the current view.")
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        docs = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        ) or str(Path.home())
        default = str(Path(docs) / f"Image_History_{stamp}.{kind}")
        filt = ("Excel Workbook (*.xlsx)" if kind == "xlsx"
                else "CSV File (*.csv)")

        path, _ = QFileDialog.getSaveFileName(
            self, "Export History", default, filt
        )
        if not path:
            return

        try:
            if kind == "xlsx":
                export_history_excel(self._records, path)
            else:
                export_history_csv(self._records, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        QMessageBox.information(
            self, "Exported",
            f"Exported {len(self._records)} record(s):\n{path}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════
# NOTE: Do NOT override QWidget.nativeEvent here. PyQt6 6.12 / Python 3.14
# crashes with an access violation as soon as such a window is shown.
# Qt's built-in drag-and-drop (setAcceptDrops + drag/drop events) is used instead.
class MainWindow(QMainWindow):

    def __init__(self, user: dict | None = None):
        super().__init__()
        self.current_user = user or {
            "id": None, "username": "guest",
            "display_name": "Guest", "is_admin": True,
        }
        self.setWindowTitle("Image Measurement & Report Tool  v3")
        self.setMinimumSize(1120, 700)
        self._file_paths: list[str] = []
        self._results:    list[ImageInfo] = []
        self._worker:     AnalysisWorker | None = None
        self._session_id: int | None = None
        self._sorting_was_enabled = True
        self._files_moved = False
        self._token_window: TokenWindow | None = None
        init_db()
        self.setAcceptDrops(True)   # allow drops anywhere in the window
        self._build_ui()
        self._apply_styles()

        # Daily automatic backup (checked at startup and once every hour while
        # the app stays open).  A backup is only written once per calendar day.
        self._backup_timer = QTimer(self)
        self._backup_timer.setInterval(60 * 60 * 1000)
        self._backup_timer.timeout.connect(self._run_daily_backup)
        self._backup_timer.start()
        QTimer.singleShot(2500, self._run_daily_backup)

    def _run_daily_backup(self):
        try:
            path = maybe_run_daily_backup()
        except Exception as exc:
            self._status(f"Automatic backup failed: {exc}")
            return
        if path:
            self._status(f"✔ Daily backup saved: {path}")

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        c = QWidget(); self.setCentralWidget(c)
        root = QVBoxLayout(c)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)
        root.addWidget(self._make_title())
        self.drop_zone = DropZone(self._add_files)
        root.addWidget(self.drop_zone)
        root.addLayout(self._make_toolbar())
        self.table = self._make_table()
        self.table.cellDoubleClicked.connect(self._preview_row)
        root.addWidget(self.table, stretch=1)
        root.addLayout(self._make_dest_row())
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(30)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)
        root.addLayout(self._make_actions())
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_copyright = QLabel(__copyright__)
        self.lbl_copyright.setStyleSheet(
            f"color:{C_SUBTEXT}; font-size:14pt; padding-right:6px;"
        )
        self.status_bar.addPermanentWidget(self.lbl_copyright)
        if _running_as_admin():
            self._status("Running as administrator — Windows blocks drag & drop from "
                         "Explorer. Use Browse, or restart the app normally.")
        else:
            self._status("Ready — drop files anywhere in this window, or click Browse.  "
                         "Double-click a row to preview.")

    def _make_title(self):
        f = QFrame(); f.setObjectName("TitleBar")
        h = QHBoxLayout(f); h.setContentsMargins(8, 4, 8, 4)
        ico = QLabel("🖼️"); ico.setFont(QFont("Segoe UI Emoji", 20))
        h.addWidget(ico)
        t = QLabel("Image Measurement & Report Tool")
        t.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{C_PRIMARY};")
        h.addWidget(t); h.addStretch()
        self.lbl_user = QLabel(f"👤  {self.current_user['display_name']}")
        self.lbl_user.setStyleSheet(
            f"color:{C_TEXT}; font-size:14pt; font-weight:bold;"
        )
        h.addWidget(self.lbl_user)
        h.addSpacing(14)
        today = datetime.now().strftime("%d %b %Y")
        sub = QLabel(f"📅 {today}  |  Analyse · Measure · Report")
        sub.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        h.addWidget(sub)
        return f

    def _make_toolbar(self):
        h = QHBoxLayout(); h.setSpacing(8)
        self.btn_browse = QPushButton("📁  Browse")
        self.btn_browse.setObjectName("BtnPrimary")
        self.btn_browse.setToolTip("Browse for image files")
        self.btn_browse.clicked.connect(self._browse)
        self.btn_clear = QPushButton("🗑  Clear")
        self.btn_clear.setObjectName("BtnSecondary")
        self.btn_clear.clicked.connect(self._clear)
        self.btn_history = QPushButton("📅  History")
        self.btn_history.setObjectName("BtnSecondary")
        self.btn_history.setToolTip("Browse the database history")
        self.btn_history.clicked.connect(self._show_history)

        self.btn_backup = QPushButton("💾  Backup")
        self.btn_backup.setObjectName("BtnSecondary")
        self.btn_backup.setToolTip(
            "Choose a backup folder and back up the database automatically every day"
        )
        self.btn_backup.clicked.connect(self._show_backup)

        self.btn_users = None
        if self.current_user.get("is_admin"):
            self.btn_users = QPushButton("👥  Users")
            self.btn_users.setObjectName("BtnSecondary")
            self.btn_users.setToolTip("Add users, reset passwords, delete accounts")
            self.btn_users.clicked.connect(self._manage_users)

        self.btn_about = QPushButton("ℹ️")
        self.btn_about.setObjectName("BtnSecondary")
        self.btn_about.setToolTip("About this application")
        self.btn_about.setFixedSize(58, 40)
        self.btn_about.clicked.connect(self._show_about)

        self.lbl_count = QLabel("0 files")
        self.lbl_count.setToolTip("Analysed / loaded files")
        self.lbl_count.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        h.addWidget(self.btn_browse)
        h.addWidget(self.btn_clear)
        h.addWidget(self.btn_history)
        h.addWidget(self.btn_backup)
        if self.btn_users:
            h.addWidget(self.btn_users)
        h.addStretch()
        h.addWidget(self.lbl_count)
        h.addWidget(self.btn_about)
        return h

    def _make_table(self):
        tbl = QTableWidget(0, len(TABLE_COLUMNS))
        tbl.setHorizontalHeaderLabels(TABLE_COLUMNS)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setDefaultSectionSize(30)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.setSortingEnabled(True)
        tbl.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        tbl.setObjectName("DataTable")
        for i, w in enumerate([280, 120, 150, 200, 110, 110, 110, 110, 110]):
            tbl.setColumnWidth(i, w)
        return tbl

    def _make_dest_row(self):
        h = QHBoxLayout(); h.setSpacing(8)

        lbl_item = QLabel("🏷️  Item name:")
        lbl_item.setStyleSheet("font-size:14pt; font-weight:bold;")
        h.addWidget(lbl_item)
        self.item_edit = QLineEdit()
        self.item_edit.setPlaceholderText("e.g. Sharma-House")
        self.item_edit.setToolTip(
            "This Item name is added in front of the moved file names "
            "(e.g. Sharma-House_IMG_001.jpg)."
        )
        self.item_edit.setFixedHeight(38)
        self.item_edit.setMinimumWidth(210)
        self.item_edit.setMaximumWidth(320)
        h.addWidget(self.item_edit)

        h.addSpacing(14)
        lbl = QLabel("📂  Destination folder:")
        lbl.setStyleSheet("font-size:14pt; font-weight:bold;")
        h.addWidget(lbl)
        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Select destination folder for moved images + report …")
        self.dest_edit.setFixedHeight(38)
        h.addWidget(self.dest_edit, stretch=1)
        btn = QPushButton("Browse…"); btn.setObjectName("BtnSecondary")
        btn.setFixedHeight(38); btn.clicked.connect(self._browse_dest)
        h.addWidget(btn)
        return h

    def _make_actions(self):
        box = QVBoxLayout(); box.setSpacing(6)

        row1 = QHBoxLayout(); row1.setSpacing(10); row1.addStretch()
        self.btn_analyse = QPushButton("🔍  Analyse")
        self.btn_analyse.setObjectName("BtnAnalyse"); self.btn_analyse.setFixedHeight(48)
        self.btn_analyse.setToolTip("Analyse the loaded image files")
        self.btn_analyse.setEnabled(False); self.btn_analyse.clicked.connect(self._start_analysis)

        self.btn_report = QPushButton("📊  Save Report")
        self.btn_report.setObjectName("BtnReport"); self.btn_report.setFixedHeight(48)
        self.btn_report.setToolTip("Save the results as an Excel (.xlsx) report")
        self.btn_report.setEnabled(False); self.btn_report.clicked.connect(self._save_report)

        self.btn_move = QPushButton("📦  Move Files")
        self.btn_move.setObjectName("BtnMove"); self.btn_move.setFixedHeight(48)
        self.btn_move.setToolTip("Move the analysed images to the destination folder")
        self.btn_move.setEnabled(False); self.btn_move.clicked.connect(self._move_files)

        for btn in (self.btn_analyse, self.btn_report, self.btn_move):
            row1.addWidget(btn)

        row2 = QHBoxLayout(); row2.setSpacing(10); row2.addStretch()
        self.btn_token = QPushButton("🏷️  Token Window")
        self.btn_token.setObjectName("BtnToken"); self.btn_token.setFixedHeight(48)
        self.btn_token.setToolTip(
            "Open the separate Token Generation window "
            "(moved files are sent there automatically)"
        )
        self.btn_token.setEnabled(True)
        self.btn_token.clicked.connect(self._open_token_window)

        self.btn_cancel = QPushButton("✖  Cancel")
        self.btn_cancel.setObjectName("BtnCancel"); self.btn_cancel.setFixedHeight(48)
        self.btn_cancel.setEnabled(False); self.btn_cancel.clicked.connect(self._cancel)

        row2.addWidget(self.btn_token)
        row2.addWidget(self.btn_cancel)

        box.addLayout(row1)
        box.addLayout(row2)
        return box

    # ── Styles ────────────────────────────────────────────────────────────────
    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background:{C_BG}; font-family:'Segoe UI';
                font-size:14pt; color:{C_TEXT}; }}
            #TitleBar {{ background:{C_CARD}; border-bottom:1px solid {C_BORDER};
                border-radius:6px; }}
            #BtnPrimary {{ background:{C_PRIMARY}; color:white; border:none;
                border-radius:6px; padding:6px 16px; font-size:14pt; font-weight:bold; }}
            #BtnPrimary:hover {{ background:#1976D2; }}
            #BtnPrimary:disabled {{ background:#90CAF9; }}
            #BtnSecondary {{ background:{C_CARD}; color:{C_TEXT}; border:1px solid {C_BORDER};
                border-radius:6px; padding:5px 14px; font-size:14pt; }}
            #BtnSecondary:hover {{ background:#EEEEEE; }}
            #BtnAnalyse {{ background:#0D47A1; color:white; border:none;
                border-radius:8px; padding:8px 20px; font-size:14pt; font-weight:bold; }}
            #BtnAnalyse:hover {{ background:#1565C0; }}
            #BtnAnalyse:disabled {{ background:#90CAF9; color:#E3F2FD; }}
            #BtnReport {{ background:{C_SUCCESS}; color:white; border:none;
                border-radius:8px; padding:8px 20px; font-size:14pt; font-weight:bold; }}
            #BtnReport:hover {{ background:#388E3C; }}
            #BtnReport:disabled {{ background:#A5D6A7; color:#E8F5E9; }}
            #BtnMove {{ background:{C_MOVE}; color:white; border:none;
                border-radius:8px; padding:8px 20px; font-size:14pt; font-weight:bold; }}
            #BtnMove:hover {{ background:#7B1FA2; }}
            #BtnMove:disabled {{ background:#CE93D8; color:#F3E5F5; }}
            #BtnCancel {{ background:{C_ERROR}; color:white; border:none;
                border-radius:8px; padding:8px 16px; font-size:14pt; font-weight:bold; }}
            #BtnCancel:hover {{ background:#D32F2F; }}
            #BtnCancel:disabled {{ background:#EF9A9A; color:#FFEBEE; }}
            #BtnToken {{ background:#00695C; color:white; border:none;
                border-radius:8px; padding:8px 20px; font-size:14pt; font-weight:bold; }}
            #BtnToken:hover {{ background:#00796B; }}
            #BtnToken:disabled {{ background:#80CBC4; color:#E0F2F1; }}
            #DataTable {{ background:{C_CARD}; alternate-background-color:#FAFAFA;
                border:1px solid {C_BORDER}; border-radius:6px; gridline-color:{C_BORDER}; }}
            #DataTable QHeaderView::section {{ background:{C_PRIMARY}; color:white;
                font-weight:bold; padding:4px; border:none;
                border-right:1px solid #1976D2; }}
            QProgressBar {{ border:1px solid {C_BORDER}; border-radius:4px;
                background:#ECEFF1; text-align:center; font-size:14pt; }}
            QProgressBar::chunk {{ background:{C_PRIMARY}; border-radius:4px; }}
            QLineEdit {{ border:1px solid {C_BORDER}; border-radius:5px;
                padding:4px 8px; background:{C_CARD}; color:{C_TEXT}; }}
            QLineEdit:focus {{ border-color:{C_PRIMARY}; }}
            QStatusBar {{ background:{C_CARD}; border-top:1px solid {C_BORDER};
                font-size:14pt; }}
        """)

    # ── File management ───────────────────────────────────────────────────────
    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Image Files", "",
            "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.gif *.webp "
            "*.ico *.psd *.eps *.pdf);;All Files (*)"
        )
        if paths: self._add_files(paths)

    # ── Drag & drop (accepted on the whole window) ────────────────────────────
    @staticmethod
    def _dropped_paths(event) -> list[str]:
        """
        Extract local file paths from a drop event.
        Handles both regular drag-drop and PyInstaller EXE drag-drop where
        Windows may deliver paths via text/plain or CF_HDROP formats.
        """
        try:
            mime = event.mimeData()
            paths = []

            # Primary: standard URL list (works in most cases)
            if mime.hasUrls():
                for u in mime.urls():
                    if u.isLocalFile():
                        paths.append(u.toLocalFile())

            # Fallback: plain text (some Windows shells send paths as text)
            if not paths and mime.hasText():
                for line in mime.text().splitlines():
                    line = line.strip().strip('"').strip("'")
                    if line and Path(line).exists():
                        paths.append(line)

            return paths
        except Exception:
            return []

    def dragEnterEvent(self, e: QDragEnterEvent):
        if self._dropped_paths(e):
            e.acceptProposedAction()
            self.drop_zone._set_active(True)
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self._dropped_paths(e):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.drop_zone._set_active(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e: QDropEvent):
        self.drop_zone._set_active(False)
        paths = self._dropped_paths(e)
        if paths:
            e.acceptProposedAction()
            self._add_files(paths)
        else:
            e.ignore()

    def _add_files(self, paths: list[str]):
        added = skipped = 0
        # Sorting must be off while rows are populated cell-by-cell,
        # otherwise Qt moves rows mid-write and cells get mixed up.
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            for p in paths:
                p = os.path.normpath(p)
                src = Path(p)

                # Dropped folder -> add the supported images directly inside it
                if src.is_dir():
                    found = [
                        f for f in sorted(src.iterdir())
                        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
                    ]
                    if not found:
                        skipped += 1
                    for f in found:
                        sp = str(f)
                        if sp not in self._file_paths:
                            self._file_paths.append(sp)
                            self._add_pending_row(sp)
                            added += 1
                    continue

                if src.suffix.lower() not in SUPPORTED_EXTS:
                    skipped += 1
                    continue
                if p not in self._file_paths:
                    self._file_paths.append(p)
                    self._add_pending_row(p)
                    added += 1
        finally:
            self.table.setSortingEnabled(sorting)

        self._update_count()
        self.btn_analyse.setEnabled(bool(self._file_paths))
        if added:
            self._files_moved = False
        msg = f"Added {added} file(s)."
        if skipped:
            msg += f"  {skipped} item(s) skipped (no supported images)."
        self._status(msg)

    def _add_pending_row(self, path: str):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(Path(path).name))
        for col in range(1, len(TABLE_COLUMNS) - 1):
            self.table.setItem(row, col, QTableWidgetItem("—"))
        s = QTableWidgetItem("Pending")
        s.setForeground(QColor(C_SUBTEXT))
        self.table.setItem(row, len(TABLE_COLUMNS) - 1, s)

    def _clear(self):
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Running", "Cancel analysis first."); return
        self._file_paths.clear(); self._results.clear()
        self.table.setRowCount(0)
        self.btn_analyse.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.btn_move.setEnabled(False)
        self._files_moved = False
        self._session_id = None
        self._update_count()
        self._status("List cleared — ready for the next batch of files.")

    def _browse_dest(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder: self.dest_edit.setText(folder)

    def _show_history(self):
        dlg = HistoryDialog(self); dlg.exec()

    def _show_backup(self):
        dlg = BackupDialog(self)
        dlg.exec()
        self._run_daily_backup()

    def _show_about(self):
        QMessageBox.about(
            self,
            "About — Image Measurement & Report Tool",
            f"<b>Image Measurement &amp; Report Tool</b><br>"
            f"Version {__version__}<br><br>"
            f"{__copyright__}<br><br>"
            "Built with Python, PyQt6, Pillow and openpyxl.",
        )

    def _manage_users(self):
        dlg = UserManagementDialog(self.current_user, self)
        dlg.exec()

    def _open_token_window(self):
        """Show the separate Token Generation window (keeps its file list)."""
        if self._token_window is None:
            self._token_window = TokenWindow(self.current_user, self)
        self._token_window.showNormal()
        self._token_window.raise_()
        self._token_window.activateWindow()

    # ── Analysis ──────────────────────────────────────────────────────────────
    def _start_analysis(self):
        if not self._file_paths: return
        self._results.clear(); self._session_id = None
        self._files_moved = False
        self._sorting_was_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.progress_bar.setMaximum(len(self._file_paths))
        self.progress_bar.setValue(0); self.progress_bar.show()
        self.btn_analyse.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.btn_move.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._status("Analysing images…")
        self._worker = AnalysisWorker(self._file_paths)
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_result)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel(self):
        if self._worker: self._worker.cancel()
        self.btn_cancel.setEnabled(False); self._status("Cancelling…")

    # ── Worker signals ────────────────────────────────────────────────────────
    def _on_progress(self, cur, total, path):
        self.progress_bar.setValue(cur)
        self.progress_bar.setFormat(f"  {cur}/{total}  —  {Path(path).name}")
        self._status(f"Processing {cur}/{total}: {Path(path).name}")

    def _on_result(self, info: ImageInfo):
        # Sorting is disabled for the whole analysis run, so row indexes are stable
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0) and self.table.item(row, 0).text() == info.file_name:
                self._fill_row(row, info); break

    def _preview_row(self, row: int, _col: int = 0):
        """Open the preview dialog for the double-clicked row."""
        item = self.table.item(row, 0)
        if not item:
            return
        name = item.text()

        info = next((r for r in self._results if r.file_name == name), None)
        if info is not None:
            path, meta = info.file_path, asdict(info)
        else:
            path = next((p for p in self._file_paths if Path(p).name == name), "")
            meta = {}

        if not path:
            return
        ImagePreviewDialog(path, meta, self).exec()

    def _fill_row(self, row: int, info: ImageInfo):
        ok = info.status == "OK"
        bg = "#E8F5E9" if ok else "#FFEBEE"
        w_ft = round(info.width_inch  / 12, 4) if info.width_inch  else 0.0
        h_ft = round(info.height_inch / 12, 4) if info.height_inch else 0.0
        vals = [
            info.file_name, info.format,
            f"{info.dpi_x} × {info.dpi_y}",
            info.color_mode_label,
            f"{info.width_inch}″", f"{info.height_inch}″",
            f"{w_ft} ft", f"{h_ft} ft",
            info.status if ok else f"ERR: {info.error[:30]}",
        ]
        for col, val in enumerate(vals):
            item = QTableWidgetItem(str(val))
            item.setBackground(QColor(bg))
            if col == len(TABLE_COLUMNS) - 1:
                item.setForeground(QColor(C_SUCCESS if ok else C_ERROR))
            self.table.setItem(row, col, item)

    def _on_finished(self, results: list[ImageInfo]):
        self._results = results
        self.progress_bar.hide()
        self.btn_cancel.setEnabled(False)
        self.btn_analyse.setEnabled(True)
        if results:
            self.btn_report.setEnabled(True)
            self.btn_move.setEnabled(True)
            self._files_moved = False
            try:
                self._session_id = save_session(results)
                ok = sum(1 for r in results if r.status == "OK")
                self._status(
                    f"✔ Done — {ok}/{len(results)} OK.  "
                    f"Saved to DB (session #{self._session_id}  "
                    f"{datetime.now().strftime('%d %b %Y')}).  "
                    "Set the Item name and destination, then click Move Files."
                )
            except Exception as exc:
                self._status(f"✔ Analysis done — DB save failed: {exc}")
        self.table.setSortingEnabled(self._sorting_was_enabled)
        self._update_count()

    def _on_error(self, msg: str):
        self.progress_bar.hide()
        self.table.setSortingEnabled(self._sorting_was_enabled)
        self.btn_analyse.setEnabled(True); self.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "Error", f"Analysis failed:\n\n{msg}")
        self._status("Error during analysis.")

    # ── Report ────────────────────────────────────────────────────────────────
    def _save_report(self):
        if not self._results:
            QMessageBox.warning(self, "No Data", "Run analysis first."); return
        dest_folder = self.dest_edit.text().strip() or None
        default_name = f"Image_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        default_dir  = dest_folder or (str(Path(self._file_paths[0]).parent)
                                       if self._file_paths else "")
        report_path, _ = QFileDialog.getSaveFileName(
            self, "Save Report As",
            os.path.join(default_dir, default_name),
            "Excel Workbook (*.xlsx)"
        )
        if not report_path: return
        try:
            generate_excel_report(self._results, report_path,
                                  dest_folder=None, move_files=False)
            QMessageBox.information(self, "Saved", f"Report saved:\n{report_path}")
            self._status(f"Report saved → {report_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not save:\n{exc}")

    # ── Move Files ────────────────────────────────────────────────────────────
    def _move_files(self):
        dest_folder = self.dest_edit.text().strip()
        if not dest_folder:
            QMessageBox.warning(self, "No Destination",
                "Please set a destination folder before moving files."); return

        ok_results = [r for r in self._results if r.status == "OK"]
        if not ok_results:
            QMessageBox.warning(self, "Nothing to Move",
                "No successfully analysed files."); return

        item = self.item_edit.text().strip()
        prefix = _clean_item_name(item)
        if not prefix:
            reply = QMessageBox.question(
                self, "No Item Name",
                "No Item name was entered.\n\n"
                "The Item name is added in front of each moved image's "
                "original name. Move the files without adding it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.item_edit.setFocus()
                return

        rename_note = (
            f"Every file keeps its original name with the Item added in front:\n"
            f"    {prefix}_OriginalName.ext\n"
            f"    {prefix}_OriginalName_1.ext (if a name already exists)\n\n"
            if prefix else
            "No Item name will be used — original file names are kept.\n\n"
        )
        reply = QMessageBox.question(
            self, "Confirm Move",
            f"Move {len(ok_results)} image file(s) to:\n{dest_folder}\n\n"
            f"{rename_note}"
            "⚠ Original files will be deleted after moving.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes: return

        dest = Path(dest_folder)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Destination Error",
                                 f"Cannot create the destination folder:\n{exc}")
            return

        moved = already_moved = failed = 0
        moved_entries: list[dict] = []

        def _row_for(file_name: str) -> int:
            for row in range(self.table.rowCount()):
                cell = self.table.item(row, 0)
                if cell and cell.text() == file_name:
                    return row
            return -1

        def _set_row(row: int, final_name: str, status_text: str,
                     status_color: str, bg: str):
            if row < 0:
                return
            name_item = QTableWidgetItem(final_name)
            self.table.setItem(row, 0, name_item)
            s = QTableWidgetItem(status_text)
            s.setForeground(QColor(status_color))
            s.setBackground(QColor(bg))
            self.table.setItem(row, len(TABLE_COLUMNS) - 1, s)

        for info in ok_results:
            src = Path(info.file_path)
            original_name = info.file_name
            target_name = _apply_item_prefix(original_name, prefix)
            row = _row_for(original_name)
            status_color = C_MOVE

            try:
                in_dest = src.exists() and src.resolve().parent == dest.resolve()
            except OSError:
                in_dest = False

            if not src.exists():
                # File was moved in an earlier run — just re-use it.
                already_moved += 1
                final_name = target_name
                final_path = str(dest / target_name)
                for candidate in (dest / target_name, dest / original_name):
                    if candidate.exists():
                        final_name = candidate.name
                        final_path = str(candidate)
                        break
                status_text = "Moved ✔"
            else:
                try:
                    if in_dest and src.name == target_name:
                        final_name, final_path = src.name, str(src)
                        already_moved += 1
                    else:
                        dst = _unique_destination(dest, target_name)
                        if in_dest:
                            src.rename(dst)      # rename in place
                        else:
                            shutil.move(str(src), str(dst))
                        final_name, final_path = dst.name, str(dst)
                        moved += 1
                    status_text = "Moved ✔"
                except Exception:
                    failed += 1
                    status_text = "Move Failed"
                    status_color = C_ERROR
                    final_name, final_path = original_name, info.file_path
                    _set_row(row, final_name, status_text, status_color, "#FFEBEE")
                    continue

            # Update the record in memory and in the database
            new_for_db = final_name if final_name != original_name else None
            orig_path = info.file_path     # captured before it is replaced
            info.file_name = final_name
            info.file_path = final_path
            if self._session_id:
                try:
                    update_moved_to(
                        self._session_id, original_name, final_path,
                        new_name=new_for_db, orig_path=orig_path,
                    )
                except Exception:
                    pass

            _set_row(row, final_name, status_text, status_color, "#F3E5F5")
            moved_entries.append({
                "file_name":   final_name,
                "color_mode":  info.color_mode_label or "—",
                "width_inch":  round(float(info.width_inch or 0), 3),
                "height_inch": round(float(info.height_inch or 0), 3),
                "moved_to":    final_path,
            })

        parts = []
        if moved:         parts.append(f"✔ {moved} file(s) moved")
        if already_moved: parts.append(f"✔ {already_moved} already moved")
        if failed:        parts.append(f"✖ {failed} failed")

        self._files_moved = failed == 0
        parts_msg = "\n".join(parts) + f"\n\nDestination:\n{dest_folder}"

        if self._files_moved:
            self.btn_move.setEnabled(False)
            self._status(
                f"Move done — {moved} moved, {already_moved} already moved.  "
                "Sending the renamed list to the Token window…"
            )
            QMessageBox.information(
                self, "Move Complete ✔",
                parts_msg + "\n\n"
                "🏷️ The renamed file list is being sent to the "
                "Token Generation window.\n"
                "The analysis list will now be cleared for the next batch.",
            )

            # Hand the renamed files to the separate Token window, then reset
            # this window so a new batch can be added immediately.
            self._open_token_window()
            if moved_entries:
                self._token_window.add_files(
                    moved_entries, item=prefix,
                    session_id=self._session_id,
                )
            self._clear()
            self._status(
                f"✔ {len(moved_entries)} renamed file(s) sent to Token Generation.  "
                "Analysis list cleared — add the next batch."
            )
        else:
            QMessageBox.warning(
                self, "Move Incomplete",
                parts_msg + "\n\nPlease retry Move Files.",
            )
            self._status(
                f"Move done — {moved} moved, {already_moved} already moved, "
                f"{failed} failed — Retry Move Files."
            )
            self.btn_move.setEnabled(True)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _update_count(self):
        total = len(self._file_paths); done = len(self._results)
        self.lbl_count.setText(
            f"{done}/{total}" if done
            else f"{total} file{'s' if total != 1 else ''} loaded"
        )

    def _status(self, msg: str):
        self.status_bar.showMessage(f"  {msg}")
