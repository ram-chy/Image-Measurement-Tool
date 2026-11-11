"""
Login, first-run account setup and user management dialogs.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QMessageBox,
    QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame,
)

from image_analyzer import __version__, __copyright__
from image_analyzer.core.database import (
    authenticate, create_user, list_users, delete_user,
    update_user_password, count_admins,
)

C_PRIMARY = "#1565C0"
C_BG      = "#F5F5F5"
C_CARD    = "#FFFFFF"
C_BORDER  = "#E0E0E0"
C_TEXT    = "#212121"
C_SUBTEXT = "#757575"
C_ERROR   = "#C62828"

_DIALOG_QSS = f"""
    QDialog {{ background:{C_BG}; color:{C_TEXT}; }}
    QLabel {{ color:{C_TEXT}; font-size:14pt; }}
    #Card {{ background:{C_CARD}; border:1px solid {C_BORDER};
             border-radius:10px; }}
    QLineEdit {{ border:1px solid {C_BORDER}; border-radius:6px;
                 padding:6px 10px; background:{C_CARD}; color:{C_TEXT};
                 font-size:14pt; }}
    QLineEdit:focus {{ border-color:{C_PRIMARY}; }}
    QPushButton {{ font-size:14pt; }}
    QCheckBox {{ color:{C_TEXT}; font-size:14pt; }}
    #Primary {{ background:{C_PRIMARY}; color:white; border:none;
                border-radius:6px; padding:8px 22px; font-weight:bold; }}
    #Primary:hover {{ background:#1976D2; }}
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Create / add account
# ═══════════════════════════════════════════════════════════════════════════════
class AccountDialog(QDialog):
    """
    Used both for the very first administrator account and for adding a new
    user from the management screen.
    """

    def __init__(self, title: str, admin_locked: bool = False,
                 first_run: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(_DIALOG_QSS)
        self.user: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        head = QLabel("🖼️  Image Measurement & Report Tool")
        head.setStyleSheet(f"color:{C_PRIMARY}; font-size:16pt; font-weight:bold;")
        root.addWidget(head)

        sub = QLabel(title)
        sub.setStyleSheet(f"color:{C_TEXT}; font-size:15pt; font-weight:bold;")
        root.addWidget(sub)

        if first_run:
            note = QLabel(
                "No user accounts exist yet. Create the administrator account "
                "that will be used to sign in and to manage other users."
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
            root.addWidget(note)

        card = QFrame(); card.setObjectName("Card")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("e.g. Ram Chowdhury")
        self.ed_name.setFixedHeight(42)

        self.ed_username = QLineEdit()
        self.ed_username.setPlaceholderText("Login username")
        self.ed_username.setFixedHeight(42)

        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_password.setFixedHeight(42)

        self.ed_confirm = QLineEdit()
        self.ed_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_confirm.setFixedHeight(42)

        self.chk_admin = QCheckBox("Administrator (can manage users)")
        self.chk_admin.setStyleSheet("font-size:14pt;")
        if admin_locked:
            self.chk_admin.setChecked(True)
            self.chk_admin.setEnabled(False)

        form.addRow("Display name:", self.ed_name)
        form.addRow("Username:", self.ed_username)
        form.addRow("Password:", self.ed_password)
        form.addRow("Confirm password:", self.ed_confirm)
        form.addRow("", self.chk_admin)
        root.addWidget(card)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("Error")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        root.addWidget(self.lbl_error)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("Secondary")
        btn_cancel.setFixedHeight(40)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Create Account")
        btn_ok.setObjectName("Primary")
        btn_ok.setFixedHeight(40)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._create)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        root.addLayout(buttons)

        self.ed_name.setFocus()

    def _error(self, text: str):
        self.lbl_error.setText(text)
        self.lbl_error.show()

    def _create(self):
        name = self.ed_name.text().strip()
        username = self.ed_username.text().strip()
        password = self.ed_password.text()
        confirm = self.ed_confirm.text()

        if not name:
            return self._error("Please enter the display name.")
        if not username:
            return self._error("Please enter a username.")
        if len(password) < 4:
            return self._error("Password must be at least 4 characters.")
        if password != confirm:
            return self._error("The two passwords do not match.")

        try:
            user_id = create_user(
                username, name, password,
                is_admin=self.chk_admin.isChecked(),
            )
        except ValueError as exc:
            return self._error(str(exc))

        self.user = {
            "id": user_id,
            "username": username,
            "display_name": name,
            "is_admin": self.chk_admin.isChecked(),
        }
        self.accept()


# ═══════════════════════════════════════════════════════════════════════════════
#  Login
# ═══════════════════════════════════════════════════════════════════════════════
class LoginDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login — Image Measurement & Report Tool")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(_DIALOG_QSS)
        self.user: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(12)

        icon = QLabel("🖼️")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size:34pt;")
        root.addWidget(icon)

        title = QLabel("Image Measurement & Report Tool")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{C_PRIMARY}; font-size:17pt; font-weight:bold;")
        root.addWidget(title)

        sub = QLabel("Sign in to continue")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        root.addWidget(sub)

        card = QFrame(); card.setObjectName("Card")
        form = QFormLayout(card)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)

        self.ed_username = QLineEdit()
        self.ed_username.setPlaceholderText("Username")
        self.ed_username.setFixedHeight(44)
        self.ed_password = QLineEdit()
        self.ed_password.setPlaceholderText("Password")
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_password.setFixedHeight(44)
        self.ed_password.returnPressed.connect(self._login)

        form.addRow("Username:", self.ed_username)
        form.addRow("Password:", self.ed_password)
        root.addWidget(card)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("Error")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        root.addWidget(self.lbl_error)

        self.btn_login = QPushButton("🔓  Login")
        self.btn_login.setObjectName("Primary")
        self.btn_login.setFixedHeight(46)
        self.btn_login.setDefault(True)
        self.btn_login.clicked.connect(self._login)
        root.addWidget(self.btn_login)

        footer = QLabel(f"Version {__version__}   •   {__copyright__}")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        footer.setWordWrap(True)
        root.addWidget(footer)

        self.ed_username.setFocus()

    def _error(self, text: str):
        self.lbl_error.setText(text)
        self.lbl_error.show()

    def _login(self):
        username = self.ed_username.text().strip()
        password = self.ed_password.text()
        if not username or not password:
            return self._error("Enter your username and password.")

        user = authenticate(username, password)
        if not user:
            self._error("Invalid username or password.")
            self.ed_password.selectAll()
            self.ed_password.setFocus()
            return

        self.user = user
        self.accept()


# ═══════════════════════════════════════════════════════════════════════════════
#  User management (administrators only)
# ═══════════════════════════════════════════════════════════════════════════════
class UserManagementDialog(QDialog):

    def __init__(self, current_user: dict, parent=None):
        super().__init__(parent)
        self.current_user = current_user
        self._users: list[dict] = []
        self.setWindowTitle("Manage Users")
        self.setModal(True)
        self.resize(1020, 620)
        self.setMinimumSize(880, 520)
        self.setStyleSheet(_DIALOG_QSS)
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("👥  User Accounts")
        title.setStyleSheet(f"color:{C_PRIMARY}; font-size:18pt; font-weight:bold;")
        head.addWidget(title)
        head.addStretch()
        hint = QLabel("Token slips show the logged-in user's name.")
        hint.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        head.addWidget(hint)
        root.addLayout(head)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(
            ["Username", "Display Name", "Role", "Created"]
        )
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.verticalHeader().setDefaultSectionSize(34)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.tbl.setColumnWidth(0, 230)
        self.tbl.setColumnWidth(2, 130)
        self.tbl.setColumnWidth(3, 220)
        root.addWidget(self.tbl, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_add = QPushButton("➕  Add")
        self.btn_add.setObjectName("Primary")
        self.btn_add.setFixedHeight(40)
        self.btn_add.setToolTip("Create a new user account")
        self.btn_add.clicked.connect(self._add_user)

        self.btn_reset = QPushButton("🔑  Reset")
        self.btn_reset.setObjectName("Secondary")
        self.btn_reset.setFixedHeight(40)
        self.btn_reset.setToolTip("Reset the selected user's password")
        self.btn_reset.clicked.connect(self._reset_password)

        self.btn_delete = QPushButton("🗑  Delete")
        self.btn_delete.setObjectName("Secondary")
        self.btn_delete.setFixedHeight(40)
        self.btn_delete.setToolTip("Delete the selected user account")
        self.btn_delete.clicked.connect(self._delete_user)

        row.addWidget(self.btn_add)
        row.addWidget(self.btn_reset)
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
        self._users = list_users()
        self.tbl.setRowCount(len(self._users))
        for row, u in enumerate(self._users):
            values = [
                u["username"],
                u["display_name"],
                "Admin" if u["is_admin"] else "User",
                (u.get("created_at") or "")[:16],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tbl.setItem(row, col, item)
        self.lbl_info.setText(f"{len(self._users)} account(s)")

    def _selected(self) -> dict | None:
        row = self.tbl.currentRow()
        if row < 0 or row >= len(self._users):
            QMessageBox.information(self, "Select a User",
                                    "Select a user in the list first.")
            return None
        return self._users[row]

    def _add_user(self):
        dlg = AccountDialog("Add User", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _reset_password(self):
        user = self._selected()
        if not user:
            return
        pwd, ok = QInputDialog.getText(
            self, "Reset Password",
            f"New password for {user['display_name']} ({user['username']}):",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        try:
            update_user_password(user["id"], pwd)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Password", str(exc))
            return
        QMessageBox.information(self, "Password Changed",
                                f"Password updated for {user['display_name']}.")

    def _delete_user(self):
        user = self._selected()
        if not user:
            return
        if user["id"] == self.current_user.get("id"):
            QMessageBox.warning(self, "Cannot Delete",
                                "You cannot delete the account you are signed in with.")
            return
        if user["is_admin"] and count_admins() <= 1:
            QMessageBox.warning(self, "Cannot Delete",
                                "At least one administrator account must remain.")
            return
        reply = QMessageBox.question(
            self, "Delete User",
            f"Delete the account “{user['display_name']}” ({user['username']})?\n\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        delete_user(user["id"])
        self._load()
