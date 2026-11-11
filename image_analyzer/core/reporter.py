"""
Report generator — slim Excel (.xlsx) report with user-requested columns only.
Columns: File Name | File Format | DPI | Color Mode | W×H (inches) | W×H (feet)
"""

import csv
import os
import shutil
from pathlib import Path
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from image_analyzer.core.analyzer import ImageInfo


# ── Palette ──────────────────────────────────────────────────────────────────
HEADER_BG = "1F3864"
HEADER_FG = "FFFFFF"
OK_BG     = "E8F5E9"
ERROR_BG  = "FFEBEE"
ALT_BG    = "F5F5F5"
TITLE_BG  = "1565C0"

THIN   = Side(style="thin", color="BDBDBD")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _header_cell(ws, row, col, value):
    c = ws.cell(row=row, column=col, value=value)
    c.font      = Font(name="Calibri", bold=True, color=HEADER_FG, size=11)
    c.fill      = PatternFill("solid", fgColor=HEADER_BG)
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border    = BORDER
    return c


def _data_cell(ws, row, col, value, bg=None):
    c = ws.cell(row=row, column=col, value=value)
    c.font      = Font(name="Calibri", size=10)
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.border    = BORDER
    if bg:
        c.fill = PatternFill("solid", fgColor=bg)
    return c


# ── Column definition: (header label, column width) ──────────────────────────
COLUMNS = [
    ("File Name",           28),
    ("File Format",         12),
    ("DPI (X × Y)",         14),
    ("Color Mode",          20),
    ("Width (inches)",      14),
    ("Height (inches)",     14),
    ("Width (feet)",        13),
    ("Height (feet)",       13),
    ("Status",              10),
]


# ── History export ───────────────────────────────────────────────────────────

HISTORY_COLUMNS = [
    ("Date",            13),
    ("Time",            10),
    ("File Name",       30),
    ("Format",           9),
    ("DPI X",            9),
    ("DPI Y",            9),
    ("Color Mode",      20),
    ("W (in)",          10),
    ("H (in)",          10),
    ("W (ft)",          10),
    ("H (ft)",          10),
    ("Status",          11),
    ("Moved To",        50),
]


def format_history_record(rec: dict) -> list[str]:
    """Turn a DB record into the display values used in the table / exports."""
    at = rec.get("analysed_at") or ""
    date_part = at[:10]
    time_part = at[11:19] if len(at) > 10 else ""
    try:
        date_part = datetime.strptime(date_part, "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        pass

    status = rec.get("status") or "—"
    moved_to = rec.get("moved_to") or ""
    if moved_to or status == "Moved":
        status = "Moved ✔"

    def _val(key: str) -> str:
        v = rec.get(key)
        return "" if v in (None, "") else str(v)

    return [
        date_part,
        time_part,
        rec.get("file_name") or "",
        rec.get("file_format") or "",
        _val("dpi_x"),
        _val("dpi_y"),
        rec.get("color_mode_label") or "",
        _val("width_inch"),
        _val("height_inch"),
        _val("width_feet"),
        _val("height_feet"),
        status,
        moved_to or "—",
    ]


def export_history_excel(records: list[dict], report_path: str) -> str:
    """Write the history records to a formatted .xlsx file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "History"
    n_cols = len(HISTORY_COLUMNS)

    # Title row
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    tc = ws.cell(row=1, column=1,
                 value=f"Image Measurement History  —  {len(records)} record(s)  —  "
                       f"{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    tc.font = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    tc.fill = PatternFill("solid", fgColor=TITLE_BG)
    tc.alignment = Alignment(horizontal="center", vertical="center")

    # Header row
    ws.row_dimensions[2].height = 30
    for col_i, (label, width) in enumerate(HISTORY_COLUMNS, start=1):
        _header_cell(ws, 2, col_i, label)
        ws.column_dimensions[get_column_letter(col_i)].width = width

    # Data rows
    for row_offset, rec in enumerate(records):
        row = row_offset + 3
        ws.row_dimensions[row].height = 17
        values = format_history_record(rec)
        status = values[-2]
        if status == "Moved ✔":
            bg = "F3E5F5"
        elif status != "OK":
            bg = ERROR_BG
        else:
            bg = OK_BG if row_offset % 2 == 0 else ALT_BG
        for col_i, val in enumerate(values, start=1):
            _data_cell(ws, row, col_i, val, bg=bg)

    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{get_column_letter(n_cols)}2"

    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(report_path)
    return report_path


def export_history_csv(records: list[dict], report_path: str) -> str:
    """Write the history records to a UTF-8 (BOM) CSV file."""
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([label for label, _ in HISTORY_COLUMNS])
        for rec in records:
            writer.writerow(format_history_record(rec))
    return report_path


def generate_excel_report(
    results: list[ImageInfo],
    report_path: str,
    dest_folder: str | None = None,
    move_files: bool = False,
) -> str:
    """
    Write a slim Excel report and optionally move image files.

    Parameters
    ----------
    results      : analysed ImageInfo list
    report_path  : output .xlsx path
    dest_folder  : folder to move/copy images into (None = skip)
    move_files   : True = move (delete original); False = copy only

    Returns
    -------
    Path to the created .xlsx file.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Image Report"

    n_cols = len(COLUMNS)

    # ── Title row ─────────────────────────────────────────────────────────────
    ws.row_dimensions[1].height = 32
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    tc = ws.cell(row=1, column=1,
                 value=f"Image Measurement Report  —  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    tc.font      = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    tc.fill      = PatternFill("solid", fgColor=TITLE_BG)
    tc.alignment = Alignment(horizontal="center", vertical="center")

    # ── Summary row ───────────────────────────────────────────────────────────
    ws.row_dimensions[2].height = 18
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    ok_n  = sum(1 for r in results if r.status == "OK")
    err_n = len(results) - ok_n
    sc = ws.cell(row=2, column=1,
                 value=f"Total: {len(results)}    ✔ OK: {ok_n}    ✖ Errors: {err_n}")
    sc.font      = Font(name="Calibri", bold=True, size=11)
    sc.alignment = Alignment(horizontal="center", vertical="center")
    sc.fill      = PatternFill("solid", fgColor="E3F2FD")

    # ── Header row ────────────────────────────────────────────────────────────
    ws.row_dimensions[3].height = 34
    for col_i, (label, width) in enumerate(COLUMNS, start=1):
        _header_cell(ws, 3, col_i, label)
        ws.column_dimensions[get_column_letter(col_i)].width = width

    # ── Data rows ─────────────────────────────────────────────────────────────
    for row_offset, info in enumerate(results):
        row = row_offset + 4
        ws.row_dimensions[row].height = 18
        ok = info.status == "OK"
        bg = ERROR_BG if not ok else (OK_BG if row_offset % 2 == 0 else ALT_BG)

        w_ft = round(info.width_inch  / 12, 4) if info.width_inch  else 0.0
        h_ft = round(info.height_inch / 12, 4) if info.height_inch else 0.0

        values = [
            info.file_name,
            info.format,
            f"{info.dpi_x} × {info.dpi_y}",
            info.color_mode_label,
            info.width_inch,
            info.height_inch,
            w_ft,
            h_ft,
            info.status,
        ]
        for col_i, val in enumerate(values, start=1):
            _data_cell(ws, row, col_i, val, bg=bg)

    # ── Freeze + filter ───────────────────────────────────────────────────────
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:{get_column_letter(n_cols)}3"

    # ── Save ──────────────────────────────────────────────────────────────────
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(report_path)

    # ── Move / copy image files ───────────────────────────────────────────────
    if dest_folder:
        dest = Path(dest_folder)
        dest.mkdir(parents=True, exist_ok=True)
        for info in results:
            if info.status == "OK" and info.file_path:
                dst = dest / info.file_name
                try:
                    if move_files:
                        shutil.move(info.file_path, str(dst))
                    else:
                        shutil.copy2(info.file_path, str(dst))
                except Exception:
                    pass

    return report_path
