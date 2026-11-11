"""Backup settings dialog."""

from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QFileDialog, QMessageBox, QFrame,
)

from image_analyzer.core.backup import (
    backup_path, create_backup, get_backup_settings, set_backup_settings,
)

C_PRIMARY = "#1565C0"
C_BG      = "#F5F5F5"
C_CARD    = "#FFFFFF"
C_BORDER  = "#E0E0E0"
C_TEXT    = "#212121"
C_SUBTEXT = "#757575"

_QSS = f"""
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
"""


class BackupDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💾  Backup Data")
        self.setModal(True)
        self.resize(780, 380)
        self.setMinimumWidth(680)
        self.setStyleSheet(_QSS)
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QLabel("💾  Backup Data")
        title.setStyleSheet(
            f"color:{C_PRIMARY}; font-size:18pt; font-weight:bold;"
        )
        root.addWidget(title)

        info = QLabel(
            "Choose a folder for the backup. A complete copy of the database "
            "is saved there once a day while the app is running. "
            "The previous backup file is replaced automatically, so only the "
            "latest backup is kept."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        root.addWidget(info)

        card = QFrame()
        card.setObjectName("Card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(16, 14, 16, 14)
        card_lay.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Backup folder:"))
        self.ed_folder = QLineEdit()
        self.ed_folder.setPlaceholderText(
            "Select a folder, e.g. an external drive or OneDrive folder"
        )
        self.ed_folder.setFixedHeight(40)
        row.addWidget(self.ed_folder, stretch=1)
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.setObjectName("Secondary")
        self.btn_browse.setFixedHeight(40)
        self.btn_browse.clicked.connect(self._browse)
        row.addWidget(self.btn_browse)
        card_lay.addLayout(row)

        self.chk_auto = QCheckBox("Back up automatically once every day")
        self.chk_auto.setToolTip(
            "The app checks the date at startup and while it stays open."
        )
        card_lay.addWidget(self.chk_auto)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        card_lay.addWidget(self.lbl_status)

        root.addWidget(card)
        root.addStretch()

        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.btn_backup_now = QPushButton("💾  Backup Now")
        self.btn_backup_now.setObjectName("Primary")
        self.btn_backup_now.setFixedHeight(44)
        self.btn_backup_now.clicked.connect(self._backup_now)
        actions.addWidget(self.btn_backup_now)

        actions.addStretch()

        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("Secondary")
        self.btn_save.setFixedHeight(44)
        self.btn_save.clicked.connect(self._save_and_close)
        actions.addWidget(self.btn_save)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("Secondary")
        self.btn_close.setFixedHeight(44)
        self.btn_close.clicked.connect(self.reject)
        actions.addWidget(self.btn_close)

        root.addLayout(actions)

    def _load(self):
        settings = get_backup_settings()
        self.ed_folder.setText(settings["backup_dir"])
        self.chk_auto.setChecked(
            settings["auto_backup"] and bool(settings["backup_dir"])
        )
        self._refresh_status(settings)

    def _refresh_status(self, settings: dict | None = None):
        settings = settings or get_backup_settings()
        folder = settings["backup_dir"]
        if not folder:
            self.lbl_status.setText(
                "No backup folder selected. Automatic backup is off."
            )
            return

        target = backup_path(folder)
        if target.exists():
            try:
                modified = datetime.fromtimestamp(
                    target.stat().st_mtime
                ).strftime("%d %b %Y, %I:%M %p")
            except OSError:
                modified = "unknown"
            self.lbl_status.setText(
                f"Latest backup: {target.name}  •  {modified}\n{target}"
            )
        else:
            self.lbl_status.setText(
                f"No backup created yet.\nBackup will be saved to: {target}"
            )

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Backup Folder", self.ed_folder.text().strip()
        )
        if folder:
            self.ed_folder.setText(folder)
            self.chk_auto.setChecked(True)
            self._refresh_status({"backup_dir": folder, "auto_backup": True,
                                  "last_backup_date": ""})

    def _save(self) -> bool:
        folder = self.ed_folder.text().strip()
        auto = self.chk_auto.isChecked()
        if auto and not folder:
            QMessageBox.warning(
                self, "Backup Folder",
                "Choose a backup folder before enabling automatic backups.",
            )
            self.ed_folder.setFocus()
            return False
        set_backup_settings(folder, auto)
        self._refresh_status()
        return True

    def _backup_now(self):
        if not self._save():
            return
        folder = self.ed_folder.text().strip()
        if not folder:
            QMessageBox.warning(
                self, "Backup Folder", "Please choose a backup folder first."
            )
            self.ed_folder.setFocus()
            return
        try:
            path = create_backup(folder)
        except Exception as exc:
            QMessageBox.critical(
                self, "Backup Failed",
                f"Could not create the backup:\n\n{exc}",
            )
            return
        self._refresh_status()
        QMessageBox.information(
            self, "Backup Complete",
            f"Backup saved and verified:\n\n{path}",
        )

    def _save_and_close(self):
        if self._save():
            self.accept()

    def reject(self):
        # Save the folder choice even when the dialog is closed with X.
        folder = self.ed_folder.text().strip()
        set_backup_settings(folder, self.chk_auto.isChecked() and bool(folder))
        super().reject()
