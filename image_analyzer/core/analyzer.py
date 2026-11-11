"""
Core image analysis engine.
Extracts dimensions, DPI, color mode, file size, color profile, and bit depth.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image
import struct


# Maps Pillow mode -> human-readable color mode label
MODE_LABELS = {
    "1":     "Bitmap (1-bit B&W)",
    "L":     "Grayscale (8-bit)",
    "LA":    "Grayscale + Alpha",
    "P":     "Palette (Indexed)",
    "RGB":   "RGB (24-bit)",
    "RGBA":  "RGB + Alpha (32-bit)",
    "CMYK":  "CMYK (32-bit)",
    "YCbCr": "YCbCr",
    "LAB":   "CIE Lab",
    "HSV":   "HSV",
    "I":     "32-bit Integer Grayscale",
    "F":     "32-bit Float Grayscale",
}

# Bits per channel per mode
MODE_BIT_DEPTH = {
    "1": 1, "L": 8, "LA": 8, "P": 8,
    "RGB": 8, "RGBA": 8, "CMYK": 8,
    "YCbCr": 8, "LAB": 8, "HSV": 8,
    "I": 32, "F": 32,
}

# Number of channels per mode
MODE_CHANNELS = {
    "1": 1, "L": 1, "LA": 2, "P": 1,
    "RGB": 3, "RGBA": 4, "CMYK": 4,
    "YCbCr": 3, "LAB": 3, "HSV": 3,
    "I": 1, "F": 1,
}


@dataclass
class ImageInfo:
    """Holds all extracted metadata for one image file."""
    file_name: str = ""
    file_path: str = ""
    file_size_bytes: int = 0
    file_size_kb: float = 0.0
    file_size_mb: float = 0.0
    format: str = ""
    width_px: int = 0
    height_px: int = 0
    width_mm: float = 0.0
    height_mm: float = 0.0
    width_inch: float = 0.0
    height_inch: float = 0.0
    dpi_x: float = 0.0
    dpi_y: float = 0.0
    color_mode: str = ""
    color_mode_label: str = ""
    bit_depth: int = 0
    channels: int = 0
    color_profile: str = ""
    has_alpha: bool = False
    error: str = ""
    status: str = "OK"


def _extract_color_profile(img: Image.Image) -> str:
    """Try to get ICC profile description or return 'None'."""
    try:
        icc = img.info.get("icc_profile")
        if not icc:
            return "None"
        # Look for the 'desc' tag in ICC data (offset 128+)
        # Simple heuristic: search for ASCII description
        pos = icc.find(b"desc")
        if pos == -1:
            return "Embedded ICC (unknown)"
        # Try to read the description string
        # 'desc' tag: 4 bytes sig, 4 bytes offset, 4 bytes size
        try:
            # Find profile description — mluc or desc tag
            if b"sRGB" in icc:
                return "sRGB"
            if b"Adobe RGB" in icc:
                return "Adobe RGB (1998)"
            if b"ProPhoto" in icc:
                return "ProPhoto RGB"
            if b"CMYK" in icc:
                return "CMYK (Embedded)"
            if b"Gray" in icc or b"grey" in icc.lower():
                return "Grayscale (Embedded)"
            return "Embedded ICC Profile"
        except Exception:
            return "Embedded ICC Profile"
    except Exception:
        return "None"


def analyze_image(file_path: str) -> ImageInfo:
    """
    Analyze a single image file and return an ImageInfo dataclass.
    """
    info = ImageInfo()
    info.file_path = file_path
    info.file_name = Path(file_path).name

    try:
        # File size
        size_bytes = os.path.getsize(file_path)
        info.file_size_bytes = size_bytes
        info.file_size_kb = round(size_bytes / 1024, 2)
        info.file_size_mb = round(size_bytes / (1024 * 1024), 3)

        with Image.open(file_path) as img:
            info.format = img.format or Path(file_path).suffix.lstrip(".").upper()
            info.width_px, info.height_px = img.size
            info.color_mode = img.mode
            info.color_mode_label = MODE_LABELS.get(img.mode, img.mode)
            info.bit_depth = MODE_BIT_DEPTH.get(img.mode, 8)
            info.channels = MODE_CHANNELS.get(img.mode, len(img.getbands()))
            info.has_alpha = img.mode in ("RGBA", "LA", "PA")
            info.color_profile = _extract_color_profile(img)

            # DPI
            dpi = img.info.get("dpi")
            if dpi:
                info.dpi_x = round(float(dpi[0]), 2)
                info.dpi_y = round(float(dpi[1]), 2)
            else:
                # Check EXIF for resolution
                try:
                    exif = img._getexif() if hasattr(img, "_getexif") else None
                    if exif:
                        # Tag 282 = XResolution, 283 = YResolution
                        xres = exif.get(282)
                        yres = exif.get(283)
                        if xres:
                            info.dpi_x = round(float(xres[0]) / float(xres[1]) if isinstance(xres, tuple) else float(xres), 2)
                        if yres:
                            info.dpi_y = round(float(yres[0]) / float(yres[1]) if isinstance(yres, tuple) else float(yres), 2)
                except Exception:
                    pass
                if not info.dpi_x:
                    info.dpi_x = 72.0
                    info.dpi_y = 72.0

            # Physical dimensions
            if info.dpi_x > 0:
                info.width_inch = round(info.width_px / info.dpi_x, 3)
                info.height_inch = round(info.height_px / info.dpi_y, 3)
                info.width_mm = round(info.width_inch * 25.4, 2)
                info.height_mm = round(info.height_inch * 25.4, 2)

        info.status = "OK"

    except Exception as e:
        info.status = "ERROR"
        info.error = str(e)

    return info


def analyze_multiple(file_paths: list[str]) -> list[ImageInfo]:
    """Analyze a list of image files and return results."""
    return [analyze_image(fp) for fp in file_paths]
