"""
PDF Token generator.
Creates a compact, printable job-token slip listing:
  - Token number (auto-incremented per session)
  - Date & time
  - Destination folder
  - Per file: File Name | Width × Height (inches) | Width × Height (feet)
"""

from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from reportlab.pdfbase import pdfmetrics

from image_analyzer.core.analyzer import ImageInfo
from image_analyzer.core.database import get_connection, init_db


# ── Colour palette ────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#1F3864")
BLUE    = colors.HexColor("#1565C0")
LBLUE   = colors.HexColor("#E3F2FD")
WHITE   = colors.white
GREEN   = colors.HexColor("#2E7D32")
LGRAY   = colors.HexColor("#F5F5F5")
GRAY    = colors.HexColor("#757575")
BLACK   = colors.black


def _next_token_number() -> int:
    """Auto-increment token counter stored in a simple DB table."""
    init_db()
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS token_counter (
                id      INTEGER PRIMARY KEY CHECK (id = 1),
                counter INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            INSERT INTO token_counter (id, counter) VALUES (1, 0)
            ON CONFLICT(id) DO NOTHING
        """)
        con.execute("UPDATE token_counter SET counter = counter + 1 WHERE id = 1")
        con.commit()
        row = con.execute("SELECT counter FROM token_counter WHERE id = 1").fetchone()
    return row[0]


def generate_token_pdf(
    results: list[ImageInfo],
    dest_folder: str,
    token_number: int | None = None,
) -> str:
    """
    Generate a PDF token slip for the moved files.

    Parameters
    ----------
    results      : list of ImageInfo (only OK + moved files)
    dest_folder  : destination folder path (shown on token + save location)
    token_number : override token number (auto-generated if None)

    Returns
    -------
    Full path of the saved PDF file.
    """
    if token_number is None:
        token_number = _next_token_number()

    now        = datetime.now()
    date_str   = now.strftime("%d %B %Y")
    time_str   = now.strftime("%I:%M %p")
    token_id   = f"TKN-{now.strftime('%Y%m%d')}-{token_number:04d}"
    pdf_name   = f"Token_{token_id}.pdf"
    pdf_path   = str(Path(dest_folder) / pdf_name)

    # Page: A5-ish width, variable height — use A4
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=14*mm,  bottomMargin=14*mm,
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Header ────────────────────────────────────────────────────────────────
    hdr_style = ParagraphStyle(
        "hdr", fontSize=18, fontName="Helvetica-Bold",
        textColor=WHITE, alignment=TA_CENTER, spaceAfter=0,
    )
    sub_style = ParagraphStyle(
        "sub", fontSize=10, fontName="Helvetica",
        textColor=LBLUE, alignment=TA_CENTER, spaceAfter=0,
    )

    hdr_data = [[
        Paragraph("IMAGE JOB TOKEN", hdr_style),
    ]]
    hdr_table = Table(hdr_data, colWidths=[174*mm])
    hdr_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), NAVY),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("ROUNDEDCORNERS",(0,0), (-1,-1), [6,6,0,0]),
    ]))
    story.append(hdr_table)

    # ── Token meta info ───────────────────────────────────────────────────────
    meta_style = ParagraphStyle(
        "meta", fontSize=9, fontName="Helvetica",
        textColor=GRAY, alignment=TA_LEFT,
    )
    bold_style = ParagraphStyle(
        "bold", fontSize=10, fontName="Helvetica-Bold",
        textColor=BLACK, alignment=TA_LEFT,
    )
    token_id_style = ParagraphStyle(
        "tid", fontSize=14, fontName="Helvetica-Bold",
        textColor=BLUE, alignment=TA_CENTER,
    )

    meta_data = [
        [
            Paragraph(f"<b>Token No.</b>", bold_style),
            Paragraph(token_id, token_id_style),
            Paragraph(f"<b>Date:</b> {date_str}", bold_style),
        ],
        [
            Paragraph(f"<b>Time:</b> {time_str}", bold_style),
            Paragraph(f"<b>Files:</b> {len(results)}", bold_style),
            Paragraph(f"<b>Destination:</b>", bold_style),
        ],
        [
            Paragraph("", meta_style),
            Paragraph("", meta_style),
            Paragraph(str(dest_folder), meta_style),
        ],
    ]
    col_w = [40*mm, 70*mm, 64*mm]
    meta_table = Table(meta_data, colWidths=col_w)
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), LBLUE),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("SPAN",          (1,0), (1,1)),   # Token ID spans 2 rows in col 1
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE))
    story.append(Spacer(1, 3*mm))

    # ── File table ────────────────────────────────────────────────────────────
    col_header_style = ParagraphStyle(
        "ch", fontSize=9, fontName="Helvetica-Bold",
        textColor=WHITE, alignment=TA_CENTER,
    )
    cell_style = ParagraphStyle(
        "cell", fontSize=9, fontName="Helvetica",
        textColor=BLACK, alignment=TA_LEFT,
    )
    dim_style = ParagraphStyle(
        "dim", fontSize=9, fontName="Helvetica",
        textColor=BLACK, alignment=TA_CENTER,
    )

    # Header row
    file_rows = [[
        Paragraph("#",             col_header_style),
        Paragraph("File Name",     col_header_style),
        Paragraph("Width × Height\n(Inches)",  col_header_style),
        Paragraph("Width × Height\n(Feet)",    col_header_style),
    ]]

    # Data rows
    for idx, info in enumerate(results, start=1):
        w_in = info.width_inch  or 0.0
        h_in = info.height_inch or 0.0
        w_ft = round(w_in / 12, 3)
        h_ft = round(h_in / 12, 3)

        file_rows.append([
            Paragraph(str(idx), dim_style),
            Paragraph(info.file_name, cell_style),
            Paragraph(f'{w_in}" × {h_in}"', dim_style),
            Paragraph(f"{w_ft} ft × {h_ft} ft", dim_style),
        ])

    col_widths = [10*mm, 84*mm, 40*mm, 40*mm]
    file_table = Table(file_rows, colWidths=col_widths, repeatRows=1)

    row_count = len(file_rows)
    ts = TableStyle([
        # Header
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("ALIGN",         (0,0), (-1,0), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        # Grid
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#BDBDBD")),
        ("LINEBELOW",     (0,0), (-1,0),  1.5, BLUE),
    ])
    # Alternating row colours
    for i in range(1, row_count):
        bg = LGRAY if i % 2 == 0 else WHITE
        ts.add("BACKGROUND", (0, i), (-1, i), bg)

    file_table.setStyle(ts)
    story.append(file_table)
    story.append(Spacer(1, 6*mm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY))
    story.append(Spacer(1, 2*mm))
    footer_style = ParagraphStyle(
        "footer", fontSize=8, fontName="Helvetica",
        textColor=GRAY, alignment=TA_CENTER,
    )
    story.append(Paragraph(
        f"Generated by Image Measurement Tool  |  {date_str}  {time_str}  |  Token: {token_id}",
        footer_style,
    ))

    doc.build(story)
    return pdf_path
