"""
Token windows.

`TokenWindow` is a separate (non-modal) window used to generate token slips.
After a successful move the main window pushes the renamed file list here, so
the analysis table can be cleared for the next batch.

`TokenHistoryDialog` lists every token that was saved to the database so old
slips can be re-opened, printed or exported again.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QMarginsF, QSizeF
from PyQt6.QtGui import QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QTextBrowser, QFileDialog, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QGroupBox, QDoubleSpinBox,
)

from image_analyzer.core.database import (
    create_token, fetch_customers, fetch_tokens,
)
from image_analyzer.core.token_report import build_token_html

C_PRIMARY = "#1565C0"
C_SUCCESS = "#2E7D32"
C_BG      = "#F5F5F5"
C_CARD    = "#FFFFFF"
C_BORDER  = "#E0E0E0"
C_TEXT    = "#212121"
C_SUBTEXT = "#757575"
C_ERROR   = "#C62828"

_TICKET_QSS = f"""
    QDialog {{ background:{C_BG}; color:{C_TEXT}; }}
    QLabel {{ color:{C_TEXT}; font-size:14pt; }}
    #Card {{ background:{C_CARD}; border:1px solid {C_BORDER};
             border-radius:10px; }}
    QLineEdit, QComboBox {{ border:1px solid {C_BORDER}; border-radius:6px;
                            padding:6px 10px; background:{C_CARD};
                            color:{C_TEXT}; font-size:14pt; }}
    QLineEdit:focus, QComboBox:focus {{ border-color:{C_PRIMARY}; }}
    QPushButton {{ font-size:14pt; }}
    QCheckBox {{ color:{C_TEXT}; font-size:14pt; }}
    #Primary {{ background:{C_PRIMARY}; color:white; border:none;
                border-radius:6px; padding:8px 22px; font-weight:bold; }}
    #Primary:hover {{ background:#1976D2; }}
    #Primary:disabled {{ background:#90CAF9; }}
    #Secondary {{ background:{C_CARD}; color:{C_TEXT};
                  border:1px solid {C_BORDER}; border-radius:6px;
                  padding:6px 14px; }}
    #Secondary:hover {{ background:#EEEEEE; }}
    #Error {{ color:{C_ERROR}; font-size:14pt; }}
    QTableWidget {{ background:{C_CARD}; alternate-background-color:#FAFAFA;
                    color:{C_TEXT}; border:1px solid {C_BORDER};
                    border-radius:6px; gridline-color:{C_BORDER};
                    font-size:14pt; }}
    QHeaderView::section {{ background:{C_PRIMARY}; color:white;
                            padding:6px; border:none; font-weight:bold; }}
"""


def _format_choices() -> list[tuple[str, str]]:
    return [
        ("A4 page", "a4"),
        ("A5 page", "a5"),
        ("80 mm Thermal", "thermal"),
        ("Custom size", "custom"),
    ]


def _format_size(file: dict) -> str:
    """'W × H' in inches and feet for the selection table."""
    try:
        w_in  = round(float(file.get("width_inch") or 0), 3)
        h_in  = round(float(file.get("height_inch") or 0), 3)
    except (TypeError, ValueError):
        return "—"
    if w_in <= 0 or h_in <= 0:
        return "—"
    return f'{w_in}" × {h_in}"  ({round(w_in / 12, 3)} ft × {round(h_in / 12, 3)} ft)'


def _entry_key(entry: dict) -> tuple:
    return (
        str(entry.get("file_name") or "").lower(),
        str(entry.get("moved_to") or entry.get("file_path") or "").lower(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Separate token-generation window
# ═══════════════════════════════════════════════════════════════════════════════
class TokenWindow(QDialog):
    """Non-modal window that receives moved files and generates token slips."""

    def __init__(self, user: dict | None = None, parent=None):
        super().__init__(parent)
        self.user = user or {
            "id": None, "username": "guest",
            "display_name": "Guest", "is_admin": True,
        }
        self._entries: list[dict] = []
        self._customers: list[dict] = []
        self._session_id: int | None = None
        self._current_item = ""
        self._building = False

        self.setWindowTitle("🏷️  Token Generation")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.resize(1060, 780)
        self.setMinimumSize(880, 620)
        self.setStyleSheet(_TICKET_QSS)
        self._build_ui()
        self._reload_customers()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("🏷️  Token Generation")
        title.setStyleSheet(f"color:{C_PRIMARY}; font-size:18pt; font-weight:bold;")
        head.addWidget(title)
        head.addStretch()
        self.btn_records = QPushButton("📜  Token Records")
        self.btn_records.setObjectName("Secondary")
        self.btn_records.setFixedHeight(40)
        self.btn_records.setToolTip("Browse every token saved in the database")
        self.btn_records.clicked.connect(self._open_records)
        head.addWidget(self.btn_records)
        root.addLayout(head)

        info = QLabel(
            "Moved files are listed here automatically. Tick the files that "
            "belong on the token, then click Generate Token. Unticked files "
            "stay in this window for the next token."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        root.addWidget(info)

        # ── Customer details (with the new Item field) ────────────────────────
        card = QFrame(); card.setObjectName("Card")
        form = QFormLayout(card)
        form.setContentsMargins(16, 12, 16, 12)
        form.setSpacing(8)

        self.cmb_customer = QComboBox()
        self.cmb_customer.setMinimumHeight(40)
        self.cmb_customer.currentIndexChanged.connect(self._pick_customer)
        form.addRow("Existing customer:", self.cmb_customer)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Customer name")
        self.ed_name.setFixedHeight(40)
        form.addRow("Customer name:", self.ed_name)

        self.ed_mobile = QLineEdit()
        self.ed_mobile.setPlaceholderText("Mobile number")
        self.ed_mobile.setFixedHeight(40)
        form.addRow("Mobile no:", self.ed_mobile)

        root.addWidget(card)

        # ── Files with checkboxes ─────────────────────────────────────────────
        files_box = QGroupBox("📄  Files in this token")
        files_box.setStyleSheet(
            "QGroupBox { font-weight:bold; border:1px solid #E0E0E0; "
            "border-radius:6px; margin-top:8px; padding:8px; } "
            "QGroupBox::title { subcontrol-origin:margin; left:10px; }"
        )
        fl = QVBoxLayout(files_box)
        fl.setSpacing(8)

        sel_row = QHBoxLayout()
        self.chk_all = QCheckBox("Select all")
        self.chk_all.setToolTip("Tick / untick every file in the list")
        self.chk_all.stateChanged.connect(self._toggle_all)
        sel_row.addWidget(self.chk_all)
        sel_row.addSpacing(12)
        self.lbl_count = QLabel("0 file(s)")
        self.lbl_count.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        sel_row.addWidget(self.lbl_count)
        sel_row.addStretch()

        self.btn_remove = QPushButton("➖  Remove selected")
        self.btn_remove.setObjectName("Secondary")
        self.btn_remove.setFixedHeight(38)
        self.btn_remove.clicked.connect(self._remove_selected)
        sel_row.addWidget(self.btn_remove)

        self.btn_clear_files = QPushButton("🗑  Clear files")
        self.btn_clear_files.setObjectName("Secondary")
        self.btn_clear_files.setFixedHeight(38)
        self.btn_clear_files.clicked.connect(self._clear_files)
        sel_row.addWidget(self.btn_clear_files)
        fl.addLayout(sel_row)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(
            ["✔", "#", "File Name", "Size", "Color Mode"]
        )
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.verticalHeader().setDefaultSectionSize(34)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setColumnWidth(0, 46)
        self.tbl.setColumnWidth(1, 46)
        self.tbl.itemChanged.connect(self._on_item_changed)
        fl.addWidget(self.tbl, stretch=1)
        root.addWidget(files_box, stretch=1)

        # ── Actions ───────────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_generate = QPushButton("🏷️  Generate Token")
        self.btn_generate.setObjectName("Primary")
        self.btn_generate.setFixedHeight(48)
        self.btn_generate.setToolTip(
            "Create a token slip for the ticked files"
        )
        self.btn_generate.clicked.connect(self._generate)
        actions.addWidget(self.btn_generate)
        actions.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setObjectName("Secondary")
        btn_close.setFixedHeight(44)
        btn_close.clicked.connect(self.close)
        actions.addWidget(btn_close)
        root.addLayout(actions)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

    # ── Customer helpers ──────────────────────────────────────────────────────
    def _reload_customers(self):
        self._customers = fetch_customers()
        self.cmb_customer.blockSignals(True)
        current = self.cmb_customer.currentData()
        self.cmb_customer.clear()
        self.cmb_customer.addItem("— New customer —", None)
        for c in self._customers:
            label = f"{c['name']}  —  {c['mobile']}"
            self.cmb_customer.addItem(label, c["id"])
        if current is not None:
            idx = self.cmb_customer.findData(current)
            if idx >= 0:
                self.cmb_customer.setCurrentIndex(idx)
        self.cmb_customer.blockSignals(False)

    def _pick_customer(self, _index: int):
        cid = self.cmb_customer.currentData()
        if cid is None:
            return
        customer = next((c for c in self._customers if c["id"] == cid), None)
        if customer:
            self.ed_name.setText(customer["name"])
            self.ed_mobile.setText(customer["mobile"])

    # ── Files ─────────────────────────────────────────────────────────────────
    def add_files(self, entries: list[dict], item: str = "",
                  session_id: int | None = None, show: bool = True):
        """
        Append moved files to this window.

        `entries` items must provide file_name, width_inch, height_inch and
        color_mode (moved_to is optional but used to avoid duplicates).
        """
        existing = {_entry_key(e) for e in self._entries}
        added = 0
        for entry in entries:
            data = {
                "file_name":   str(entry.get("file_name") or ""),
                "color_mode":  str(entry.get("color_mode") or "—"),
                "width_inch":  float(entry.get("width_inch") or 0),
                "height_inch": float(entry.get("height_inch") or 0),
                "moved_to":    str(entry.get("moved_to") or ""),
            }
            key = _entry_key(data)
            if key in existing:
                continue
            existing.add(key)
            self._entries.append(data)
            added += 1

        if session_id is not None:
            self._session_id = session_id

        # The latest moved batch determines the Item stored with the token.
        self._current_item = (item or "").strip()

        self._refresh_table()

        if added:
            self.lbl_status.setText(
                f"✔ {added} file(s) added — {len(self._entries)} file(s) waiting."
            )
        elif entries:
            self.lbl_status.setText(
                "Those files are already in the token list."
            )

        if show:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _refresh_table(self):
        self._building = True
        self.tbl.setRowCount(0)
        for row, entry in enumerate(self._entries):
            self.tbl.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            )
            chk.setCheckState(Qt.CheckState.Checked)
            chk.setData(Qt.ItemDataRole.UserRole, row)
            self.tbl.setItem(row, 0, chk)

            num = QTableWidgetItem(str(row + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl.setItem(row, 1, num)

            name = QTableWidgetItem(entry["file_name"])
            name.setToolTip(entry.get("moved_to") or entry["file_name"])
            self.tbl.setItem(row, 2, name)

            size = QTableWidgetItem(_format_size(entry))
            self.tbl.setItem(row, 3, size)

            mode = QTableWidgetItem(entry.get("color_mode") or "—")
            self.tbl.setItem(row, 4, mode)

        self._building = False
        self._sync_select_all()
        self._update_count()

    def _update_count(self):
        total = len(self._entries)
        selected = len(self._selected_indices())
        self.lbl_count.setText(f"{selected} of {total} file(s) selected")

    def _sync_select_all(self):
        total = len(self._entries)
        selected = len(self._selected_indices())
        self.chk_all.blockSignals(True)
        if total and selected == total:
            self.chk_all.setCheckState(Qt.CheckState.Checked)
        elif selected:
            self.chk_all.setCheckState(Qt.CheckState.PartiallyChecked)
        else:
            self.chk_all.setCheckState(Qt.CheckState.Unchecked)
        self.chk_all.blockSignals(False)

    def _selected_indices(self) -> list[int]:
        selected = []
        for row in range(self.tbl.rowCount()):
            item = self.tbl.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                idx = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(idx, int) and 0 <= idx < len(self._entries):
                    selected.append(idx)
        return sorted(set(selected))

    def _toggle_all(self, state: int):
        if self._building:
            return
        checked = state != Qt.CheckState.Unchecked.value
        self._building = True
        for row in range(self.tbl.rowCount()):
            item = self.tbl.item(row, 0)
            if item:
                item.setCheckState(
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )
        self._building = False
        self._update_count()

    def _on_item_changed(self, _item: QTableWidgetItem):
        if self._building:
            return
        self._sync_select_all()
        self._update_count()

    def _remove_selected(self):
        selected = set(self._selected_indices())
        if not selected:
            QMessageBox.information(
                self, "No Selection",
                "Tick the file(s) you want to remove from this window."
            )
            return
        self._entries = [
            e for i, e in enumerate(self._entries) if i not in selected
        ]
        self._refresh_table()
        self.lbl_status.setText(
            f"{len(selected)} file(s) removed — "
            f"{len(self._entries)} file(s) remaining."
        )

    def _clear_files(self):
        if not self._entries:
            return
        reply = QMessageBox.question(
            self, "Clear Files",
            f"Remove all {len(self._entries)} file(s) from the token window?\n\n"
            "The files are not deleted from disk — only from this list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._entries.clear()
        self._refresh_table()
        self.lbl_status.setText("Token file list cleared.")

    # ── Token generation ──────────────────────────────────────────────────────
    def _generate(self):
        selected = self._selected_indices()
        if not selected:
            QMessageBox.warning(
                self, "No Files Selected",
                "Tick at least one file before generating the token."
            )
            return

        name = self.ed_name.text().strip()
        mobile = self.ed_mobile.text().strip()
        digits = "".join(ch for ch in mobile if ch.isdigit())

        if len(name) < 2:
            QMessageBox.warning(self, "Customer Name",
                                "Please enter the customer's name.")
            self.ed_name.setFocus()
            return
        if len(digits) < 6:
            QMessageBox.warning(self, "Mobile Number",
                                "Please enter a valid mobile number.")
            self.ed_mobile.setFocus()
            return

        item = self._current_item

        files = [
            {
                "file_name":   self._entries[i]["file_name"],
                "color_mode":  self._entries[i].get("color_mode") or "—",
                "width_inch":  round(float(self._entries[i].get("width_inch") or 0), 3),
                "height_inch": round(float(self._entries[i].get("height_inch") or 0), 3),
            }
            for i in selected
        ]

        try:
            token = create_token(
                self._session_id, name, mobile,
                self.user.get("id"), self.user.get("display_name", ""),
                files, item=item,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Token Failed",
                                 f"Could not create the token slip:\n{exc}")
            return

        # The generated files leave this window; unticked files stay for later.
        self._entries = [
            e for i, e in enumerate(self._entries) if i not in set(selected)
        ]
        self._refresh_table()
        self._reload_customers()

        self.lbl_status.setText(
            f"✔ Token {token['token_no']} created for {name} "
            f"({len(files)} file(s)). "
            f"{len(self._entries)} file(s) still waiting."
        )
        TokenPreviewDialog(token, self).exec()

    # ── Token records ─────────────────────────────────────────────────────────
    def _open_records(self):
        TokenHistoryDialog(self).exec()

    def closeEvent(self, event):
        # Keep pending files: closing the window only hides it.  It can be
        # re-opened from the main window with its list intact.
        event.ignore()
        self.hide()


# ═══════════════════════════════════════════════════════════════════════════════
#  Saved-token browser (future use / reprint)
# ═══════════════════════════════════════════════════════════════════════════════
class TokenHistoryDialog(QDialog):
    """Lists every token saved in the database, newest first."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tokens: list[dict] = []
        self.setWindowTitle("📜  Token Records")
        self.setModal(True)
        self.resize(1100, 680)
        self.setMinimumSize(900, 560)
        self.setStyleSheet(_TICKET_QSS)
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("📜  Token Records")
        title.setStyleSheet(f"color:{C_PRIMARY}; font-size:18pt; font-weight:bold;")
        head.addWidget(title)
        head.addStretch()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        head.addWidget(self.lbl_info)
        root.addLayout(head)

        hint = QLabel(
            "Every generated token is kept here. Double-click a row (or use "
            "Open) to view, print or save it as PDF again."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        root.addWidget(hint)

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(
            ["Token No", "Date", "Customer", "Mobile", "Item", "Files"]
        )
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.verticalHeader().setDefaultSectionSize(34)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        hdr = self.tbl.horizontalHeader()
        for col in range(6):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl.cellDoubleClicked.connect(self._open_row)
        root.addWidget(self.tbl, stretch=1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_open = QPushButton("👁  Open / Print")
        self.btn_open.setObjectName("Primary")
        self.btn_open.setFixedHeight(42)
        self.btn_open.clicked.connect(lambda: self._open_row(self.tbl.currentRow()))
        actions.addWidget(self.btn_open)

        self.btn_refresh = QPushButton("🔄  Refresh")
        self.btn_refresh.setObjectName("Secondary")
        self.btn_refresh.setFixedHeight(42)
        self.btn_refresh.clicked.connect(self._load)
        actions.addWidget(self.btn_refresh)
        actions.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setObjectName("Secondary")
        btn_close.setFixedHeight(42)
        btn_close.clicked.connect(self.accept)
        actions.addWidget(btn_close)
        root.addLayout(actions)

    def _load(self):
        self._tokens = fetch_tokens(limit=1000)
        self.tbl.setRowCount(len(self._tokens))
        for row, token in enumerate(self._tokens):
            created = str(token.get("created_at") or "")
            try:
                created = created[:16].replace("T", " ")
            except Exception:
                pass
            values = [
                token.get("token_no") or "",
                created,
                token.get("customer_name") or "",
                token.get("customer_mobile") or "",
                token.get("item") or "—",
                str(token.get("file_count", 0)),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tbl.setItem(row, col, item)
        self.lbl_info.setText(f"{len(self._tokens)} token(s) saved")

    def _open_row(self, row: int):
        if not (0 <= row < len(self._tokens)):
            QMessageBox.information(self, "Select a Token",
                                    "Select a token in the list first.")
            return
        TokenPreviewDialog(self._tokens[row], self).exec()


# ═══════════════════════════════════════════════════════════════════════════════
#  Preview / print / save PDF
# ═══════════════════════════════════════════════════════════════════════════════
class TokenPreviewDialog(QDialog):

    def __init__(self, token: dict, parent=None):
        super().__init__(parent)
        self.token = token
        self.setWindowTitle(f"Token Slip — {token.get('token_no', '')}")
        self.setModal(True)
        self.resize(1000, 860)
        self.setMinimumSize(760, 620)
        self.setStyleSheet(_TICKET_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(f"🏷️  Token {token.get('token_no', '')}")
        title.setStyleSheet(f"color:{C_PRIMARY}; font-size:18pt; font-weight:bold;")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(QLabel("Print size:"))
        self.cmb_format = QComboBox()
        for label, value in _format_choices():
            self.cmb_format.addItem(label, value)
        self.cmb_format.setMinimumHeight(38)
        self.cmb_format.currentIndexChanged.connect(self._update_preview)
        head.addWidget(self.cmb_format)

        # Custom paper width × height, used when "Custom size" is selected.
        self.lbl_custom_w = QLabel("W:")
        self.spn_custom_w = QDoubleSpinBox()
        self.spn_custom_w.setRange(30.0, 1200.0)
        self.spn_custom_w.setDecimals(1)
        self.spn_custom_w.setValue(100.0)
        self.spn_custom_w.setSuffix(" mm")
        self.spn_custom_w.setToolTip("Custom paper width in millimetres")
        self.spn_custom_w.valueChanged.connect(self._update_preview)
        head.addWidget(self.lbl_custom_w)
        head.addWidget(self.spn_custom_w)

        self.lbl_custom_x = QLabel("×")
        self.spn_custom_h = QDoubleSpinBox()
        self.spn_custom_h.setRange(30.0, 3000.0)
        self.spn_custom_h.setDecimals(1)
        self.spn_custom_h.setValue(150.0)
        self.spn_custom_h.setSuffix(" mm")
        self.spn_custom_h.setToolTip("Custom paper height in millimetres")
        head.addWidget(self.lbl_custom_x)
        head.addWidget(self.spn_custom_h)
        root.addLayout(head)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet(
            "QTextBrowser { background:white; border:1px solid #E0E0E0; "
            "border-radius:6px; padding:8px; font-size:14pt; }"
        )
        root.addWidget(self.browser, stretch=1)

        note = QLabel(
            "The selected page size is applied when printing or saving as PDF. "
            "The on-screen preview is a convenience view."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        root.addWidget(note)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.btn_print = QPushButton("🖨  Print…")
        self.btn_print.setObjectName("Primary")
        self.btn_print.setFixedHeight(44)
        self.btn_print.clicked.connect(self._print)

        self.btn_pdf = QPushButton("💾  Save PDF…")
        self.btn_pdf.setObjectName("Secondary")
        self.btn_pdf.setFixedHeight(44)
        self.btn_pdf.clicked.connect(self._save_pdf)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("Secondary")
        btn_close.setFixedHeight(44)
        btn_close.clicked.connect(self.accept)

        buttons.addWidget(self.btn_print)
        buttons.addWidget(self.btn_pdf)
        buttons.addStretch()
        buttons.addWidget(btn_close)
        root.addLayout(buttons)

        self._update_preview()

    # ── helpers ───────────────────────────────────────────────────────────────
    def _fmt(self) -> str:
        return self.cmb_format.currentData() or "a4"

    def _html_kwargs(self) -> dict:
        """Extra keyword arguments for build_token_html()."""
        if self._fmt() == "custom":
            return {"custom_width_mm": self.spn_custom_w.value()}
        return {}

    def _thermal_height_mm(self) -> float:
        files = self.token.get("files") or []
        # Each thermal row now has the file name plus a size line below it.
        height = 100 + 10.0 * len(files)
        return max(120.0, min(height, 500.0))

    def _page_size(self) -> QPageSize:
        fmt = self._fmt()
        if fmt == "custom":
            return QPageSize(
                QSizeF(self.spn_custom_w.value(), self.spn_custom_h.value()),
                QPageSize.Unit.Millimeter,
                "Custom",
                QPageSize.SizeMatchPolicy.ExactMatch,
            )
        if fmt == "a5":
            return QPageSize(QPageSize.PageSizeId.A5)
        if fmt == "thermal":
            return QPageSize(
                QSizeF(80.0, self._thermal_height_mm()),
                QPageSize.Unit.Millimeter,
                "Thermal80",
                QPageSize.SizeMatchPolicy.ExactMatch,
            )
        return QPageSize(QPageSize.PageSizeId.A4)

    def _update_preview(self):
        custom = self._fmt() == "custom"
        for widget in (self.lbl_custom_w, self.spn_custom_w,
                       self.lbl_custom_x, self.spn_custom_h):
            widget.setEnabled(custom)
        self.browser.setHtml(
            build_token_html(self.token, self._fmt(), **self._html_kwargs())
        )

    def _apply_page_setup(self, printer: QPrinter):
        printer.setPageSize(self._page_size())
        fmt = self._fmt()
        narrow = fmt == "thermal" or (
            fmt == "custom" and self.spn_custom_w.value() < 100.0
        )
        margin = 3.0 if narrow else 12.0
        printer.setPageMargins(
            QMarginsF(margin, margin, margin, margin),
            QPageLayout.Unit.Millimeter,
        )

    def _render(self, printer: QPrinter):
        doc = QTextDocument()
        doc.setHtml(
            build_token_html(self.token, self._fmt(), **self._html_kwargs())
        )
        # QTextDocument needs an explicit page size, otherwise it falls back to
        # its own default and the slip gets large unintended margins.
        doc.setPageSize(printer.pageRect(QPrinter.Unit.Point).size())
        doc.setDocumentMargin(0)
        doc.print(printer)

    # ── actions ───────────────────────────────────────────────────────────────
    def _print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(f"Token_{self.token.get('token_no', '')}")
        self._apply_page_setup(printer)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("Print Token Slip")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._render(printer)
        except Exception as exc:
            QMessageBox.critical(self, "Print Failed", str(exc))

    def _save_pdf(self):
        default = str(
            Path.home() / f"Token_{self.token.get('token_no', 'token')}.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Token as PDF", default, "PDF (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setDocName(f"Token_{self.token.get('token_no', '')}")
        self._apply_page_setup(printer)
        try:
            self._render(printer)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        if Path(path).exists():
            QMessageBox.information(self, "Saved",
                                    f"Token slip saved as PDF:\n{path}")
        else:
            QMessageBox.critical(self, "Save Failed",
                                 "The PDF file could not be created.")
