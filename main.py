"""
Entry point — Image Measurement & Report Tool
Run with:  python main.py
"""

import sys
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPalette, QColor
from image_analyzer.core.database import init_db, count_users
from image_analyzer.ui.login import AccountDialog, LoginDialog
from image_analyzer.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Image Measurement Tool")
    app.setOrganizationName("ImageTool")
    app.setStyle("Fusion")
    # Global baseline font — the UI never goes below 14 pt
    app.setFont(QFont("Segoe UI", 14))

    # Force a light palette.  Without this, Windows dark mode can make the
    # text white while our stylesheets paint the fields white (invisible text).
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F5F5F5"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#212121"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#FAFAFA"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#212121"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#212121"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#1565C0"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#212121"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9E9E9E"))
    app.setPalette(palette)

    init_db()

    # ── First run: create the administrator account ───────────────────────
    if count_users() == 0:
        dlg = AccountDialog(
            "Create Administrator Account",
            admin_locked=True,
            first_run=True,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.user:
            sys.exit(0)
        user = dlg.user
    else:
        dlg = LoginDialog()
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.user:
            sys.exit(0)
        user = dlg.user

    window = MainWindow(user=user)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
