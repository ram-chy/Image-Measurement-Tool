"""
Token-slip HTML builder.

The same HTML is shown in the preview pane and sent to QTextDocument for
printing / PDF export, so everything here must stay within the subset of
HTML/CSS supported by Qt's rich-text engine.
"""

import html
from datetime import datetime


def _format_created(value: str) -> str:
    """'2026-11-09 10:30:00' -> '09 Nov 2026, 10:30 AM' (best effort)."""
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %I:%M %p")
    except (TypeError, ValueError):
        return value or ""


def _format_ft_in(value) -> str:
    """Format a measurement in inches as feet + inches (e.g. 27.5 → 2 ft 3.5 in)."""
    try:
        total = round(float(value), 2)
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""

    feet = int(total // 12)
    remainder = round(total - feet * 12, 2)
    if remainder >= 12:
        feet += 1
        remainder = 0.0

    if abs(remainder - round(remainder)) < 0.005:
        inches = str(int(round(remainder)))
    else:
        inches = f"{remainder:.2f}".rstrip("0").rstrip(".")
    return f"{feet} ft {inches} in"


def _format_decimal_ft(value) -> str:
    """Format inches as decimal feet (e.g. 27.5 → 2.292 ft)."""
    try:
        total = round(float(value), 2)
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    return f"{round(total / 12, 3)} ft"


def _format_decimal_in(value) -> str:
    """Format inches as decimal inches (e.g. 27.5 → 27.5 in)."""
    try:
        total = round(float(value), 2)
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    return f"{total} in"


def _format_size(file: dict) -> str:
    """Returns 'W ft × H ft' for a token file row."""
    width  = _format_ft_in(file.get("width_inch"))
    height = _format_ft_in(file.get("height_inch"))
    if not width or not height:
        return "—"
    return f"{width} × {height}"


def _format_size_both(file: dict) -> tuple[str, str]:
    """
    Returns (inches_str, feet_str) for a file row.
    e.g. ('20.0 in × 11.25 in', '1.667 ft × 0.938 ft')
    """
    w_in  = file.get("width_inch")  or 0
    h_in  = file.get("height_inch") or 0
    try:
        w_in  = round(float(w_in), 3)
        h_in  = round(float(h_in), 3)
        w_ft  = round(w_in / 12, 3)
        h_ft  = round(h_in / 12, 3)
        inches = f'{w_in}" × {h_in}"'
        feet   = f"{w_ft} ft × {h_ft} ft"
    except Exception:
        inches = "—"
        feet   = "—"
    return inches, feet


def build_token_html(token: dict, fmt: str = "a4",
                     custom_width_mm: float | None = None) -> str:
    """
    Build the printable token slip.

    fmt: "a4" | "a5" | "thermal" | "custom"
    For "custom", `custom_width_mm` picks the closest hand-tuned layout for
    the paper width (>=170 mm → A4, >=100 mm → A5, narrower → thermal).
    token keys used: token_no, created_at, customer_name, customer_mobile,
                     file_count, files
    files: [{"file_name": ..., "color_mode": ...,
             "width_inch": ..., "height_inch": ...}, ...]
    """
    files = token.get("files") or []
    token_no = html.escape(str(token.get("token_no", "")))
    customer_name = html.escape(str(token.get("customer_name", "")))
    customer_mobile = html.escape(str(token.get("customer_mobile", "")))
    created_at = html.escape(_format_created(token.get("created_at", "")))
    count = token.get("file_count", len(files))

    if fmt == "custom":
        try:
            width = float(custom_width_mm or 0)
        except (TypeError, ValueError):
            width = 0.0
        if width >= 170:
            fmt = "a4"
        elif width >= 100:
            fmt = "a5"
        else:
            fmt = "thermal"

    if fmt == "thermal":
        base, title, sub, token_pt, table_pt = 8.5, 13, 8.5, 11, 8
        contact_pt = 8
    elif fmt == "a5":
        base, title, sub, token_pt, table_pt = 10, 17, 9.5, 13, 9.5
        contact_pt = 9
    else:  # a4
        base, title, sub, token_pt, table_pt = 11.5, 24, 11, 16, 10.5
        contact_pt = 10

    is_thermal = fmt == "thermal"

    # ── Build one block per file (stacked, narrow-slip friendly) ─────────────
    file_blocks = []
    for i, f in enumerate(files, 1):
        name = html.escape(str(f.get("file_name", "")))
        mode = html.escape(str(f.get("color_mode", "") or "—"))
        inches_str, feet_str = _format_size_both(f)
        inches_str = html.escape(inches_str)
        feet_str   = html.escape(feet_str)
        dim_color  = "#444444"
        dim_size   = max(table_pt - 0.5, 7)

        file_blocks.append(
            f'<tr>'
            f'<td width="6%" align="center" valign="top"'
            f'  style="padding-top:4px;"><b>{i}</b></td>'
            f'<td width="94%" style="padding:3px 2px 5px 4px;">'
            f'  <span style="font-size:{table_pt}pt; font-weight:bold;">{name}</span><br>'
            f'  <span style="color:{dim_color}; font-size:{dim_size}pt;">'
            f'    &#x1F4CF;&nbsp;{inches_str}</span><br>'
            f'  <span style="color:{dim_color}; font-size:{dim_size}pt;">'
            f'    &#x1F4D0;&nbsp;{feet_str}</span><br>'
            f'  <span style="color:#666666; font-size:{max(dim_size-0.5,7)}pt;">'
            f'    &#x1F3A8;&nbsp;{mode}</span>'
            f'</td>'
            f'</tr>'
            # thin separator between files
            f'<tr><td colspan="2">'
            f'  <hr style="border:none; border-top:1px dotted #CCCCCC; margin:0;">'
            f'</td></tr>'
        )

    rows_html = "".join(file_blocks) if file_blocks else (
        '<tr><td colspan="2" align="center">No files</td></tr>'
    )

    return f"""
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: 'Segoe UI', 'Nirmala UI', Arial, sans-serif;
    color: #111111;
    font-size: {base}pt;
    margin: 0; padding: 0;
  }}
  .appname {{ color: #555555; font-size: {sub}pt; }}
  .label   {{ color: #444444; }}
  .foot    {{ color: #555555; font-size: {contact_pt}pt; }}
</style>
</head>
<body>

<table width="100%" cellspacing="0" cellpadding="2">
  <tr>
    <td align="center">
      <div style="font-size:{title}pt; font-weight:bold; letter-spacing:2px;">TOKEN SLIP</div>
      <div class="appname">Image Measurement &amp; Report Tool</div>
    </td>
  </tr>
</table>

<hr>

<table width="100%" cellspacing="0" cellpadding="4">
  <tr>
    <td width="36%" class="label"><b>Token No</b></td>
    <td><span style="font-size:{token_pt}pt; font-weight:bold;">{token_no}</span></td>
  </tr>
  <tr>
    <td class="label"><b>Date</b></td>
    <td>{created_at}</td>
  </tr>
  <tr>
    <td class="label"><b>Customer Name</b></td>
    <td><b>{customer_name}</b></td>
  </tr>
  <tr>
    <td class="label"><b>Mobile No</b></td>
    <td>{customer_mobile}</td>
  </tr>
  <tr>
    <td class="label"><b>Total Files</b></td>
    <td>{count}</td>
  </tr>
</table>

<hr>

<div style="font-size:{sub}pt; font-weight:bold;">FILES</div>
<br>

<table width="100%" cellspacing="0" cellpadding="0"
       style="font-size:{table_pt}pt;">
  {rows_html}
</table>

<br>

<div align="center" class="foot">
  Please keep this token slip and bring it when collecting your files.
</div>

</body>
</html>
"""
