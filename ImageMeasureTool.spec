# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Image Measurement & Report Tool
Build with:  pyinstaller ImageMeasureTool.spec
"""

import os
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'reportlab',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.lib.colors',
        'reportlab.lib.units',
        'reportlab.lib.styles',
        'reportlab.lib.enums',
        'reportlab.platypus',
        'reportlab.platypus.tables',
        'reportlab.platypus.flowables',
        'reportlab.pdfbase',
        'reportlab.pdfbase.pdfmetrics',
        'reportlab.pdfgen',
        'PIL._tkinter_finder',
        'PIL.Image',
        'PIL.ExifTags',
        'PIL.TiffImagePlugin',
        'PIL.JpegImagePlugin',
        'PIL.PngImagePlugin',
        'PIL.BmpImagePlugin',
        'PIL.GifImagePlugin',
        'PIL.WebPImagePlugin',
        'PIL.IcoImagePlugin',
        'PIL.EpsImagePlugin',
        'PIL.PdfImagePlugin',
        'PIL.PsdImagePlugin',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'image_analyzer',
        'image_analyzer.core',
        'image_analyzer.core.analyzer',
        'image_analyzer.core.backup',
        'image_analyzer.core.database',
        'image_analyzer.core.reporter',
        'image_analyzer.core.token_report',
        'image_analyzer.core.worker',
        'image_analyzer.ui',
        'image_analyzer.ui.backup',
        'image_analyzer.ui.login',
        'image_analyzer.ui.main_window',
        'image_analyzer.ui.preview',
        'image_analyzer.ui.token',
        'PyQt6.QtPrintSupport',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'cv2'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ImageMeasureTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,        # MUST be False — admin EXEs block D&D from Explorer
    icon=str(SPEC_DIR / 'assets' / 'app.ico'),
    version=str(SPEC_DIR / 'version_info.txt'),
)
