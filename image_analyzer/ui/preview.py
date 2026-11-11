"""
Image preview dialog — shows the picture plus its measurement metadata.

Works with any format Pillow can open (JPEG, PNG, TIFF, BMP, GIF, WebP,
ICO, PSD, …). PDF/EPS need Ghostscript, so they show a friendly message.
"""

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)

C_BG      = "#F5F5F5"
C_CARD    = "#FFFFFF"
C_BORDER  = "#E0E0E0"
C_SUBTEXT = "#757575"


def _to_pixmap(path: str, max_w: int = 1600, max_h: int = 1200) -> QPixmap:
    """Load any Pillow-supported image and convert it to a QPixmap."""
    with Image.open(path) as im:
        im.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            im = im.convert("RGBA")
            flat = Image.new("RGB", im.size, (255, 255, 255))
            flat.paste(im, mask=im.split()[-1])
            im = flat
        elif im.mode != "RGB":
            im = im.convert("RGB")

        data = im.tobytes("raw", "RGB")
        qimg = QImage(
            data, im.width, im.height, im.width * 3,
            QImage.Format.Format_RGB888,
        ).copy()

    return QPixmap.fromImage(qimg)


class ImagePreviewDialog(QDialog):
    """Preview one image file, with an optional metadata dict."""

    def __init__(self, path: str, meta: dict | None = None, parent=None):
        super().__init__(parent)
        self._path = str(path)
        self._meta = meta or {}
        self._pixmap = QPixmap()

        self.setWindowTitle(f"🖼️  Preview — {Path(self._path).name}")
        self.resize(1080, 880)
        self.setMinimumSize(780, 620)
        self.setStyleSheet(f"QDialog {{ background:{C_BG}; }}")
        self._build_ui()
        self._load_image()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(10)

        # Image area
        frame = QFrame()
        frame.setObjectName("PreviewFrame")
        frame.setStyleSheet(
            f"#PreviewFrame {{ background:{C_CARD}; border:1px solid {C_BORDER}; "
            "border-radius:8px; }"
        )
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(6, 6, 6, 6)
        self.img_label = QLabel("Loading…")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setMinimumSize(520, 380)
        self.img_label.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
        self.img_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        fl.addWidget(self.img_label)
        root.addWidget(frame, stretch=1)

        # Metadata
        meta_box = QFrame()
        meta_box.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border:1px solid {C_BORDER}; "
            "border-radius:8px; }} QLabel { border:none; }"
        )
        grid = QGridLayout(meta_box)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(5)

        row = 0
        for label, value in self._meta_rows():
            key = QLabel(label)
            key.setStyleSheet(f"color:{C_SUBTEXT}; font-size:14pt;")
            key.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            val = QLabel(str(value))
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(key, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(val, row, 1)
            row += 1
        grid.setColumnStretch(1, 1)
        root.addWidget(meta_box)

        # Buttons
        btns = QHBoxLayout()
        self.btn_open = QPushButton("Open in default app")
        self.btn_open.setObjectName("BtnSecondary")
        self.btn_open.setEnabled(Path(self._path).exists())
        self.btn_open.clicked.connect(self._open_external)
        btns.addWidget(self.btn_open)
        btns.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        btns.addWidget(box)
        root.addLayout(btns)

    def _meta_rows(self) -> list[tuple[str, str]]:
        m = self._meta

        def get(*keys, default=""):
            for k in keys:
                v = m.get(k)
                if v not in (None, ""):
                    return v
            return default

        def fmt_num(v, suffix=""):
            if v in (None, "", 0):
                return ""
            return f"{v}{suffix}"

        rows: list[tuple[str, str]] = [("File", Path(self._path).name)]

        fmt = get("format", "file_format")
        if fmt:
            rows.append(("Format", str(fmt)))

        w_px, h_px = get("width_px"), get("height_px")
        if w_px and h_px:
            rows.append(("Pixels", f"{w_px} × {h_px} px"))

        dpi_x, dpi_y = get("dpi_x"), get("dpi_y")
        if dpi_x and dpi_y:
            rows.append(("DPI", f"{dpi_x} × {dpi_y}"))

        if get("width_inch") and get("height_inch"):
            rows.append((
                "Print size",
                f"{fmt_num(get('width_inch'))}″ × {fmt_num(get('height_inch'))}″"
                f"   ({fmt_num(get('width_feet'))} × {fmt_num(get('height_feet'))} ft)",
            ))
        elif get("width_mm") and get("height_mm"):
            rows.append((
                "Print size",
                f"{fmt_num(get('width_mm'))} × {fmt_num(get('height_mm'))} mm",
            ))

        mode = get("color_mode_label", "color_mode")
        if mode:
            rows.append(("Color mode", str(mode)))

        size_kb = get("file_size_kb")
        if size_kb:
            rows.append(("File size", f"{size_kb} KB"))

        status = get("status")
        if status:
            rows.append(("Status", str(status)))

        moved_to = get("moved_to")
        if moved_to:
            rows.append(("Moved to", str(moved_to)))

        rows.append(("Full path", self._path))
        return rows

    # ── Image loading ─────────────────────────────────────────────────────────
    def _load_image(self):
        path = Path(self._path)
        if not path.exists():
            self.img_label.setText(
                "⚠️  File not found.\n\n"
                f"{path}\n\nIt may have been moved or deleted."
            )
            self.btn_open.setEnabled(False)
            return
        try:
            self._pixmap = _to_pixmap(self._path)
        except Exception as exc:
            self.img_label.setText(
                "⚠️  This file can't be previewed.\n\n"
                f"{exc}\n\nUse “Open in default app” to view it."
            )
            return
        self._apply_scaled_pixmap()

    def _apply_scaled_pixmap(self):
        if self._pixmap.isNull():
            return
        area = self.img_label.size()
        self.img_label.setPixmap(
            self._pixmap.scaled(
                area,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self._apply_scaled_pixmap()

    def _open_external(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))
