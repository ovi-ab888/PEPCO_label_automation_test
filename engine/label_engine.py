"""
engine/label_engine.py
Shared core engine used by every label type (inner, outer, ...).
Takes a FIXED template PDF + one Excel row -> returns a filled PDF (bytes).

Field config entry:
{
    "name": "Excel_Column_Name",
    "type": "text" | "barcode" | "qr",
    "x": 10, "y": 20,                 # position in PDF points, top-left origin
    "font_size": 8,                   # text only
    "prefix": "Style: ",              # optional, text only
    "suffix": "",                     # optional, text only
    "cover": [x0, y0, x1, y1],        # optional: white-out a placeholder area first
    "width": 100, "height": 30,       # barcode only
    "size": 60,                       # qr only
    "font": "arial",                  # optional, key into FONTS dict below
}
"""

import io
import os
import fitz  # PyMuPDF
import qrcode
import barcode
from barcode.writer import ImageWriter

# Map a short font key -> ttf file path. Drop real font files into /fonts and
# list them here for exact brand-font matching. Falls back to built-in Helvetica
# if the file isn't found, so this is fully optional.
FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")
FONTS = {
    "arial": os.path.join(FONTS_DIR, "arial.ttf"),
    "arial_bold": os.path.join(FONTS_DIR, "arialbd.ttf"),
    "tahoma": os.path.join(FONTS_DIR, "tahoma.ttf"),
    "helv_bold_oblique": os.path.join(FONTS_DIR, "Helvetica_Bold_Oblique.ttf"),
    "pepco_ovi": os.path.join(FONTS_DIR, "PEPCO_Ovi.ttf"),
}

# PyMuPDF built-in fonts — always available, no file needed
BUILTIN_FONTS = {
    "helv": "helv",        # Helvetica
    "hebo": "hebo",        # Helvetica-Bold
    "heit": "heit",        # Helvetica-Oblique
    "cour": "cour",        # Courier
    "tiro": "tiro",        # Times Roman
}


def _make_qr_image(data: str) -> bytes:
    img = qrcode.make(str(data))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_barcode_image(data: str, barcode_type: str = "code128") -> bytes:
    data = str(data).strip()

    if barcode_type == "ean13":
        # EAN13 needs exactly 12 digits (checksum is auto-calculated as the 13th).
        # If we were given a full 13-digit code, drop the last digit and let the
        # library recompute+verify the checksum; pad/trim if the data is dirty.
        digits = "".join(ch for ch in data if ch.isdigit())
        if len(digits) >= 13:
            digits = digits[:12]
        elif len(digits) == 12:
            pass
        else:
            digits = digits.zfill(12)
        BARCODE_CLASS = barcode.get_barcode_class("ean13")
        code_input = digits
    else:
        BARCODE_CLASS = barcode.get_barcode_class("code128")
        code_input = data

    buf = io.BytesIO()
    writer = ImageWriter()
    writer.set_options({"write_text": False, "quiet_zone": 1})
    BARCODE_CLASS(code_input, writer=writer).write(buf)
    return buf.getvalue()


def _clean(value):
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return ""
    return str(value)


def fill_single_label(template_path: str, row: dict, field_config: list) -> bytes:
    """Fill ONE label (one Excel row) onto a copy of the template. Returns PDF bytes."""
    doc = fitz.open(template_path)
    page = doc[0]

    for field in field_config:
        name = field["name"]
        if name not in row:
            continue
        value = _clean(row[name])

        x, y = field["x"], field["y"]
        ftype = field.get("type", "text")

        cover = field.get("cover")
        if cover:
            page.draw_rect(fitz.Rect(*cover), color=None, fill=(1, 1, 1))

        if ftype == "text":
            font_size = field.get("font_size", 8)
            color = field.get("color", [0, 0, 0])
            color = tuple(c / 255 if c > 1 else c for c in color)
            text_out = field.get("prefix", "") + value + field.get("suffix", "")

            font_key = field.get("font", "helv")
            fontname = "helv"
            fontfile = None
            if font_key in FONTS and os.path.exists(FONTS[font_key]):
                fontname = font_key
                fontfile = FONTS[font_key]
            elif font_key in BUILTIN_FONTS:
                fontname = BUILTIN_FONTS[font_key]

            page.insert_text(
                (x, y), text_out, fontsize=font_size, color=color,
                fontname=fontname, fontfile=fontfile,
            )

        elif ftype == "qr":
            size = field.get("size", 60)
            img_bytes = _make_qr_image(value)
            page.insert_image(fitz.Rect(x, y, x + size, y + size), stream=img_bytes)

        elif ftype == "barcode":
            w = field.get("width", 150)
            h = field.get("height", 40)
            barcode_type = field.get("barcode_type", "code128")
            img_bytes = _make_barcode_image(value, barcode_type)
            page.insert_image(fitz.Rect(x, y, x + w, y + h), stream=img_bytes)

    out = doc.tobytes()
    doc.close()
    return out


def generate_multipage_pdf(template_path: str, rows: list, field_config: list) -> bytes:
    """rows = list of dicts (each dict = one Excel row). Returns single merged multi-page PDF."""
    merged = fitz.open()
    for row in rows:
        single_bytes = fill_single_label(template_path, row, field_config)
        single_doc = fitz.open("pdf", single_bytes)
        merged.insert_pdf(single_doc)
        single_doc.close()
    out = merged.tobytes()
    merged.close()
    return out
