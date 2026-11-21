"""
Customer management dialogs — add, edit and delete saved customers.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)

from image_analyzer.core.database import (
    fetch_customers, create_customer, update_customer, delete_customer,
)

C_PRIMARY = "#1565C0"
C_SUCCESS = "#2E7D32"
C_BG = "#F5F5F5"
C_CARD = "#FFFFFF"
C_BORDER = "#E0E0E0"
C_TEXT = "#212121"
C_SUBTEXT = "#757575"
C_ERROR = "#C62828"

_DIALOG_QSS = (
    f"\n    QDialog {{ background:{C_BG}; color:{C_TEXT}; }}\n"
    f"    QLabel {{ color:{C_TEXT}; font-size:14pt; }}\n"
    f"    QLineEdit {{ border:1px solid {C_BORDER}; border-radius:6px;\n"
    f"                 padding:6px 10px; background:{C_CARD}; color:{C_TEXT};\n"
    f"                 font-size:14pt; }}\n"
    f"    QLineEdit:focus {{ border-color:{C_PRIMARY}; }}\n"
    f"    QPushButton {{ font-size:14pt; }}\n"
    f"    #Primary {{ background:{C_PRIMARY}; color:white; border:none;\n"
    f"                 border-radius:6px; padding:8px 22px; font-weight:bold; }}\n"
    f"    #Primary:hover {{ background:#1976D2; }}\n"
    f"    #Secondary {{ background:{C_CARD}; color:{C_TEXT};\n"
    f"                   border:1px solid {C_BORDER}; border-radius:6px;\n"
    f"                   padding:6px 14px; }}\n"
    f"    #Secondary:hover {{ background:#EEEEEE; }}\n"
    f"    #Error {{ color:{C_ERROR}; font-size:14pt; }}\n"
    f"    QTableWidget {{ background:{C_CARD}; alternate-background-color:#FAFAFA;\n"
    f"                     color:{C_TEXT}; border:1px solid {C_BORDER};\n"
    f"                     border-radius:6px; gridline-color:{C_BORDER};\n"
    f"                     font-size:14pt; }}\n"
    f"    QHeaderView::section {{ background:{C_PRIMARY}; color:white;\n"
    f"                             padding:6px; border:none; font-weight:bold; }}\n"
)




class CustomerDialog(QDialog):

    def __init__(self, customer: dict | None = None, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.setWindowTitle("Edit Customer" if customer else "Add Customer")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(_DIALOG_QSS)
        self._build_ui()
        if customer:
            self.ed_name.setText(customer.get("name", ""))
            self.ed_mobile.setText(customer.get("mobile", ""))
            self.ed_item.setText(customer.get("item", ""))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title = QLabel("🧑  Customer Details")
        title.setStyleSheet(f"color:{C_PRIMARY}; font-size:18pt; font-weight:bold;")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Customer name")
        self.ed_name.setFixedHeight(40)
        self.ed_name.textChanged.connect(self._check_existing)
        form.addRow("Customer name:", self.ed_name)

        self.lbl_match = QLabel("")
        self.lbl_match.setWordWrap(True)
        self.lbl_match.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        form.addRow("", self.lbl_match)

        self.ed_mobile = QLineEdit()
        self.ed_mobile.setPlaceholderText("Mobile number")
        self.ed_mobile.setFixedHeight(40)
        form.addRow("Mobile no:", self.ed_mobile)

        self.ed_item = QLineEdit()
        self.ed_item.setPlaceholderText("Last used item (optional)")
        self.ed_item.setFixedHeight(40)
        form.addRow("Item:", self.ed_item)
        root.addLayout(form)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("Error")
        self.lbl_error.setWordWrap(True)
        root.addWidget(self.lbl_error)

        row = QHBoxLayout()
        row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("Secondary")
        btn_cancel.setFixedHeight(40)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("💾  Save")
        btn_save.setObjectName("Primary")
        btn_save.setFixedHeight(40)
        btn_save.clicked.connect(self._save)

        row.addWidget(btn_cancel)
        row.addWidget(btn_save)
        root.addLayout(row)

    def _check_existing(self, *_args):
        """Show previously saved customers whose name matches what is typed."""
        typed = self.ed_name.text().strip().casefold()
        if len(typed) < 2:
            self.lbl_match.setText("")
            return

        matches = [
            c for c in fetch_customers()
            if typed in (c["name"] or "").casefold()
            and not (self.customer and c["id"] == self.customer["id"])
        ]

        if not matches:
            self.lbl_match.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
            self.lbl_match.setText(
                "" if self.customer else "No saved customer with this name.")
            return

        self.lbl_match.setStyleSheet(f"color:{C_SUCCESS}; font-size:14pt;")
        if len(matches) == 1:
            c = matches[0]
            self.lbl_match.setText(f"✔ Already saved: {c['name']} — {c['mobile']}")
            return
        self.lbl_match.setText(f"✔ {len(matches)} saved customers with this name.")

    def _save(self):
        name = self.ed_name.text().strip()
        mobile = self.ed_mobile.text().strip()
        item = self.ed_item.text().strip()
        try:
            if self.customer:
                update_customer(self.customer["id"], name, mobile, item)
            else:
                create_customer(name, mobile, item)
        except ValueError as exc:
            self.lbl_error.setText(str(exc))
            if len(name) < 2:
                self.ed_name.setFocus()
            else:
                self.ed_mobile.setFocus()
            return
        self.accept()


class CustomerManagementDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._customers = []
        self.setWindowTitle("Manage Customers")
        self.setModal(True)
        self.resize(900, 560)
        self.setMinimumSize(760, 440)
        self.setStyleSheet(_DIALOG_QSS)
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("🧑  Saved Customers")
        title.setStyleSheet(
            f"color:{C_PRIMARY}; font-size:18pt; font-weight:bold;"
        )
        head.addWidget(title)
        head.addStretch()
        hint = QLabel("Pick a customer in the Token window to reuse these details.")
        hint.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        head.addWidget(hint)
        root.addLayout(head)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(
            ["Name", "Mobile", "Item", "Created"]
        )
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.verticalHeader().setDefaultSectionSize(34)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl.setColumnWidth(1, 180)
        self.tbl.setColumnWidth(2, 200)
        self.tbl.setColumnWidth(3, 180)
        root.addWidget(self.tbl, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_add = QPushButton("➕  Add")
        self.btn_add.setObjectName("Primary")
        self.btn_add.setFixedHeight(40)
        self.btn_add.setToolTip("Add a new customer")
        self.btn_add.clicked.connect(self._add_customer)

        self.btn_edit = QPushButton("✏️  Edit")
        self.btn_edit.setObjectName("Secondary")
        self.btn_edit.setFixedHeight(40)
        self.btn_edit.setToolTip("Edit the selected customer")
        self.btn_edit.clicked.connect(self._edit_customer)

        self.btn_delete = QPushButton("🗑  Delete")
        self.btn_delete.setObjectName("Secondary")
        self.btn_delete.setFixedHeight(40)
        self.btn_delete.setToolTip("Delete the selected customer")
        self.btn_delete.clicked.connect(self._delete_customer)

        row.addWidget(self.btn_add)
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_delete)
        row.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setObjectName("Secondary")
        btn_close.setFixedHeight(40)
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        root.addLayout(row)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        root.addWidget(self.lbl_info)

    def _load(self):
        self._customers = fetch_customers()
        self.tbl.setRowCount(len(self._customers))
        for row, c in enumerate(self._customers):
            values = [
                c["name"],
                c["mobile"],
                c.get("item", ""),
                (c.get("created_at") or "")[:16],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tbl.setItem(row, col, item)
        self.lbl_info.setText(f"{len(self._customers)} customer(s)")

    def _selected(self) -> dict | None:
        row = self.tbl.currentRow()
        if row < 0 or row >= len(self._customers):
            QMessageBox.information(
                self, "Select a Customer",
                "Select a customer in the list first.",
            )
            return None
        return self._customers[row]

    def _add_customer(self):
        dlg = CustomerDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _edit_customer(self):
        customer = self._selected()
        if not customer:
            return
        dlg = CustomerDialog(customer, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _delete_customer(self):
        customer = self._selected()
        if not customer:
            return
        reply = QMessageBox.question(
            self,
            "Delete Customer",
            f"Delete the customer “{customer['name']}” "
            f"({customer['mobile']})?\n\n"
            "Saved token slips keep their copy of these details.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        delete_customer(customer["id"])
        self._load()
